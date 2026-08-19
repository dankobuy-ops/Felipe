"""ANEXO PROBE — find the anexo control, which this scraper has never once seen.

    python anexo_probe.py --launch --port 9910 --desde 01/07/2026 --hasta 31/07/2026

⚠️ WHY. Watching the operator drive on 2026-08-19 produced FOUR document endpoints that appear
nowhere in this codebase — `anexoDocCivil.php` (30 hits), `anexoCausaCivil.php` (7),
`docCertificadoEscrito.php` (4), `anexoCausaSolicitudCivil.php` (1). `anexoDocCivil` alone
outnumbered `docuN.php` five to one: it is the document class the human actually uses most, and we
have fetched exactly zero of them.

`parse_historia` looks for the anexo as a `<form>` in `td[2]` and has found ONE IN 117,173 ROWS —
that is, none. So the control is not a form in that cell. This opens one causa and dumps enough of
the DOM to find out what it really is.

⚠️ The sequence, from the recording: `anexoCausaCivil.php` OPENS A FOLDER (a modal), and then one
`anexoDocCivil.php` per document inside it. So the contrato costs two acts, not one — open, then
take. A probe that only looks for a direct link will conclude there is nothing there.

Operator, 2026-08-19: the anexo folder is *almost always in the caratulado*, but sometimes it is in
the **Anexo column of book 1's historia** — and for Promotora CMR Falabella it is usually the
historia, with the document called "CTO" or "ctoi" rather than "contrato". So: dump BOTH places,
and never match on the word.

This is READ-ONLY apart from opening one causa and, with --open-anexo, clicking the folder once.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import human_engine as E
import ojv
import worker_a as A
from ojv import note
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent.parent / "data" / "anexo_probe"


# ── what we are looking for, described so the dump is readable ───────────────
# ⚠️ DUMP EVERY CANDIDATE, DO NOT GUESS ONE SELECTOR. The last three times this project looked for
# a control it "knew" the shape of, it found nothing and concluded the site did not have it.
DUMP_JS = r"""
() => {
  const m = document.querySelector('#modalDetalleCivil');
  if (!m) return {err: 'no modal'};
  const brief = (e) => ({
    tag: e.tagName,
    id: e.id || '',
    cls: (e.className || '').toString().slice(0, 60),
    txt: (e.innerText || e.textContent || '').trim().slice(0, 40),
    href: e.getAttribute && e.getAttribute('href'),
    onclick: (e.getAttribute && e.getAttribute('onclick') || '').slice(0, 200),
    title: (e.getAttribute && e.getAttribute('title')) || '',
  });
  // 1. Everything clickable in the modal whose text/onclick/title mentions an anexo, in ANY case.
  const rx = /anexo|adjunt|contrat/i;
  const clickable = [...m.querySelectorAll('a,button,[onclick],form,i,img,span')];
  const anexoish = clickable.filter(e => {
    const s = (e.innerText||'') + ' ' + (e.getAttribute('onclick')||'') + ' ' +
              (e.getAttribute('title')||'') + ' ' + (e.className||'').toString() + ' ' +
              (e.getAttribute('href')||'') + ' ' + (e.getAttribute('alt')||'') + ' ' + (e.id||'');
    return rx.test(s);
  }).map(brief);

  // 2. Every FORM in the modal, with its action and inputs — this is how documents are fetched.
  const forms = [...m.querySelectorAll('form')].map(f => ({
    action: f.getAttribute('action') || '',
    method: f.getAttribute('method') || '',
    where: f.closest('#historiaCiv') ? 'historia' : (f.closest('table') ? 'some-table' : 'header'),
    inputs: [...f.querySelectorAll('input')].map(i => ({name: i.name, len: (i.value||'').length})),
  }));

  // 3. The historia table's HEADER ROW — which column is actually called "Anexo"?
  const hh = [...document.querySelectorAll('#historiaCiv table thead th, #historiaCiv table tr th')]
               .map(t => (t.innerText||'').trim());

  // 4. The first few historia rows, CELL BY CELL, with each cell's inner HTML.
  //    parse_historia assumes doc=td[1], anexo=td[2]. This is how we find out if that is true.
  const rows = [...document.querySelectorAll('#historiaCiv table tbody tr')].slice(0, 3).map(tr => ({
    cells: [...tr.querySelectorAll('td')].map((td, i) => ({
      i, txt: (td.innerText||'').trim().slice(0, 30),
      html: (td.innerHTML||'').replace(/\s+/g, ' ').trim().slice(0, 260),
    })),
  }));

  // 5. The caratulado / header block, so the folder control there can be spotted.
  const head = m.querySelector('.modal-header, .caratulado, #caratulado');
  return {
    anexoish, forms, historiaHeaders: hh, rows,
    headerHTML: head ? head.innerHTML.replace(/\s+/g,' ').slice(0, 1500) : null,
    modalIds: [...m.querySelectorAll('[id]')].map(e => e.id).filter(Boolean).slice(0, 60),
    otherModals: [...document.querySelectorAll('.modal[id]')].map(e => e.id),
  };
}
"""


def main():
    ap = argparse.ArgumentParser(description="Find the anexo control in the causa modal.")
    ap.add_argument("--port", type=int, default=9910)
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--desde", default="01/07/2026")
    ap.add_argument("--hasta", default="31/07/2026")
    ap.add_argument("--tribunal", default="", help="tribunal value; default = the first with rows")
    ap.add_argument("--rows", type=int, default=1, help="how many causas to open")
    ap.add_argument("--open-anexo", action="store_true",
                    help="also CLICK the anexo control and dump whatever modal it opens. One extra "
                         "request per causa; without it this probe never asks the site for a doc.")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        if a.launch:
            import os
            prof = str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / f"pjud_anx{a.port}")
            if not A.launch_chrome(a.port, prof, 0, exe=A.chrome_executable(pw)):
                raise SystemExit("could not start Chrome")
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=45000)
        ctx = b.contexts[0]
        net = []
        p, S, lst = A.enter_and_setup(ctx, net, a.desde, a.hasta)
        if not p:
            raise SystemExit("could not enter")
        note(f"on the form, {len(lst)} tribunales")

        tv = a.tribunal or lst[0]["v"]
        if not E.set_select_mouse(p, "#fecTribunal", tv):
            raise SystemExit(f"could not select tribunal {tv}")
        if not C.human_click(p, "#btnConConsultaFec"):
            raise SystemExit("search click refused")
        state = ojv.wait_results(p, S, net)
        note(f"search -> {state}")

        n = p.eval_on_selector_all("#dtaTableDetalleFecha tbody tr", "e=>e.length")
        note(f"{n} rows on page 1")
        for i in range(min(a.rows, n)):
            rol = p.evaluate(
                "(i)=>{const tr=document.querySelectorAll('#dtaTableDetalleFecha tbody tr')[i];"
                " const td=tr.querySelectorAll('td'); return td[1]?td[1].innerText.trim():'';}", i)
            note(f"opening row {i} — {rol}")
            if not C.human_click(p, p.locator("#dtaTableDetalleFecha tbody tr").nth(i)
                                 .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000):
                note("  click refused, next"); continue
            got = False
            for _ in range(90):
                if p.evaluate("(r)=>{const m=document.querySelector('#modalDetalleCivil');"
                              "return !!m && m.innerText.indexOf(r)>=0;}", rol):
                    got = True; break
                C.human_idle(p, 1.0)
            if not got:
                note("  modal never opened, next"); continue
            C.human_idle(p, 2.0)
            d = p.evaluate(DUMP_JS)
            f = OUT / f"anexo-{rol.replace('/', '-')}.json"
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            note(f"  dumped -> {f.name}")

            print(f"\n  historia column headers: {d.get('historiaHeaders')}")
            print(f"  forms in modal ({len(d.get('forms') or [])}):")
            for fm in (d.get("forms") or [])[:8]:
                print(f"    [{fm['where']:<11}] {fm['action']}  inputs={fm['inputs']}")
            print(f"  anexo-ish controls ({len(d.get('anexoish') or [])}):")
            for e in (d.get("anexoish") or [])[:10]:
                print(f"    {e['tag']:<7} id={e['id']!r} cls={e['cls'][:28]!r} txt={e['txt']!r}")
                if e["onclick"]:
                    print(f"            onclick={e['onclick'][:120]}")
            print(f"  other modals present: {d.get('otherModals')}")

            # ⚠️ THE ANEXO ANCHOR HAS NO id AND NO TEXT — it is an icon. The first version built a
            # selector only when there was an id, so it never clicked anything and reported "no id
            # to click", which reads like the control being absent. Locate it by its ONCLICK
            # PREFIX, which is the only stable thing about it.
            if a.open_anexo:
                # ⚠️ ONE CLICK, on the first candidate that carries an onclick. This is the only
                # request this probe makes beyond the causa open.
                for fn, modal in (("anexoCausaCivil", "#modalAnexoCausaCivil"),
                                  ("anexoSolicitudCivil", "#modalAnexoSolicitudCivil")):
                    loc = p.locator(f"#modalDetalleCivil a[onclick^='{fn}']").first
                    try:
                        if loc.count() == 0:
                            continue
                    except Exception:
                        continue
                    note(f"  clicking {fn} ...")
                    n0 = len(net)
                    try:
                        if not C.human_click(p, loc, timeout=8000):
                            note("    click refused"); continue
                        C.human_idle(p, 3.0)
                        # THE FOLDER'S CONTENTS: this is the list the contrato lives in.
                        inner = p.evaluate(
                            """(sel)=>{const m=document.querySelector(sel); if(!m) return null;
                               const vis = !!(m.offsetWidth||m.offsetHeight||m.getClientRects().length);
                               const rows=[...m.querySelectorAll('table tbody tr')].map(tr=>
                                 [...tr.querySelectorAll('td')].map(td=>({
                                   txt:(td.innerText||'').trim().slice(0,60),
                                   html:(td.innerHTML||'').replace(/\s+/g,' ').trim().slice(0,240)})));
                               const forms=[...m.querySelectorAll('form')].map(f=>({
                                 action:f.getAttribute('action')||'', target:f.getAttribute('target')||'',
                                 inputs:[...f.querySelectorAll('input')].map(i=>({n:i.name,len:(i.value||'').length}))}));
                               const links=[...m.querySelectorAll('a[onclick]')].map(x=>({
                                 txt:(x.innerText||'').trim().slice(0,40),
                                 oc:(x.getAttribute('onclick')||'').slice(0,80)}));
                               return {visible:vis, text:(m.innerText||'').trim().slice(0,400),
                                       rows, forms, links};}""", modal)
                        (OUT / f"folder-{fn}-{rol.replace('/', '-')}.json").write_text(
                            json.dumps(inner, ensure_ascii=False, indent=1), encoding="utf-8")
                        print(f"    {modal} visible={inner and inner.get('visible')}")
                        print(f"    text: {(inner or {}).get('text','')[:220]!r}")
                        for fm in ((inner or {}).get("forms") or [])[:8]:
                            print(f"      FORM {fm['action']} target={fm['target']} inputs={fm['inputs']}")
                        for lk in ((inner or {}).get("links") or [])[:8]:
                            print(f"      LINK {lk['txt']!r} {lk['oc']}")
                        for r_ in ((inner or {}).get("rows") or [])[:6]:
                            print(f"      ROW {[c['txt'] for c in r_]}")
                        print(f"    requests: {[q['u'].split('/')[-1] for q in net[n0:]][:8]}")
                        C.close_modal(p, modal)
                        C.human_idle(p, 1.5)
                    except Exception as e:
                        note(f"    {fn} failed: {str(e)[:90]}")
            C.close_modal(p, "#modalDetalleCivil")
            C.human_idle(p, 2.0)
        note("done")


if __name__ == "__main__":
    main()
