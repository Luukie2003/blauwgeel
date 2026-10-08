"""PDF-opmaak: bestellijst, voorraadoverzicht, kassatelling, verkooprapporten, schaplabels,
de compacte uitdraai, omzet per seizoen en het logboek.

Vroeger 1 bestand van ruim 1000 regels; nu per onderwerp opgesplitst. Alles wordt hier
opnieuw beschikbaar gemaakt, dus `from pdf import ...` werkt ongewijzigd.
"""

from pdf.basis import (
    KLEUR_ACCENT,
    KLEUR_BLAUW,
    KLEUR_BLAUW_DONKER,
    KLEUR_GEEL,
    KLEUR_GRIJS,
    KLEUR_KOPRIJ,
    KLEUR_RAND,
    KLEUR_WIT,
    KLEUR_ZEBRA,
    LOGO_PAD,
    NAAM_APP,
    NAAM_CLUB,
    Rapport,
    _datum_nl,
    _euro,
    _kort,
)
from pdf.voorraad import bestellijst_pdf, voorraadoverzicht_pdf
from pdf.kas import kassa_pdf
from pdf.verkoop import periode_verkoop_pdf, verkoop_pdf
from pdf.labels import (
    LABEL_BREEDTE,
    LABEL_GAP,
    LABEL_HOOGTE,
    LABEL_MARGE_BOVEN,
    LABEL_MARGE_LINKS,
    LABEL_STROKEN_PER_PAGINA,
    schaplabels_pdf,
    stemming_poster_pdf,
)
from pdf.seizoen import (
    SEIZOEN_PDF_MAX_SEIZOENEN,
    _procent,
    _seizoen_tabel_kop,
    seizoen_samenvatting_tabel,
    seizoensrapport_pdf,
)
from pdf.uitdraai import (
    UITDRAAI_KOLOM_BREEDTE,
    UITDRAAI_KOLOM_X,
    UITDRAAI_RIJ_HOOGTE,
    _ruimte_voor,
    _uitdraai_bestellijst,
    _uitdraai_geldblok,
    _uitdraai_prognose,
    _uitdraai_voorraadrijen,
    compacte_uitdraai_pdf,
)
from pdf.logboek import _logboek_kop, logboek_pdf

__all__ = [
    "KLEUR_ACCENT",
    "KLEUR_BLAUW",
    "KLEUR_BLAUW_DONKER",
    "KLEUR_GEEL",
    "KLEUR_GRIJS",
    "KLEUR_KOPRIJ",
    "KLEUR_RAND",
    "KLEUR_WIT",
    "KLEUR_ZEBRA",
    "LOGO_PAD",
    "NAAM_APP",
    "NAAM_CLUB",
    "Rapport",
    "_euro",
    "_kort",
    "bestellijst_pdf",
    "voorraadoverzicht_pdf",
    "kassa_pdf",
    "periode_verkoop_pdf",
    "verkoop_pdf",
    "LABEL_BREEDTE",
    "LABEL_GAP",
    "LABEL_HOOGTE",
    "LABEL_MARGE_BOVEN",
    "LABEL_MARGE_LINKS",
    "LABEL_STROKEN_PER_PAGINA",
    "schaplabels_pdf",
    "stemming_poster_pdf",
    "SEIZOEN_PDF_MAX_SEIZOENEN",
    "seizoen_samenvatting_tabel",
    "seizoensrapport_pdf",
    "UITDRAAI_KOLOM_BREEDTE",
    "UITDRAAI_KOLOM_X",
    "UITDRAAI_RIJ_HOOGTE",
    "compacte_uitdraai_pdf",
    "logboek_pdf",
]
