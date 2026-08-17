"""HUMAN MOTION — keep a pointer alive on the page the way a hand does.

⚠️ WHY, AND WHY THE OLD ATTEMPT DOES NOT COUNT. `cdp_scrape.human_idle` already emits "hand
jitter" during the pacing waits, was tested on 2026-08-14, and changed nothing — so the channel
was written off. Then we measured a real person doing the same work (`human_record.py`,
2026-08-16) and the numbers said the test had been run at the wrong amplitude:

    channel            a person          --idle-motion        worker A between clicks
    mousemove          25.8 /s           ~1 /s                0
    mouseover           6.4 /s (modal)   ~0 (jitter crosses    only what the click path
                                          no element)          crosses
    seconds with no
    pointer motion      2%               most                 nearly all

⇒ idle jitter was ONE TWENTY-SIXTH of a hand, and it vibrated in place instead of travelling, so
it generated no `mouseover` at all. The negative result stands for that implementation and says
nothing about the channel. This module is the amplitude the measurement actually calls for.

THE MODEL IS THE MEASUREMENT, not an idea of how hands move. From 2,482 sampled path points of a
real 6.5-minute session (median step 13 px, mean 47, p90 124, max 874; 15% of steps under 3 px,
19% over 60 px; median speed 258 px/s, p90 2,462):

    REST      15%   a hand resting on the mouse: sub-3 px tremor
    DRIFT     66%   wandering 20-150 px at ~250 px/s, which is what crosses rows and
                    produces the mouseover stream
    TRAVERSE  19%   a real 200-900 px journey at 1,500-2,500 px/s toward something

⚠️ IT MUST TRAVEL, NOT VIBRATE. The `mouseover` rate is the tell that distinguishes the two, and
it is the one idle-motion could never have produced.

⚠️ COST, MEASURED not assumed: one `mouse.move` over CDP costs 16.7 ms (300 moves in 5.02 s), so
~60/s is the ceiling and the ~26/s a person emits needs no batching at all. I had assumed this
would require `Input.dispatchMouseEvent` batching and said so; it does not.

⚠️ A POINTER CANNOT LEAVE THE VIEWPORT. Every target is clamped — an unclamped
getBoundingClientRect().top once went straight into mouse.move().
"""

import math
import random
import time


class Presence:
    """A hand resting on this page. Call run() wherever the worker would otherwise be still."""

    def __init__(self, page, rate=52.0, margin=6):
        # ⚠️ THE TARGET RATE IS NOT THE ACHIEVED RATE — measure it, do not set it and believe it.
        # Each mouse.move costs ~17 ms over CDP and the caller's polling steals more: asking for
        # 26/s measured 15-22/s, and asking for 34/s measured 16.7/s. Roughly half of what is
        # requested survives, so the default is set at twice the 25.8/s a hand produces.
        # Aim above the number you want and CHECK: worker H reports its own mousemove/s beside
        # the human's on every record, because a rate you did not measure is a rate you guessed.
        self.page = page
        self.rate = float(rate)
        self.margin = margin
        self.w, self.h = 1200, 800
        self.x, self.y = 600.0, 400.0
        self.leg = []                 # points still to emit on the current leg
        # ⚠️ WHERE THE POINTER GOES MATTERS AS MUCH AS THAT IT MOVES. The first version was a
        # random walk from a fixed start, and the operator caught it in seconds, watching:
        # "it's not moving in the modal, only in the left-sided menu". A random walk has no
        # reason to be anywhere, so it pools where it began — and the whole point of this module
        # is the `mouseover` stream, which exists only when the pointer is OVER THE CONTENT.
        # A person's pointer follows what they are reading. So does this one.
        self.focus = None             # (x, y, w, h) the pointer should mostly live inside
        self.moves = 0
        self.legs = {"rest": 0, "drift": 0, "traverse": 0}
        self._sync_bounds()

    def _sync_bounds(self):
        try:
            d = self.page.evaluate("()=>({w:innerWidth,h:innerHeight,"
                                   " x:0, y:0})")
            self.w, self.h = max(200, d["w"]), max(200, d["h"])
        except Exception:
            pass
        self.x = min(max(self.x, self.margin), self.w - self.margin)
        self.y = min(max(self.y, self.margin), self.h - self.margin)

    def _clamp(self, x, y):
        return (min(max(x, self.margin), self.w - self.margin),
                min(max(y, self.margin), self.h - self.margin))

    def aim(self, target, selector=None):
        """Point the hand at what is being read, or at what it is about to click.

        Accepts either `aim(page, "#css")` or `aim(locator)` — the second is what lets a caller
        aim at ONE row of a table, which is the difference between a hand travelling to its next
        target and a hand drifting around the general area.

        Keeps the previous aim if the element is not there. Cheap enough to call every record.
        """
        try:
            loc = target.locator(selector).first if selector is not None else target.first
            b = loc.bounding_box()
        except Exception:
            b = None
        if not b or b["width"] < 40 or b["height"] < 40:
            return False
        self.focus = (b["x"], b["y"], b["width"], b["height"])
        return True

    def _target(self):
        """Somewhere worth looking — and usually NEAR where the hand already is.

        ⚠️ LOCAL FIRST, OR THE MIX INVERTS. Picking any point in the focus box makes almost every
        target 200+ px away, so every leg becomes a fast traverse: measured 77% traverse / 8%
        drift against the human's 19% / 66%. The pointer then pinballs across the record instead
        of reading it, and `drift` is the leg that does the actual work — it is the slow local
        wandering that crosses rows and generates the `mouseover` stream. A hand reads within a
        paragraph and only occasionally crosses the page.
        """
        far = random.random() < 0.22
        if self.focus:
            x, y, w, h = self.focus
            if not far:
                # A short hop from here, kept inside what is being read.
                ang, d = random.uniform(0, 2 * math.pi), random.uniform(20, 150)
                return (min(max(self.x + math.cos(ang) * d, x + 2), x + w - 2),
                        min(max(self.y + math.sin(ang) * d, y + 2), y + h - 2))
            return self._clamp(x + random.uniform(0.03, 0.97) * w,
                               y + random.uniform(0.03, 0.97) * h)
        if not far:
            ang, d = random.uniform(0, 2 * math.pi), random.uniform(20, 150)
            return self._clamp(self.x + math.cos(ang) * d, self.y + math.sin(ang) * d)
        return self._clamp(random.uniform(0, self.w), random.uniform(0, self.h))

    def _plan(self):
        """Choose the next leg. The measured mix stays; the DESTINATION is now the content."""
        if random.random() < 0.15:
            self.legs["rest"] += 1
            tx, ty = self._clamp(self.x + random.uniform(-2.5, 2.5),
                                 self.y + random.uniform(-2.5, 2.5))
            speed = random.uniform(6, 30)
        else:
            tx, ty = self._target()
            d = math.hypot(tx - self.x, ty - self.y)
            # Far means a real journey, near means a wander — so the measured 19%/66% split
            # ARISES from where the content is, instead of being imposed on a direction that had
            # no destination in the first place.
            if d > 200:
                self.legs["traverse"] += 1
                speed = random.uniform(1500, 2500)
            else:
                self.legs["drift"] += 1
                speed = random.uniform(180, 420)
        real = math.hypot(tx - self.x, ty - self.y)
        n = max(1, int(round(real / max(1e-6, speed) * self.rate)))
        sx, sy = self.x, self.y
        bow = random.uniform(-0.12, 0.12) * real       # hands do not travel in straight lines
        pts = []
        for i in range(1, n + 1):
            t = i / n
            ease = t * t * (3 - 2 * t)
            perp = math.sin(math.pi * t) * bow
            nx = sx + (tx - sx) * ease - (ty - sy) / max(1e-6, real) * perp
            ny = sy + (ty - sy) * ease + (tx - sx) / max(1e-6, real) * perp
            pts.append(self._clamp(nx + random.uniform(-1.1, 1.1),
                                   ny + random.uniform(-1.1, 1.1)))
        if real < 4:
            # A resting hand emits FEWER events, not none. Hold the spot for a beat.
            hold = int(random.uniform(0.3, 1.5) * self.rate * 0.25)
            pts += [self._clamp(tx + random.uniform(-2, 2), ty + random.uniform(-2, 2))
                    for _ in range(hold)]
        self.leg = pts

    def step(self):
        """Emit exactly one pointer event. Never raises — a hand is not worth a run."""
        if not self.leg:
            self._plan()
        x, y = self.leg.pop(0)
        try:
            self.page.mouse.move(x, y)
            self.x, self.y = x, y
            self.moves += 1
        except Exception:
            self.leg = []

    def run(self, secs, poll=None, poll_every=0.5):
        """Be present for `secs`, moving throughout. If `poll()` returns something truthy, stop
        early and return it — so a wait for the modal is spent MOVING rather than frozen, which
        is the single largest difference between us and a person (they emit 25 moves/s through
        the two seconds a causa takes to load; we emit none).
        """
        end = time.time() + max(0.0, secs)
        interval = 1.0 / self.rate
        last_poll = 0.0
        while True:
            now = time.time()
            if now >= end:
                return None
            if poll is not None and now - last_poll >= poll_every:
                last_poll = now
                try:
                    got = poll()
                except Exception:
                    got = None
                if got:
                    return got
            t0 = time.time()
            self.step()
            # Feed whatever watcher is installed, through the hook that already exists rather
            # than a second mechanism. Presence is where the wall-clock now lives, so a live
            # view that only ticked in human_idle would see nothing at all in this worker.
            if self.moves % max(1, int(self.rate * 2)) == 0:
                try:
                    import cdp_scrape as _C
                    if _C.IDLE_HOOK is not None:
                        _C.IDLE_HOOK(self.page)
                except Exception:
                    pass
            gap = interval - (time.time() - t0)
            if gap > 0:
                time.sleep(min(gap, max(0.0, end - time.time())))

    def travel_to(self, target, selector=None, timeout=3.0):
        """Move the hand ONTO something, and stop when it gets there.

        ⚠️ THIS REPLACES EVERY FIXED WAIT (operator, 2026-08-16: "no padding at all — just mimic
        me"). A duration copied off a recording is padding wearing a measurement's clothes: the
        person's two seconds between opening a record and switching its tab was them LOOKING and
        then MOVING THEIR HAND THERE, and if you reproduce the two seconds instead of the moving
        you get a worker that idles for two seconds and then teleports. Travel to the target and
        let the clock report whatever it reports.

        Returns True if the pointer arrived. `timeout` is a safety stop, not a pace.
        """
        if not self.aim(target, selector):
            return False
        x, y, w, h = self.focus
        end = time.time() + timeout
        while time.time() < end:
            if x <= self.x <= x + w and y <= self.y <= y + h:
                return True
            self.run(0.12)
        return False

    def stats(self):
        return {"moves": self.moves, **self.legs}
