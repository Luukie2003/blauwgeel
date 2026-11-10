"""De vraag 'Weet je het zeker?' bij verwijderen, archiveren en corrigeren (bevestigEnVerstuur in gedeeld.js). Een naam
mag nooit in een JavaScript-string staan: met een apostrof erin (Lay's, 't Hart) brak de vraag dan, en ging het
formulier zonder te vragen door. De tekst staat daarom in data-vraag, en het script leest this.dataset.vraag."""

import re
from pathlib import Path

SJABLONEN = Path(__file__).resolve().parent.parent / "templates"


def test_geen_sjabloonwaarde_in_een_javascript_string():
    fout = []
    for pad in sorted(SJABLONEN.glob("*.html")):
        for m in re.finditer(r'bevestigEnVerstuur\(this, \'([^"]*)"', pad.read_text(encoding="utf-8")):
            if "{{" in m.group(1):
                fout.append(f"{pad.name}: {m.group(0)[:80]}")
    assert fout == [], "zet de vraag in data-vraag en gebruik this.dataset.vraag:\n" + "\n".join(fout)


def test_een_naam_met_een_apostrof_staat_veilig_in_de_vraag(ingelogde_client, db):
    db.execute("INSERT INTO producten (naam, categorie) VALUES ('Lay''s Paprika', 'Chips')")
    db.commit()
    tekst = ingelogde_client.get("/producten").data.decode()
    assert 'data-vraag="Product \'Lay&#39;s Paprika\' verwijderen?' in tekst
    assert "Lay&#39;s Paprika\\'" not in tekst  # niet meer in een JavaScript-string


def test_ook_blokkeren_vraagt_het_weer(ingelogde_client, db):
    # Deze vraag had altijd aanhalingstekens rond de naam en brak dus bij elk account.
    db.execute(
        """INSERT INTO gebruikers (naam, wachtwoord_hash, rol, actief, aangemaakt_op)
           VALUES ('Jan ''t Hart', 'x', 'vrijwilliger', 1, '2026-01-01 10:00')"""
    )
    db.commit()
    tekst = ingelogde_client.get("/accounts").data.decode()
    assert 'data-vraag="Account &#39;Jan &#39;t Hart&#39; blokkeren?' in tekst
