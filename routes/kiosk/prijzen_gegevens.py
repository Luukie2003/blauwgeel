"""Gegevens voor het prijzenscherm: categorieën en kolommen, acties, bardienst, uitgelicht product en de versie-hash."""

import json
from datetime import date, timedelta

from helpers import bepaal_tegenstander, vandaag_amsterdam
from sponsoren import bouw_sponsor_dias
from routes.kiosk.gedeeld import _prijzen_instellingen, _scherm_instellingen, _versie


def _prijzen_categorieen(db, uitgelicht_product_id=None):
    # Eén algemene prijslijst voor elke dag: de producten met
    # toon_op_kiosk aan.
    producten = db.execute(
        """SELECT * FROM producten
           WHERE actief = 1 AND toon_op_kiosk = 1
           ORDER BY categorie, naam"""
    ).fetchall()
    opties_per_product = {}
    for optie in db.execute(
        "SELECT * FROM product_prijsopties ORDER BY product_id, volgorde, id"
    ).fetchall():
        opties_per_product.setdefault(optie["product_id"], []).append(optie)

    per_categorie = {}
    for p in producten:
        if uitgelicht_product_id is not None and p["id"] == uitgelicht_product_id:
            # Dit product wordt al apart, groot en los van zijn categorie
            # getoond (zie _uitgelicht_product) -- niet nog eens hier.
            continue
        # kiosk_categorie is een optionele override, alleen voor de
        # indeling op dit scherm -- de echte categorie (tellen,
        # rapportage) blijft ongemoeid. Handig voor een product met
        # prijsopties (bijv. een fust in categorie 'Telling') dat je
        # liever onder een bestaande verkoopcategorie toont, bijv.
        # 'Bier'.
        weergave_categorie = p["kiosk_categorie"] or p["categorie"]
        opties = opties_per_product.get(p["id"])
        if opties:
            # Een fust-achtig product wordt zelf niet in zijn geheel
            # verkocht: i.p.v. de eigen verkoopprijs tonen we de losse
            # porties die eruit getapt/geschonken worden (bijv. pitcher
            # of glas, zie product_form.html). Is het hele product als
            # uitverkocht gemarkeerd (leeg fust), dan geldt dat voor elke
            # portie ervan.
            for optie in opties:
                per_categorie.setdefault(weergave_categorie, []).append(
                    {
                        "id": optie["id"],
                        "naam": optie["naam"],
                        # Los van "naam" (de portienaam, bijv. "Klein
                        # glas") bewaard voor _uitverkocht_namen hieronder
                        # -- die moet het onderliggende product tonen
                        # (bijv. "Jupiler"), niet de portienaam.
                        "product_naam": p["naam"],
                        "verkoopprijs": optie["prijs"],
                        "kiosk_uitverkocht": p["kiosk_uitverkocht"],
                    }
                )
        else:
            per_categorie.setdefault(weergave_categorie, []).append(p)
    # Op naam sorteren binnen de groep: door de kiosk_categorie-override
    # kunnen producten uit verschillende echte categorieën in dezelfde
    # groep belanden, in een andere volgorde dan de SQL ORDER BY hierboven
    # (die op de ECHTE categorie sorteert) garandeert.
    for lijst in per_categorie.values():
        lijst.sort(key=lambda p: p["naam"].lower())
    return sorted(per_categorie.items())


def _uitgelicht_product(db, instellingen=None):
    """Het door de beheerder gekozen 'uitgelicht'-product (bijv. Snack
    van de week, zie kiosk_prijzen_instellingen.html) -- groot en
    omlijnd getoond op het prijzenscherm, los van zijn eigen categorie.
    None als er niets gekozen is, of het gekozen product inmiddels
    verwijderd/gedeactiveerd is (dan verdwijnt de kaart gewoon, net als
    de rest van dit scherm bij een leeg blok -- zie _bouw_slides).
    instellingen mag al opgehaald zijn meegegeven (zie
    _prijzen_render_kwargs/kiosk_prijzen_versie) i.p.v. 'm hier nogmaals
    op te vragen -- dat scheelt een herhaalde losse query per poll."""
    instellingen = instellingen or _prijzen_instellingen(db)
    product_id = instellingen["uitgelicht_product_id"]
    if product_id is None:
        return None
    p = db.execute(
        "SELECT id, naam, verkoopprijs, kiosk_uitverkocht FROM producten WHERE id = ? AND actief = 1",
        (product_id,),
    ).fetchone()
    if p is None:
        return None
    return {
        "titel": instellingen["uitgelicht_titel"],
        "product_id": p["id"],
        "naam": p["naam"],
        "verkoopprijs": p["verkoopprijs"],
        "kiosk_uitverkocht": p["kiosk_uitverkocht"],
    }


def _acties_actief(db):
    """Actieve prijs-acties met de gegevens van het gekoppelde product --
    voor de korte, opvallende pop-up die af en toe over het
    prijzenscherm heen verschijnt (zie kiosk_prijzen_scherm.html).
    Gebruikt bewust de foto/prijs van het product zelf, geen losse
    afbeelding per actie."""
    return db.execute(
        """SELECT ka.id, ka.tekst, p.naam AS product_naam, p.verkoopprijs, p.afbeelding
           FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id
           WHERE ka.actief = 1
           ORDER BY ka.id"""
    ).fetchall()


def _uitverkocht_namen(categorieen):
    # Bij prijsopties (fust-achtige producten, zie hierboven) is "naam"
    # de portienaam (bijv. "Klein glas"); voor de uitverkocht-popup moet
    # het onderliggende product getoond worden ("product_naam", bijv.
    # "Jupiler"), en maar 1x per product, ook al zijn er meerdere
    # uitverkochte porties van hetzelfde product.
    namen = []
    for _, lijst in categorieen:
        for p in lijst:
            if not p["kiosk_uitverkocht"]:
                continue
            naam = p["product_naam"] if "product_naam" in p.keys() else p["naam"]
            if naam not in namen:
                namen.append(naam)
    return namen


def _bardiensten_vandaag(db):
    """Bardiensten rond vandaag, op datum+tijd gesorteerd -- geen
    wekelijks terugkerend rooster, dus alleen echte datums tellen mee
    (zie kiosk_bardienst hieronder voor de planning zelf). Haalt bewust
    ook gisteren en morgen op (serverdatum) i.p.v. alleen exact vandaag:
    de server draait op UTC terwijl het scherm in Europe/Amsterdam
    staat, dus rond middernacht kan de serverdatum een paar uur
    achterlopen op de kloktijd van de kantine zelf. Welke dienst nu
    precies actief is (en het afhandelen van een dienst die middernacht
    overschrijdt, bijv. 22:00-01:00) wordt daarom client-side bepaald
    met de eigen klok van het scherm, zie kiosk_prijzen_scherm.html."""
    vandaag = date.today()
    return db.execute(
        "SELECT * FROM kiosk_bardiensten WHERE datum BETWEEN ? AND ? ORDER BY datum, start_tijd",
        ((vandaag - timedelta(days=1)).isoformat(), (vandaag + timedelta(days=1)).isoformat()),
    ).fetchall()


def _bardiensten_voor_scherm(bardiensten):
    return [
        {"datum": b["datum"], "start_tijd": b["start_tijd"], "eind_tijd": b["eind_tijd"], "namen": b["namen"]}
        for b in bardiensten
    ]


def _wedstrijddag_welkom_wedstrijden(db, instellingen=None):
    """Eigen thuiswedstrijden vandaag, voor de welkomstbanner/-popup op
    het prijzenscherm (instelling: zie kiosk_wedstrijddag_welkom_instellingen)
    -- lege lijst als de banner uitstaat of er niets gepland staat.
    Op tijd gesorteerd (onbekende tijd/"hele dag" achteraan) zodat de
    client precies weet in welke volgorde de wedstrijden vandaag
    plaatsvinden -- de client bepaalt met die volgorde en de eigen klok
    welk tijdvak nu actief is (zie werkWedstrijddagWelkomBij() in
    kiosk_prijzen_scherm.html), net als bij de bardienst-balk en om
    dezelfde reden: geen servertijdzone-afhankelijkheid."""
    instellingen = instellingen or _prijzen_instellingen(db)
    if not instellingen["wedstrijddag_welkom_actief"]:
        return []
    vandaag = vandaag_amsterdam().isoformat()
    wedstrijden = db.execute(
        """SELECT tijd, omschrijving FROM wedstrijden
           WHERE thuis = 1 AND afgelast = 0 AND datum = ?
           ORDER BY tijd IS NULL, tijd, team""",
        (vandaag,),
    ).fetchall()
    resultaat = []
    gezien = set()
    for w in wedstrijden:
        naam = bepaal_tegenstander(w["omschrijving"])
        if not naam or naam in gezien:
            continue
        gezien.add(naam)
        resultaat.append({"tijd": w["tijd"], "tegenstander": naam})
    return resultaat


def _eerstvolgende_bekende_tegenstander(db):
    """Voor de testknop bij de wedstrijddag-welkomstmelding (zie
    kiosk_wedstrijddag_welkom_testen) -- toont daar een echte naam i.p.v.
    het kale "Tegenstander"-placeholder, ook als er vandaag geen eigen
    thuiswedstrijd gepland staat (de test moet altijd werken, los van de
    instelling/datum, dus geen 'wedstrijddag_welkom_actief'-check zoals
    bij _wedstrijddag_welkom_wedstrijden hierboven). Pakt de eerste
    aankomende thuiswedstrijd waarvan de tegenstander uit de omschrijving
    te herleiden is; None als er niets (meer) gepland staat."""
    vandaag = vandaag_amsterdam().isoformat()
    wedstrijden = db.execute(
        """SELECT omschrijving FROM wedstrijden
           WHERE thuis = 1 AND afgelast = 0 AND datum >= ?
           ORDER BY datum, tijd IS NULL, tijd""",
        (vandaag,),
    ).fetchall()
    for w in wedstrijden:
        naam = bepaal_tegenstander(w["omschrijving"])
        if naam:
            return naam
    return None


def _categorie_kolommen_indeling(db, instellingen=None):
    """Leest de opgeslagen kolomindeling (zie kiosk_prijzen_instellingen.html,
    de sleep-interface) -- {"1": [...namen], "2": [...], "3": [...]}.
    Onherkenbare/kapotte inhoud (zou hier nooit moeten voorkomen, alleen
    via _categorie_kolommen_opslaan hieronder geschreven) valt terug op
    een lege indeling i.p.v. de pagina te laten crashen."""
    instellingen = instellingen or _prijzen_instellingen(db)
    ruw = instellingen["categorie_kolommen"]
    try:
        data = json.loads(ruw)
    except (TypeError, ValueError):
        data = {}
    return {
        kolom: [naam for naam in data.get(kolom, []) if isinstance(naam, str)]
        for kolom in ("1", "2", "3")
    }


def _alle_kiosk_categorie_namen(db):
    """Alle categorie-koppen die op het prijzenscherm voorkomen, voor de
    sleep-indeling."""
    return sorted({naam for naam, _ in _prijzen_categorieen(db)}, key=str.lower)


def _verdeel_namen_over_kolommen(namen, indeling):
    """Kern van de kolomindeling: verdeelt een lijst categorienamen over
    de 3 vaste kolommen volgens de opgeslagen (gesleepte) indeling. Een
    naam die er niet in voorkomt -- nieuw, of nog nooit gesleept --
    belandt achteraan in kolom 1, zodat 'ie zichtbaar blijft i.p.v. te
    verdwijnen totdat iemand 'm een plek geeft. Gebruikt voor zowel de
    sleep-interface (alleen namen, zie kiosk_prijzen_instellingen) als
    het prijzenscherm zelf (naam + producten, zie _verdeel_over_kolommen
    hieronder)."""
    beschikbaar = set(namen)
    geplaatst = set()
    kolommen = []
    for kolom in ("1", "2", "3"):
        lijst = [
            naam
            for naam in indeling.get(kolom, [])
            if naam in beschikbaar and naam not in geplaatst
        ]
        geplaatst.update(lijst)
        kolommen.append(lijst)
    for naam in namen:
        if naam not in geplaatst:
            kolommen[0].append(naam)
    return kolommen


def _verdeel_over_kolommen(categorieen, indeling):
    bij_naam = dict(categorieen)
    namen_per_kolom = _verdeel_namen_over_kolommen(
        [naam for naam, _ in categorieen], indeling
    )
    return [[(naam, bij_naam[naam]) for naam in namen] for namen in namen_per_kolom]


def _prijzen_sponsoren(db):
    """Sponsordia's voor de prijzenlijst (om de 'interval' seconden
    'duur' seconden over de prijzen heen), of None als dat uit staat of
    er geen sponsoren zijn."""
    instellingen = _scherm_instellingen(db)
    if not instellingen["sponsors_toon_prijzen"]:
        return None
    dias = bouw_sponsor_dias(db, instellingen)
    if not dias:
        return None
    return {
        "dias": dias,
        "interval": max(10, instellingen["sponsors_prijzen_interval"]),
        "duur": max(3, instellingen["sponsors_prijzen_duur"]),
    }


def _prijzen_versie(
    categorieen, acties, bardiensten, wedstrijden_vandaag, indeling, uitgelicht, *extra, sponsoren=None
):
    # Alleen de velden die daadwerkelijk op het scherm staan -- zo
    # triggert bijv. een gewijzigde voorraad (niet zichtbaar hier) geen
    # onnodige herlaadbeurt. Acties, de bardiensten van vandaag, de
    # thuiswedstrijden van vandaag, de kolomindeling en het uitgelichte
    # product tellen ook mee, zodat een wijziging daaraan het scherm net
    # als de rest vanzelf bijwerkt. *extra is puur om /kiosk/tv (zie
    # kiosk_tv) een eigen versie-'namespace' te geven, zodat het
    # wisselen tussen prijzen/dia's ook zonder inhoudelijke wijziging
    # als een update gezien wordt.
    return _versie(
        [
            (
                naam,
                [(p["id"], p["naam"], p["verkoopprijs"], p["kiosk_uitverkocht"]) for p in lijst],
            )
            for naam, lijst in categorieen
        ],
        [(a["id"], a["tekst"], a["product_naam"], a["verkoopprijs"], a["afbeelding"]) for a in acties],
        [(b["id"], b["datum"], b["start_tijd"], b["eind_tijd"], b["namen"]) for b in bardiensten],
        [(w["tijd"], w["tegenstander"]) for w in wedstrijden_vandaag],
        indeling,
        (
            uitgelicht["titel"],
            uitgelicht["product_id"],
            uitgelicht["naam"],
            uitgelicht["verkoopprijs"],
            uitgelicht["kiosk_uitverkocht"],
        )
        if uitgelicht
        else None,
        sponsoren,
        *extra,
    )


def _prijzen_render_kwargs(db, versie_url, extra_versie=None):
    """Gedeelde render-context voor zowel /kiosk/prijzen als de
    prijzen-stand van /kiosk/tv (zie kiosk_tv) -- 1 plek voor de opbouw
    zodat beide altijd exact hetzelfde renderen."""
    instellingen = _prijzen_instellingen(db)
    uitgelicht = _uitgelicht_product(db, instellingen)
    categorieen = _prijzen_categorieen(
        db, uitgelicht_product_id=uitgelicht["product_id"] if uitgelicht else None
    )
    acties = _acties_actief(db)
    bardiensten = _bardiensten_vandaag(db)
    wedstrijden_vandaag = _wedstrijddag_welkom_wedstrijden(db, instellingen)
    indeling = _categorie_kolommen_indeling(db, instellingen)
    acties_voor_scherm = [
        {
            "naam": a["product_naam"],
            "prijs": a["verkoopprijs"],
            "tekst": a["tekst"],
            "foto": a["afbeelding"],
        }
        for a in acties
    ]
    extra = (extra_versie,) if extra_versie else ()
    sponsoren = _prijzen_sponsoren(db)
    return {
        "sponsoren": sponsoren,
        "categorieen_kolommen": _verdeel_over_kolommen(categorieen, indeling),
        "acties": acties_voor_scherm,
        "uitgelicht": uitgelicht,
        "versie": _prijzen_versie(
            categorieen, acties, bardiensten, wedstrijden_vandaag, indeling, uitgelicht, *extra,
            sponsoren=sponsoren,
        ),
        "versie_url": versie_url,
        "uitverkocht_namen": _uitverkocht_namen(categorieen),
        "bardiensten_vandaag": _bardiensten_voor_scherm(bardiensten),
        "wedstrijden_vandaag": wedstrijden_vandaag,
        "wedstrijddag_welkom_tekst": instellingen["wedstrijddag_welkom_tekst"],
        "wedstrijddag_test": instellingen["wedstrijddag_test_teller"],
    }
