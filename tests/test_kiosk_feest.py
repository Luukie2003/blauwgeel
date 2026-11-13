"""De feestdia op de kantine-tv (2.12.0, zie kiosk_feest.py): het sjabloon 'feest' in de clubkleuren, met de titel en de
knaller zo groot als ze passen, een tekening, het effect feest, en het opslaan en het live voorbeeld bij het formulier."""

import json

from conftest import stel_csrf_token_in as _csrf
from test_kiosk_momenten import _dia

import kiosk_feest
import kiosk_momenten


def test_de_tekst_van_de_actie_past_op_de_dia():
    fs = kiosk_feest.delen("Topscoorder trakteert", ["op 2 pitchers!"], True, "Bij winst van Blauw-Geel")
    assert fs["vorm"] == "poster"
    assert fs["titel_regels"] == ["Topscoorder", "trakteert"]  # twee regels: zo is de titel het grootst
    assert fs["aanloop"] == "op" and fs["knal"] == [[("2", True), (" pitchers!", False)]]  # het getal extra groot
    assert 8 < fs["titel_vw"] <= 12 and 5 < fs["knal_vw"] <= 7.6 and fs["label_vw"] > 0
    # Zonder tekening staat alles in het midden, met meer ruimte in de breedte.
    assert kiosk_feest.delen("Topscoorder trakteert", ["op 2 pitchers!"], False, "Bij winst")["vorm"] == "midden"


def test_elke_tekst_past_ook_een_lange():
    lang = "Vanavond na de wedstrijd groot feest in de kantine met muziek en een verrassing"
    fs = kiosk_feest.delen(lang, ["Elk doelpunt een rondje", "bitterballen voor € 2,50"], True, None)
    assert 1 <= len(fs["titel_regels"]) <= 3
    breedste = max(kiosk_feest._maat(r) for r in fs["titel_regels"])
    assert breedste * fs["titel_vw"] <= 90.01  # niet breder dan de dia
    assert fs["regels"] == [("Elk doelpunt een rondje", fs["regels"][0][1])]
    assert fs["aanloop"] == "bitterballen voor" and fs["knal"] == [[("€ 2,50", True)]]
    # Zonder getal is de hele regel de knal, eventueel over twee regels; zonder tekst geen sticker.
    knal = kiosk_feest.delen("Kampioen!", ["Gratis bitterballen voor iedereen"], False, None)
    assert knal["aanloop"] is None and all(not getal for regel in knal["knal"] for _, getal in regel)
    leeg = kiosk_feest.delen("Kampioen!", [], False, None)
    assert leeg["knal"] == [] and leeg["titel_vw"] == 14.0 and leeg["label_vw"] == 0


def test_de_getallen_in_de_knaller():
    assert kiosk_feest.delen_van("2 halen, 1 betalen") == [("2", True), (" halen, ", False), ("1", True), (" betalen", False)]
    assert kiosk_feest.delen_van("nu 5,- per pitcher") == [("nu ", False), ("5,-", True), (" per pitcher", False)]
    assert kiosk_feest.delen_van("Proost!") == [("Proost!", False)]


def test_de_tekening_en_het_effect_horen_bij_de_feestdia():
    assert "feest" in kiosk_momenten.EFFECTEN and kiosk_momenten.EFFECTEN["feest"][2] is None  # geen gloed op een prijs
    assert json.loads(kiosk_momenten.schoon_opties("feest", None, None, None, "feest", "pitchers")) == {"tekening": "pitchers"}
    assert kiosk_momenten.schoon_opties("feest", None, None, None, "feest", "ketel") is None  # een griezeltekening niet
    assert kiosk_momenten.schoon_opties("vuur", "50", "50", None, "feest", None) is None  # de prijs klopt zelf
    assert kiosk_momenten.schoon_opties(None, None, None, None, "griezel", "pitchers") is None
    assert kiosk_momenten.tekening_van({"sjabloon": "feest", "effect_opties": '{"tekening": "beker"}'}) == "beker"
    assert kiosk_momenten.tekening_van({"sjabloon": "griezel", "effect_opties": '{"tekening": "beker"}'}) is None


def test_de_feestdia_op_de_tv(client, db):
    dia = _dia(db, "Topscoorder trakteert", sjabloon="feest", effect="feest", tekst="op 2 pitchers!",
               label="Bij winst van Blauw-Geel")
    db.execute("UPDATE kiosk_sponsoren SET effect_opties = ? WHERE id = ?", (json.dumps({"tekening": "pitchers"}), dia))
    db.commit()
    html = client.get("/kiosk/scherm").get_data(as_text=True)
    assert "sjabloon-feest" in html and 'class="fs fs--poster"' in html and 'data-effect="feest"' in html
    assert "<span>Bij winst van Blauw-Geel</span>" in html and "<span>Topscoorder</span><span>trakteert</span>" in html
    assert '<span class="fs-getal">2</span> pitchers!</p>' in html and "fs-tekening--pitchers" in html
    assert html.count('class="fs-vlag"') == len(kiosk_feest.VLAGGEN)


def test_zonder_label_de_tijd_van_het_moment_op_het_lint(client, db):
    from test_kiosk_momenten import _straks

    moment = _straks()
    _dia(db, "Kampioen!", moment=moment, sjabloon="feest", effect="feest", tekst="Feest!")
    html = client.get("/kiosk/scherm").get_data(as_text=True)
    assert f"<span>{moment[11:16]} uur</span>" in html and 'class="fs-lint" style="font-size: 0vw;"' not in html


def test_een_feestdia_opslaan_en_het_voorbeeld(ingelogde_client, db):
    ingelogde_client.post("/kiosk/sponsoren-leden/sponsoren/nieuw", data={
        "csrf_token": _csrf(ingelogde_client), "sjabloon": "feest", "titel": "Topscoorder trakteert",
        "tekst": "op 2 pitchers!", "label": "Bij winst van Blauw-Geel", "weergave_duur_seconden": "12", "actief": "1",
        "effect": "feest", "tekening": "pitchers"})
    d = db.execute("SELECT * FROM kiosk_sponsoren ORDER BY id DESC").fetchone()
    assert (d["sjabloon"], d["label"], d["effect"]) == ("feest", "Bij winst van Blauw-Geel", "feest")
    assert json.loads(d["effect_opties"]) == {"tekening": "pitchers"}
    pagina = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{d['id']}/bewerken").get_data(as_text=True)
    assert '<option value="pitchers" selected>' in pagina and '"feest": [["pitchers"' in pagina
    resp = ingelogde_client.get("/kiosk/griezel-voorbeeld?sjabloon=feest&titel=Kampioen!&tekst=Feest&tekening=beker")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "sjabloon-feest" in html and "fs-tekening--beker" in html and "<span>Kampioen!</span>" in html
    # Een onbekend sjabloon in het adres: gewoon de griezeldia.
    assert "sjabloon-griezel" in ingelogde_client.get("/kiosk/griezel-voorbeeld?sjabloon=onzin&titel=X").get_data(as_text=True)


def test_het_poppetje_met_een_praatwolkje(ingelogde_client, client, db):
    fs = kiosk_feest.delen("Koud in de kantine?", ["Vraag het aan Koen", "Regelen we binnenkort!"], True, "Brrr!", wolk=True)
    assert fs["wolk"] and fs["aanloop"] is None and fs["knal"] == [[("Regelen we", False)], [("binnenkort!", False)]]
    dia = _dia(db, "Koud in de kantine?", sjabloon="feest", effect="sneeuw", tekst="Vraag het aan Koen\nRegelen we binnenkort!")
    db.execute("UPDATE kiosk_sponsoren SET effect_opties = ? WHERE id = ?", (json.dumps({"tekening": "poppetje"}), dia))
    db.commit()
    html = client.get("/kiosk/scherm").get_data(as_text=True)
    assert "fs--wolk" in html and '<div class="fs-wolk">' in html and "fs-tekening--poppetje" in html
    assert 'data-effect="sneeuw"' in html and "fs-sticker" not in html
    assert "sneeuw" in kiosk_momenten.EFFECTEN and "poppetje" in kiosk_momenten.tekeningen_voor("feest")
