"""Launch + drive the monitored Chrome for the HDI scraper.

Chrome is a real chrome.exe launched with only a debug port + a persistent
profile (logins survive between runs), so the page has NO automation flags and
looks like a normal user's browser. Every command attaches over CDP, does ONE
thing, and detaches — your manual navigation is never disturbed.

Usage:
  python cdp.py launch [url]                 # open the monitored Chrome window
  python cdp.py pages                        # list open tabs (idx, title, url)
  python cdp.py shot [out.png] [--match s]   # screenshot the (matched) tab
  python cdp.py js "<expr>" [--match s]      # eval a JS expression, print JSON

--match picks the tab whose URL/title contains the substring (default: the last
non-devtools tab, usually the one in front).
"""
import sys, os, json, subprocess, time, urllib.request

PORT = int(os.environ.get("CDP_PORT", "9333"))
PROFILE = os.environ.get("CDP_PROFILE", os.path.expanduser("~/.cache/portal-chrome"))
CHROME = os.environ.get("CDP_CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def http_pages():
    try:
        raw = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=4).read()
        return [p for p in json.loads(raw) if p.get("type") == "page"]
    except Exception:
        return []


def launch(url):
    if http_pages():
        print(f"Chrome already up on port {PORT}."); return
    os.makedirs(PROFILE, exist_ok=True)
    subprocess.Popen([
        CHROME,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-popup-blocking",          # act like a normal user (ads/popups ok)
        url or "about:blank",
    ])
    for _ in range(80):
        if http_pages():
            print(f"Chrome up on port {PORT} (profile: {PROFILE})"); return
        time.sleep(0.5)
    sys.exit(f"Chrome didn't expose the debug port {PORT} in time.")


def _pick(pages, match):
    real = [p for p in pages if not p.get("url", "").startswith("devtools://")] or pages
    if match:
        for p in real:
            if match.lower() in (p.get("url", "") + " " + p.get("title", "")).lower():
                return p
        sys.exit(f"No tab matches {match!r}. Run `pages` to see open tabs.")
    return real[-1]


def _sp():
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        from playwright.sync_api import sync_playwright
    return sync_playwright


def with_page(match, fn):
    pages = http_pages()
    if not pages:
        sys.exit("Chrome isn't running (no debug port). Run `launch` first.")
    turl = _pick(pages, match).get("url", "")
    with _sp()() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        try:
            allpages = [pg for ctx in browser.contexts for pg in ctx.pages]
            page = next((pg for pg in allpages if pg.url == turl), None) or \
                   (allpages[-1] if allpages else None)
            if page is None:
                sys.exit("No attachable page found.")
            return fn(page)
        finally:
            browser.close()  # disconnect only; Chrome keeps running


def cmd_pages():
    for i, p in enumerate(http_pages()):
        print(f"[{i}] {p.get('title','')[:60]!r}  {p.get('url','')}")


def cmd_js(expr, match):
    with_page(match, lambda pg: print(json.dumps(pg.evaluate(expr), ensure_ascii=False, indent=2, default=str)))


def cmd_shot(out, match):
    def run(pg):
        pg.screenshot(path=out, full_page=False); print(f"saved {out}")
    with_page(match, run)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    cmd, rest = args[0], args[1:]
    match = None
    if "--match" in rest:
        i = rest.index("--match"); match = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
    if cmd == "launch":
        launch(rest[0] if rest else None)
    elif cmd == "pages":
        cmd_pages()
    elif cmd == "shot":
        cmd_shot(rest[0] if rest else "shot.png", match)
    elif cmd == "js":
        cmd_js(rest[0], match)
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main()
