"""Een mail naar de beheerder zodra de site een serverfout (HTTP 500) geeft.

Zonder dit staan crashes alleen in het foutenlog op PythonAnywhere, dat niemand leest: de fouten van
10 t/m 21 september 2026 waren zo dagen lang onopgemerkt. De mail bevat welke pagina het was, wie er
was ingelogd, de versie en de technische foutmelding -- niet de zoekopdracht (?...), niet wat er in
een formulier is ingevuld en geen sleutels of tokens uit de url.

Om de mailbox niet vol te spammen: dezelfde fout wordt maximaal 1 keer per uur gemeld en er gaan
nooit meer dan MAX_PER_UUR mails per uur uit. Het versturen gebeurt op de achtergrond, zodat de
bezoeker niet op de mailserver hoeft te wachten."""

import re
import threading
import time
import traceback
from collections import deque

MAX_PER_UUR = 10
ZELFDE_FOUT_PAUZE_SECONDEN = 3600
MAX_TRACEBACK_REGELS = 25

# Stukjes van een pad die op een token/sleutel lijken (lange reeksen letters, cijfers, - en _; een
# gewoon pad als "wachtwoord-instellen" blijft zo leesbaar).
_TOKEN = re.compile(r"[A-Za-z0-9_\-]{24,}")


def masker_pad(pad):
    """/wachtwoord-instellen/<lang token> -> /wachtwoord-instellen/…; de zoekopdracht valt weg."""
    return _TOKEN.sub("…", (pad or "").split("?")[0])


def vingerafdruk(fout):
    """Wat 'dezelfde fout' is: het soort fout en de plek in de code waar hij optrad."""
    frames = traceback.extract_tb(fout.__traceback__) if fout.__traceback__ else []
    laatste = frames[-1] if frames else None
    plek = f"{laatste.filename}:{laatste.lineno}" if laatste else "?"
    return f"{type(fout).__name__}@{plek}"


def maak_rapport(fout, *, endpoint, methode, pad, gebruiker, versie, commit):
    """(onderwerp, tekst) van de mail."""
    regels = traceback.format_exception(type(fout), fout, fout.__traceback__)
    technisch = "".join(regels).strip().splitlines()
    if len(technisch) > MAX_TRACEBACK_REGELS:
        technisch = ["…"] + technisch[-MAX_TRACEBACK_REGELS:]
    onderwerp = f"Serverfout op de kantinesite: {type(fout).__name__} bij {masker_pad(pad) or endpoint}"
    tekst = (
        "Er is een fout opgetreden op de kantinesite (de bezoeker kreeg een foutpagina).\n\n"
        f"Pagina:       {methode} {masker_pad(pad)}\n"
        f"Onderdeel:    {endpoint or '-'}\n"
        f"Ingelogd als: {gebruiker or '(niet ingelogd)'}\n"
        f"Versie:       {versie} ({commit or 'onbekend'})\n\n"
        "Technische melding:\n" + "\n".join(technisch) + "\n\n"
        "Dezelfde fout wordt het komende uur niet nog eens gemeld. Het volledige foutenlog staat op "
        "PythonAnywhere (Web-tab > Log files > Error log)."
    )
    return onderwerp, tekst


class Melder:
    """Bepaalt of een fout gemeld mag worden (zie de moduledocstring) en verstuurt de mail."""

    def __init__(self, max_per_uur=MAX_PER_UUR, pauze=ZELFDE_FOUT_PAUZE_SECONDEN):
        self._max_per_uur = max_per_uur
        self._pauze = pauze
        self._laatst_gemeld = {}
        self._verstuurd = deque()
        self._slot = threading.Lock()

    def mag_melden(self, vinger, nu=None):
        nu = time.time() if nu is None else nu
        with self._slot:
            while self._verstuurd and nu - self._verstuurd[0] > 3600:
                self._verstuurd.popleft()
            if len(self._verstuurd) >= self._max_per_uur:
                return False
            if nu - self._laatst_gemeld.get(vinger, -self._pauze - 1) < self._pauze:
                return False
            self._laatst_gemeld[vinger] = nu
            self._verstuurd.append(nu)
            return True

    def meld(self, fout, versturen, *, op_achtergrond=True, **context):
        """versturen = functie(onderwerp, tekst). Geeft True als er een mail is (of wordt) verstuurd."""
        if not self.mag_melden(vingerafdruk(fout)):
            return False
        onderwerp, tekst = maak_rapport(fout, **context)
        if op_achtergrond:
            threading.Thread(target=self._veilig_versturen, args=(versturen, onderwerp, tekst), daemon=True).start()
        else:
            self._veilig_versturen(versturen, onderwerp, tekst)
        return True

    @staticmethod
    def _veilig_versturen(versturen, onderwerp, tekst):
        try:
            versturen(onderwerp, tekst)
        except Exception as fout:  # een mislukte mail mag nooit een tweede fout veroorzaken
            print(f"[foutmelding] versturen mislukt: {fout}")
