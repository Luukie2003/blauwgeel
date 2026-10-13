"""Beheer > Foutmeldingen: elke serverfout (HTTP 500) komt in de database, samengevoegd per soort fout en plek in de
code, met hoe vaak en wanneer het laatst. Zo hoef je het foutenlog van de hosting niet zelf door te lezen.

Wat er bewaard wordt, is hetzelfde als in de melding van foutmelding.py: de pagina zonder zoekopdracht of tokens, de
versie en de technische melding; niets uit formulieren. Een opgeloste melding komt terug zodra de fout opnieuw optreedt."""

import traceback

from foutmelding import MAX_TRACEBACK_REGELS, masker_pad, vingerafdruk
from helpers.tijd import now_str


def registreer_fout(db, fout, *, endpoint=None, pad=None, versie=None):
    """Legt een serverfout vast (of telt hem op bij dezelfde fout). Gooit zelf nooit een uitzondering."""
    try:
        frames = traceback.extract_tb(fout.__traceback__) if fout.__traceback__ else []
        plek = f"{frames[-1].filename.rsplit('/', 1)[-1]}:{frames[-1].lineno}" if frames else None
        regels = "".join(traceback.format_exception(type(fout), fout, fout.__traceback__)).strip().splitlines()
        technisch = "\n".join(regels[-MAX_TRACEBACK_REGELS:])
        nu = now_str()
        db.rollback()  # wat het mislukte verzoek half had geschreven, hoort niet bewaard te worden
        db.execute(
            """INSERT INTO fouten (sleutel, fouttype, melding, plek, endpoint, pad, versie, technisch, eerste_op, laatste_op)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(sleutel) DO UPDATE SET
                   aantal = aantal + 1, laatste_op = excluded.laatste_op, melding = excluded.melding,
                   endpoint = excluded.endpoint, pad = excluded.pad, versie = excluded.versie,
                   technisch = excluded.technisch, opgelost = 0""",
            (vingerafdruk(fout), type(fout).__name__, str(fout)[:500], plek, endpoint, masker_pad(pad), versie,
             technisch, nu, nu),
        )
        db.commit()
    except Exception as tweede:  # het vastleggen mag nooit een tweede fout geven
        print(f"[foutenlog] vastleggen mislukt: {tweede}")


def recente_open_fouten(db, dagen=7):
    """Hoeveel verschillende, niet opgeloste fouten er de laatste 'dagen' dagen zijn opgetreden (voor het overzicht)."""
    from datetime import datetime, timedelta

    grens = (datetime.now() - timedelta(days=dagen)).strftime("%Y-%m-%d %H:%M")
    return db.execute("SELECT COUNT(*) FROM fouten WHERE opgelost = 0 AND laatste_op >= ?", (grens,)).fetchone()[0]
