"""TRACE SHEET — turn a runner's step trace into one HTML page you can actually read.

    python trace_sheet.py --dir ../data/shots/trace --out ../data/shots/trace.html

⚠️ ONE FILE, SELF-CONTAINED. A trace of an arrival is ~30 frames and a full shift is thousands;
a zip of loose JPEGs is a picture that was captured and still never looked at. The frames are
embedded as data URIs so the page survives being downloaded from an artifact, opened on another
machine, or pasted somewhere — nothing to resolve, nothing to unzip in order.

⚠️ IT SAYS WHEN IT TRUNCATES. A sheet that quietly drops the last 300 frames reads exactly like a
run that stopped early, which is the one thing a trace exists to disambiguate.
"""
import argparse
import base64
import html
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load(d):
    """Every frame, ordered — jsonl first, then any JPEG on disk the jsonl never got to."""
    rows, seen = [], set()
    jl = d / "trace.jsonl"
    if jl.exists():
        for line in jl.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            rows.append(r)
            seen.add(r.get("img"))
    for p in sorted(d.glob("*.jpg")):
        if p.name not in seen:
            # A frame whose jsonl line never landed — the run was killed between the two writes.
            # That is precisely the last frame before a hard stop, so never drop it.
            rows.append({"img": p.name, "tag": p.stem.split("-", 1)[-1], "n": 0,
                         "url": "(no metadata — trace.jsonl line was never written)"})
    rows.sort(key=lambda r: (r.get("n") or 0, r.get("img") or ""))
    return rows


CSS = """
:root{--bg:#f7f7f8;--card:#fff;--ink:#16181d;--dim:#5d6470;--line:#e3e5ea;--accent:#8c1d1d}
:root:not([data-theme=light]) {}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  --bg:#101215;--card:#181b20;--ink:#e8eaee;--dim:#9aa2ae;--line:#272b33;--accent:#e06c6c}}
:root[data-theme=dark]{--bg:#101215;--card:#181b20;--ink:#e8eaee;--dim:#9aa2ae;--line:#272b33;--accent:#e06c6c}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);
 font:14px/1.5 ui-sans-serif,system-ui,'Segoe UI',sans-serif}
h1{font-size:18px;margin:0 0 4px}
.sub{color:var(--dim);margin-bottom:20px}
.f{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:0 0 18px;
 overflow:hidden}
.hd{display:flex;gap:12px;align-items:baseline;padding:10px 14px;border-bottom:1px solid var(--line);
 flex-wrap:wrap}
.n{font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}
.tag{font-weight:600}
.t{color:var(--dim);font-variant-numeric:tabular-nums;margin-left:auto}
.meta{padding:8px 14px;color:var(--dim);font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;
 word-break:break-word}
.meta b{color:var(--ink);font-weight:600}
img{display:block;width:100%;height:auto;border-top:1px solid var(--line)}
.warn{background:var(--accent);color:#fff;padding:10px 14px;border-radius:8px;margin:16px 0}
"""


def main():
    ap = argparse.ArgumentParser(description="Build one HTML page from a step-trace directory.")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--max", type=int, default=250, help="frames to embed (says so when it cuts)")
    a = ap.parse_args()

    d = Path(a.dir)
    if not d.exists():
        print(f"no trace at {d} — nothing to build")
        return
    rows = load(d)
    if not rows:
        print(f"{d} has no frames")
        return
    cut = max(0, len(rows) - a.max)
    shown = rows[:a.max]

    out = [f"<title>Step trace — {html.escape(a.title or d.parent.name)}</title>",
           f"<style>{CSS}</style>",
           f"<h1>Step trace — {html.escape(a.title or d.parent.name)}</h1>",
           f"<div class=sub>{len(rows)} frame(s), before and after every action.</div>"]
    if cut:
        out.append(f"<div class=warn>Showing the first {a.max} of {len(rows)} frames — "
                   f"{cut} not embedded, to keep this page openable. They are in the artifact.</div>")
    for r in shown:
        img = d / (r.get("img") or "")
        b64 = ""
        if img.exists():
            b64 = base64.b64encode(img.read_bytes()).decode("ascii")
        bits = []
        for k in ("url", "title", "frames", "modals", "sheets", "sx", "sy", "extra"):
            v = r.get(k)
            if v in (None, "", [], 0):
                continue
            bits.append(f"<b>{k}</b> {html.escape(str(v))[:400]}")
        txt = " / ".join(t.strip() for t in str(r.get("text", "")).splitlines() if t.strip())[:300]
        if txt:
            bits.append(f"<b>text</b> {html.escape(txt)}")
        out.append(
            "<div class=f><div class=hd>"
            f"<span class=n>{r.get('n', 0):04d}</span>"
            f"<span class=tag>{html.escape(str(r.get('tag', '')))}</span>"
            f"<span class=t>t+{r.get('t', 0)}s</span></div>"
            f"<div class=meta>{'<br>'.join(bits)}</div>"
            + (f"<img loading=lazy src='data:image/jpeg;base64,{b64}'>" if b64
               else "<div class=meta>(frame file missing)</div>")
            + "</div>")
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(shown)} frame(s) -> {p}  ({p.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
