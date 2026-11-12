"""De tekst uit een pdf van de site, voor de tests. Sinds 2.9.0 staan de pdf's in de Barlow-letter (pdf/basis.py): dan
staat er in de pdf per teken een glyphnummer in plaats van de letter zelf. fpdf2 schrijft per letter een ToUnicode-tabel
mee (zodat je in een pdf-lezer kunt zoeken en kopiëren); daarmee maakt pdf_tekst er weer gewone tekst van. Een stuk tekst
in een standaardletter (zonder tabel) wordt als cp1252 gelezen."""

import re
import zlib

_OBJECT = re.compile(rb"(?<![0-9])(\d+) 0 obj\b")
_TEKST = re.compile(rb"/(F\d+)\s+[\d.]+\s+Tf|\(((?:\\.|[^\\)])*)\)", re.S)
_ONTSNAPT = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f"}


def _objecten(data):
    begin = [(m.start(), int(m.group(1))) for m in _OBJECT.finditer(data)]
    return {nummer: data[start:(begin[i + 1][0] if i + 1 < len(begin) else len(data))]
            for i, (start, nummer) in enumerate(begin)}


def _stroom(obj):
    m = re.search(rb"stream\r?\n(.*)\r?\nendstream", obj, re.S)
    if not m:
        return b""
    try:
        return zlib.decompress(m.group(1))
    except zlib.error:
        return m.group(1)


def _naar_unicode(cmap):
    tabel = {}
    for blok in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.S):
        for bron, doel in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blok):
            tabel[int(bron, 16)] = bytes.fromhex(doel.decode()).decode("utf-16-be")
    for blok in re.findall(rb"beginbfrange(.*?)endbfrange", cmap, re.S):
        for van, tot, doel in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blok):
            for i, cid in enumerate(range(int(van, 16), int(tot, 16) + 1)):
                tabel[cid] = chr(int(doel, 16) + i)
    return tabel


def _ontsnap(ruw):
    uit, i = bytearray(), 0
    while i < len(ruw):
        if ruw[i] == 0x5C and i + 1 < len(ruw):  # een backslash
            volgend = ruw[i + 1]
            if volgend in _ONTSNAPT:
                uit += _ONTSNAPT[volgend]
                i += 2
            elif 0x30 <= volgend <= 0x37:  # octaal, tot drie cijfers
                cijfers = re.match(rb"[0-7]{1,3}", ruw[i + 1:i + 4]).group()
                uit.append(int(cijfers, 8) & 0xFF)
                i += 1 + len(cijfers)
            else:
                uit.append(volgend)
                i += 2
        else:
            uit.append(ruw[i])
            i += 1
    return bytes(uit)


def pdf_tekst(data):
    """Alle tekst van de pdf, een stuk per regel (zoals fpdf2 hem per cel wegschrijft)."""
    objecten = _objecten(data)
    tabellen = {}
    for nummer, obj in objecten.items():
        m = re.search(rb"/ToUnicode (\d+) 0 R", obj)
        if m and int(m.group(1)) in objecten:
            tabellen[nummer] = _naar_unicode(_stroom(objecten[int(m.group(1))]))
    letters = {}
    for obj in objecten.values():
        for blok in re.findall(rb"/Font\s*<<(.*?)>>", obj, re.S):
            for naam, nummer in re.findall(rb"/(F\d+)\s+(\d+) 0 R", blok):
                letters[naam.decode()] = tabellen.get(int(nummer))
    stukken = []
    for obj in objecten.values():
        inhoud = _stroom(obj)
        if b"BT" not in inhoud:
            continue
        tabel = None
        for m in _TEKST.finditer(inhoud):
            if m.group(1):
                tabel = letters.get(m.group(1).decode())
                continue
            ruw = _ontsnap(m.group(2))
            if tabel is None:
                stukken.append(ruw.decode("cp1252", "replace"))
            else:
                stukken.append("".join(tabel.get(int.from_bytes(ruw[i:i + 2], "big"), "")
                                        for i in range(0, len(ruw) - 1, 2)))
    return "\n".join(stukken)
