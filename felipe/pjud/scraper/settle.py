"""wait_settled() — the four-condition quiescence check, all passive.

Nothing here injects input. Reading the DOM over CDP is the proven-innocent path (2026-07-22),
so polling is free and we can afford to be paranoid.

Conditions, ALL required to hold CONTINUOUSLY for `quiet_ms`:
  1. site spinner idle            -- cdp_scrape.page_busy() == False (#loadPre*)
  2. content assertion true       -- caller's JS predicate (assert CONTENT, never timing)
  3. no in-flight site requests   -- tracked here, EXCLUDING F5's Shape endpoint, because
                                     Playwright's networkidle never fires on this site (Shape
                                     posts 238KB telemetry pairs continuously)
  4. DOM quiet                    -- MutationObserver timestamp older than quiet_ms

Any one of these alone is a false-positive generator: the spinner misses F5's retries, the
content check misses CSS fade transitions, and network state alone misses rendering.
"""
import re, time

# F5 Shape's obfuscated channel: a 32-hex path segment. Never wait on it — it never stops.
SHAPE_RE = re.compile(r"/[0-9a-f]{24,40}(\?|$)")


class Settler:
    def __init__(self, page):
        self.page = page
        self.inflight = 0
        self._seen = set()
        page.on("request", self._req)
        page.on("requestfinished", self._done)
        page.on("requestfailed", self._done)

    def _tracked(self, r):
        u = r.url
        if "pjud.cl" not in u or SHAPE_RE.search(u):
            return False
        return r.resource_type in ("document", "xhr", "fetch") or u.endswith(".php")

    def _req(self, r):
        if self._tracked(r):
            self._seen.add(r)
            self.inflight += 1

    def _done(self, r):
        if r in self._seen:
            self._seen.discard(r)
            self.inflight = max(0, self.inflight - 1)

    def arm_observer(self):
        """Stamp window.__lastMut on every DOM change. Re-armed after each navigation."""
        try:
            self.page.evaluate("""()=>{
              if (window.__mo) return;
              window.__lastMut = Date.now();
              window.__mo = new MutationObserver(()=>{ window.__lastMut = Date.now(); });
              window.__mo.observe(document.documentElement,
                  {childList:true, subtree:true, attributes:true, characterData:true});
            }""")
            return True
        except Exception:
            return False

    def dom_quiet_ms(self):
        try:
            v = self.page.evaluate("()=>window.__lastMut?Date.now()-window.__lastMut:99999")
            return int(v)
        except Exception:
            return 99999   # context destroyed mid-navigation -> not quiet

    def wait(self, need=None, quiet_ms=1200, timeout=45, label=""):
        """need: JS expression string evaluating truthy when the target content is present."""
        import cdp_scrape as C
        self.arm_observer()
        deadline = time.time() + timeout
        ok_since = None
        while time.time() < deadline:
            busy = C.page_busy(self.page)
            try:
                content = bool(self.page.evaluate(f"()=>!!({need})")) if need else True
            except Exception:
                content = False
            quiet = self.dom_quiet_ms()
            allgood = (not busy) and content and self.inflight == 0 and quiet >= quiet_ms
            if allgood:
                if ok_since is None:
                    ok_since = time.time()
                if (time.time() - ok_since) * 1000 >= 300:
                    el = timeout - (deadline - time.time())
                    print(f"      [settled{':'+label if label else ''}] {el:.1f}s "
                          f"(spinner=idle content=ok inflight=0 domQuiet={quiet}ms)")
                    return True
            else:
                ok_since = None
                self.arm_observer()   # re-arm if a navigation wiped it
            self.page.wait_for_timeout(200)
        print(f"      [NOT settled{':'+label if label else ''}] busy={C.page_busy(self.page)} "
              f"content={content} inflight={self.inflight} domQuiet={self.dom_quiet_ms()}ms")
        return False
