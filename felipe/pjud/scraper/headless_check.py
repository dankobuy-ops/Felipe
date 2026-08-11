"""Is headless viable against the OJV? Run this locally instead of burning runner minutes.

Answer as of 2026-08-11: NO — and that is the whole explanation for the old workflow's 13 days of
"could not establish the date search form". Measured back to back with identical code:

    headed (under Xvfb on a GitHub runner)   entered, 232 tribunales, search returned results
    headless=new (locally, same code)        entry failed after 102 s, NO captcha, form never came

F5's challenge script tests document.visibilityState before it will run. A headless browser has
no visible surface, so the challenge never completes and the OJV never renders the entry form.
The click IS delivered — the page simply never becomes usable, which looks exactly like a refusal
and is not one.

⇒ Any remote runner must use Xvfb + a HEADED browser. `playwright install chromium --with-deps`
  plus `Xvfb :99` and DISPLAY=:99, never --headless.
"""
import sys, os, time, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright
import ojv

PORT = 9402
prof = Path(os.environ.get("LOCALAPPDATA", "/tmp")) / "pjud_headless_test"

with sync_playwright() as pw:
    proc = subprocess.Popen(
        [pw.chromium.executable_path, f"--remote-debugging-port={PORT}",
         f"--user-data-dir={prof}", "--headless=new", "--no-sandbox",
         "--disable-dev-shm-usage", "--window-size=1440,900", "https://www.pjud.cl/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    up = False
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2).read()
            up = True
            break
        except Exception:
            time.sleep(1)
    print("headless CDP up:", up)
    if up:
        ctx = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=60000).contexts[0]
        t0 = time.time()
        p = ojv.walk_in(ctx)
        print(f"entered: {p is not None} after {time.time()-t0:.0f}s   "
              f"captcha: {any(ojv.captcha_frame(q) for q in ctx.pages)}")
        print("VERDICT:", "headless works" if p else "headless CANNOT enter — use Xvfb + headed")
    proc.terminate()
