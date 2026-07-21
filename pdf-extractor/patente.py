"""Extract Chilean vehicle plates from (noisy) OCR text of JPL demandas.

Chilean plates are ALWAYS 6 chars:
  - old format: 2 letters + 4 digits   (e.g. ZP1185)
  - new format: 4 letters + 2 digits   (e.g. KGDD66); new-format letters never
    include vowels A E I O U.
In these 'cobro de peaje' demandas the plate(s) appear right after the phrase
'placa patente N°', which OCR mangles to 'piaca patente N�' / 'Ne' etc. The word
'patente' itself OCRs cleanly, so we anchor on it and read the uppercase run that
follows, chunked into 6-char plates.
"""
import re

OLD = re.compile(r"^[A-Z]{2}\d{4}$")             # 2 letters + 4 digits (pre-2008)
NEW = re.compile(r"^[BCDFGHJKLMNPQRSTVWXYZ]{4}\d{2}$")  # 4 consonants + 2 digits (2008+)

def is_plate(tok: str) -> bool:
    """Any Chilean plate shape — used only to keep 6-char run alignment."""
    return bool(OLD.match(tok) or NEW.match(tok))

def is_new(tok: str) -> bool:
    """New-format (2008+) plate: 4 non-vowel letters + 2 digits. The only kind we keep."""
    return bool(NEW.match(tok))

# A new-format plate anywhere in a text window: 4 non-vowel letters + 2 digits.
_NEW_SCAN = re.compile(r"[BCDFGHJKLMNPQRSTVWXYZ]{4}\d{2}")

def plates_after_anchor(text: str, window: int = 70):
    """New-format plates found in the window right after each 'patente' anchor.

    Handles both templates seen in JPL demandas:
      - Procobro:  '...placa patente N° KGDD66 las referidas'   (glued after N°)
      - Costanera: '...placa(s) patente(s) única(s) es (son): BCXY81.'  (after a phrase)
    Scanning (findall) walks a glued multi-plate run AND skips intervening words;
    upper-casing first absorbs OCR case slips (e.g. 'BcxY81' -> 'BCXY81'). The
    4-consonant+2-digit shape plus the anchor keeps false positives away (old-format
    noise like 'NE2025' / 'RE2023' never matches)."""
    found = []
    for m in re.finditer(r"(?i)patente", text):
        chunk = text[m.end(): m.end() + window].upper()
        for p in _NEW_SCAN.findall(chunk):
            if p not in found:
                found.append(p)
    return found


# Page-level context that marks a demanda's vehicle page — used to gate the
# page-wide fallback so we don't scan unrelated pages. 'peaje' is ubiquitous in
# these toll demandas, so the gate is lenient; the strict plate shape does the
# real filtering.
_CTX = re.compile(r"(?i)veh[ií]cul|p[il]aca|patent|peaje|concesionar|telev[ií]")

# Legal-citation cues near a candidate token mean it's NOT a plate. E.g. OCR reads
# 'artículos 75 del DFL 850 de 1997' as '...delDFL850...' and 'LDFL85' (from "l DFL
# 85") matches the plate shape — a false positive that recurs across many demandas.
_CITATION = re.compile(r"DFL|DECRETO|\bLEY\b|ART[IÍ]CULO|\bDS\b|\bMOP\b")

def plates_in_text(text: str, window: int = 70):
    """Robust extraction for one CLEAN (text-layer) page: anchor-based first
    (precise); if that finds nothing AND the page looks like a vehicle/demanda
    page, fall back to a page-wide new-format scan, skipping tokens that sit inside
    a legal citation. Do NOT use this on noisy OCR text — call plates_after_anchor
    there, since the page-wide fallback mines boilerplate when OCR is garbled."""
    found = plates_after_anchor(text, window)
    if found:
        return found
    if _CTX.search(text):
        up = text.upper()
        for m in _NEW_SCAN.finditer(up):
            ctx = up[max(0, m.start() - 18): m.end() + 6]
            if _CITATION.search(ctx):
                continue                       # legal citation, not a plate
            if m.group() not in found:
                found.append(m.group())
    return found


if __name__ == "__main__":
    CASES = {
        "1096": ("...piaca patente N�KGDD66lasreferidas autopistas.",
                 ["KGDD66"]),
        "1097": ("...piaca patente N�ZP1185RPRW87 PJCL63las referidas",
                 ["RPRW87", "PJCL63"]),   # ZP1185 is old-format -> dropped
        "1014": ("placapatente NeLHGG92RXSG12DRJK73LXRK27LKSC66,las",
                 ["LHGG92", "RXSG12", "DRJK73", "LXRK27", "LKSC66"]),
        "1088": ("placapatenteN�RWPC55RSVP40PTGB95DSLZ32PSBT36JRTH19PRDD53PSPK20",
                 ["RWPC55", "RSVP40", "PTGB95", "DSLZ32", "PSBT36", "JRTH19", "PRDD53", "PSPK20"]),
        # Costanera template: plate follows a phrase, and OCR lowercased 2 letters
        "277": ("vehiculo(s), cuya(s) placa(s) patente(s) unica(s) es (son): BcxY81.",
                ["BCXY81"]),
    }
    ok = True
    for name, (txt, exp) in CASES.items():
        got = plates_after_anchor(txt)
        good = got == exp
        ok = ok and good
        print(f"{'PASS' if good else 'FAIL'} {name}: {got}" + ("" if good else f"  expected {exp}"))
    print("\nALL PASS" if ok else "\nSOME FAILED")
