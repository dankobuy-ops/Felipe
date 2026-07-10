"""Cloudflare-friendly browser session for patentechile.com.

Empirical finding (2026-07): when Playwright/patchright *launches* Chrome it adds
automation flags (--no-sandbox, --disable-blink-features=AutomationControlled,
--remote-debugging-pipe, a pile of --disable-features). Cloudflare's Turnstile
loops forever on such a browser — the "Verify you are human" checkbox never
passes. A normally-launched Chrome (only a debug port + a persistent profile,
exactly like the user's own browser) passes with one human click.

So this module:
  1. launches a NORMAL Chrome ourselves (subprocess, real chrome.exe),
  2. lets a human solve the Cloudflare challenge with NOTHING attached
     (detected via the debug server's page-title, which doesn't instrument the
     page and so can't trip Cloudflare),
  3. only ATTACHES over CDP afterwards to drive the search.

Cloudflare only scrutinises the challenge page, so once solved the attached
automation is invisible on the data pages. The cf_clearance cookie persists in
the profile, so most later runs skip the challenge entirely; if it reappears
mid-run we detach, let the human re-solve, and re-attach.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

HOME = "https://www.patentechile.com/"
PROFILE_DIR = os.path.expanduser("~/.cache/patente-chrome")
DEBUG_PORT = 9444


class CFChallenge(Exception):
    """A Cloudflare challenge blocked this lookup — retryable, not a real 'no data'."""


def find_chrome():
    """Locate a real Google Chrome executable across common OS locations."""
    candidates = []
    if sys.platform.startswith("win"):
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(
                    base, "Google", "Chrome", "Application", "chrome.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        candidates += ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                       "/opt/google/chrome/chrome"]
    return next((p for p in candidates if os.path.exists(p)), None)


class Session:
    """A live patentechile.com session: a normally-launched Chrome we attach to
    over CDP, with a human in the loop for Cloudflare."""

    def __init__(self, profile=PROFILE_DIR, port=DEBUG_PORT, on_prompt=None):
        self.profile = profile
        self.port = port
        self._proc = None
        self._pw = None
        self._browser = None
        self._page = None
        self._prompt = on_prompt or (lambda m: print(m, flush=True))

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self):
        chrome = find_chrome()
        if not chrome:
            raise SystemExit(
                "[FATAL] Google Chrome no esta instalado (es obligatorio para pasar "
                "Cloudflare). Instalalo desde https://www.google.com/chrome/ y reintenta.")
        os.makedirs(self.profile, exist_ok=True)
        print(f"[patentes] abriendo Chrome real: {chrome}", flush=True)
        self._proc = subprocess.Popen([
            chrome,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run", "--no-default-browser-check",
            HOME,
        ])
        self._pw = sync_playwright().start()
        self._wait_boot()
        self.ensure_past_wall()
        return self

    def close(self):
        # Best-effort quit via CDP (on Windows the launched chrome.exe hands off to
        # a background process, so terminating our proc handle may not kill Chrome).
        try:
            self._attach()
            cdp = self._browser.contexts[0].new_cdp_session(self._page)
            cdp.send("Browser.close")
        except Exception:
            pass
        self._detach()
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        try:
            if self._proc:
                self._proc.terminate()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    def alive(self):
        # The debug server answering == Chrome is up. Don't use proc.poll(): on
        # Windows the launched chrome.exe exits after handing off to a background
        # process, which would look "dead" even though the window is open.
        return bool(self._http_pages())

    # ── attach / detach ──────────────────────────────────────────────────────
    def _attach(self):
        if self._browser is not None:
            return
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        ctx = self._browser.contexts[0]
        pages = ctx.pages or [ctx.new_page()]
        self._page = next((p for p in pages if "patentechile" in (p.url or "")), pages[0])

    def _detach(self):
        if self._browser is not None:
            try:
                self._browser.close()   # disconnect only — Chrome keeps running
            except Exception:
                pass
        self._browser = None
        self._page = None

    @property
    def page(self):
        if self._browser is None:
            self._attach()
        return self._page

    def dismiss_popups(self):
        """Close ad pop-ups / pop-unders (extra tabs) and dismiss simple overlay
        ads. Safe: only closes tabs that are NOT the patentechile page."""
        if self._browser is None:
            return
        try:
            for p in list(self._browser.contexts[0].pages):
                if p is not self._page and "patentechile" not in (p.url or ""):
                    try:
                        p.close()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self._page.keyboard.press("Escape")   # dismisses many overlay ads
        except Exception:
            pass

    # ── Cloudflare wall ──────────────────────────────────────────────────────
    def _http_pages(self):
        try:
            raw = urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/list", timeout=4).read()
            return [p for p in json.loads(raw) if p.get("type") == "page"]
        except Exception:
            return []

    def _wait_boot(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._http_pages():
                return
            time.sleep(0.5)

    def _blocked(self):
        """Are we stuck on the Cloudflare wall? Judged from the debug server's
        page list (title/URL only) — no page instrumentation, so it can't trip CF.
        Solved homepage title is 'Patentes Chile ...'; the wall is 'Just a moment...'."""
        pat = [p for p in self._http_pages() if "patentechile" in p.get("url", "")]
        if not pat:
            return True
        url = pat[0].get("url", "")
        title = (pat[0].get("title", "") or "").strip().lower()
        if "__cf_chl" in url:
            return True
        if not title or "just a moment" in title:
            return True
        if any(m in title for m in ("un momento", "verific", "checking your browser",
                                    "attention required")):
            return True
        return False

    def ensure_past_wall(self, solve_timeout=240, grace=8):
        """Guarantee we're past Cloudflare. Gives a brief grace for an auto-clearing
        challenge / slow load; if still blocked, DETACHES (so nothing is
        instrumented), asks the human to click the checkbox, waits until it clears,
        then re-attaches. Cheap no-op when already clear."""
        deadline = time.time() + grace
        while True:
            if not self._blocked():
                self._attach()
                return
            if time.time() >= deadline:
                break
            time.sleep(1)

        self._detach()                       # let the human solve un-automated
        self._prompt(
            "\n" + "=" * 64 +
            "\n>>> Cloudflare pide verificacion. En la ventana de Chrome, haz clic"
            "\n>>> en la casilla 'Verifique que es un ser humano' / 'Verify you are human'."
            "\n>>> (No cierres la ventana; en cuanto pase, sigo solo.)\n" + "=" * 64)
        deadline = time.time() + solve_timeout
        while time.time() < deadline:
            time.sleep(2)
            if not self._blocked():
                self._prompt("[patentes] OK, verificacion superada. Continuo.")
                time.sleep(1.5)
                self._attach()
                return
        raise CFChallenge("La verificacion de Cloudflare no se completo a tiempo.")

    def goto_home(self, form_timeout=12):
        """Navigate to the homepage, transparently clearing the wall if needed.
        Returns a page whose search box (#inputTerm) is ready, or raises CFChallenge."""
        last = None
        for _ in range(3):
            self.ensure_past_wall()          # detach+solve if blocked, else attach
            page = self.page
            try:
                page.goto(HOME, wait_until="domcontentloaded", timeout=30_000)
            except Exception as e:
                last = e
            time.sleep(1.5)
            if self._blocked():              # a wall appeared on this navigation
                continue
            if self._form_ready(page, form_timeout):
                return page
        raise CFChallenge(f"el buscador no aparecio tras pasar Cloudflare ({last})")

    @staticmethod
    def _form_ready(page, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if page.locator("#inputTerm").count():
                    return True
            except Exception:
                return False
            page.wait_for_timeout(700)
        return False
