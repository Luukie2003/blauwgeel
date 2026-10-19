package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityProductBinding
import org.json.JSONObject
import kotlin.math.roundToInt

/** Eén product: de voorraad, boeken (erin of eruit), en daaronder alles van de productpagina van de site: kerncijfers,
 * verkoop per week en de verwachting, prijzen, inkoop en bestellen ("Op de bestellijst"), de laatste boekingen, de
 * artikelen met hun barcodes en de laatste tellingen. Het blok "Verkoop en verwachting" komt apart binnen, want het
 * voorspelmodel rekent op de server soms enkele seconden.
 *
 * Geopend door een scan staat het aantal al goed (een krat van 24: 24) en bij een doos of krat staat "Erin" al aan.
 * Nog een keer scannen van hetzelfde product telt erbij op: drie kratten scannen is 72. Een onbekende barcode scannen
 * op dit scherm vraagt of hij bij dit product hoort; dan is hij in één tik gekoppeld.
 *
 * Boeken gaat met een verzoek_id: valt de verbinding weg, dan probeert de app het vanzelf opnieuw, en de site boekt het
 * toch maar één keer (zie routes/app_api.py). */
class ProductActivity : BasisActivity() {

    private lateinit var b: ActivityProductBinding
    private var productId = 0
    private var product: Catalogus.Product? = null
    private var richting: String? = null
    private var aantal = 1
    private var aantalAangepast = false
    private var reden: String? = null
    private var verzoekId: String? = null
    private var boekt = false
    private var scans = 0
    /** Na de vraag bij een los gescand artikel: tellen volgende losse scans als volle doos (true) of als los (false). */
    private var losAlsVolle: Boolean? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityProductBinding.inflate(layoutInflater)
        setContentView(b.root)
        productId = intent.getIntExtra(EXTRA_ID, 0)
        product = Catalogus.opId(productId)
        richtBalkIn(b.balk, product?.naam ?: getString(R.string.product), sub = product?.let(::balkSub))

        b.erinKnop.setOnClickListener { kiesRichting("in") }
        b.eruitKnop.setOnClickListener { kiesRichting("uit") }
        b.minKnop.setOnClickListener { zetAantal(maxOf(1, aantal - 1)) }
        b.plusKnop.setOnClickListener { zetAantal(aantal + 1) }
        b.aantal.setOnClickListener {
            Cijferpad.vraag(this, getString(R.string.aantal), aantal.toString(), eenheid = product?.eenheid ?: "") {
                it.toIntOrNull()?.takeIf { n -> n > 0 }?.let(::zetAantal)
            }
        }
        b.boekKnop.setOnClickListener { boek() }
        b.koppelKnop.setOnClickListener { koppelKnop() }

        bouwRedenen()
        toonProduct()
        intent.getStringExtra(EXTRA_SCAN)?.let { gescand(it, eerste = true) }
        werkBoekKnopBij()
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laadDetail()
    }

    override fun weerVerbonden() = laadDetail()

    private fun balkSub(p: Catalogus.Product) = listOf(p.categorie, p.eenheid).filter { it.isNotEmpty() }.joinToString(" · ")

    // ---------------------------------------------------------------- tonen

    private fun toonProduct() {
        val p = product ?: return
        zetBalkTitel(p.naam)
        zetBalkSub(balkSub(p))
        Fotos.toon(b.productFoto, p.foto)
        b.voorraad.text = p.voorraadTekst()
        b.voorraad.setTextColor(getColor(if (p.laag || p.voorraad < 0) R.color.rood_balk else R.color.tekst))
        b.laagLabel.isVisible = p.laag || !p.actief
        b.laagLabel.text = getString(if (!p.actief) R.string.inactief else R.string.laag)
        b.laagLabel.setBackgroundResource(if (!p.actief) R.drawable.badge_grijs else R.drawable.badge_rood)
        if (b.voorraadSub.text.isNullOrEmpty()) b.voorraadSub.text = getString(R.string.minimum, p.minVoorraad)
        bouwSnelKnoppen(p)
        toonBarcodes(p)
        b.aantal.text = getString(R.string.aantal_eenheid, aantal, p.eenheid)
    }

    private fun bouwSnelKnoppen(p: Catalogus.Product) {
        b.snelKnoppen.removeAllViews()
        val stappen = mutableListOf<Pair<String, () -> Unit>>()
        if (p.besteleenheid != null && p.perBesteleenheid > 1) {
            stappen += getString(R.string.een_besteleenheid, p.besteleenheid, p.perBesteleenheid) to {
                zetAantal(if (aantalAangepast) aantal + p.perBesteleenheid else p.perBesteleenheid)
            }
        }
        for (n in listOf(5, 10)) stappen += "+$n" to { zetAantal(if (aantalAangepast) aantal + n else n) }
        for ((tekst, actie) in stappen) {
            val chip = LayoutInflater.from(this).inflate(R.layout.keuze, b.snelKnoppen, false) as TextView
            chip.text = tekst
            chip.setOnClickListener { actie() }
            b.snelKnoppen.addView(chip)
        }
    }

    private fun bouwRedenen() {
        b.redenen.removeAllViews()
        val keuzes = listOf<Pair<String?, String>>(null to getString(R.string.verkocht_of_verbruikt)) +
            Catalogus.dervingRedenen.map { (sleutel, tekst) -> sleutel to tekst.substringBefore(" (") }
        for ((sleutel, tekst) in keuzes) {
            val chip = LayoutInflater.from(this).inflate(R.layout.keuze, b.redenen, false) as TextView
            chip.text = tekst
            chip.isSelected = sleutel == reden
            chip.setOnClickListener {
                reden = sleutel
                for (i in 0 until b.redenen.childCount) b.redenen.getChildAt(i).isSelected = false
                chip.isSelected = true
                verzoekId = null
            }
            b.redenen.addView(chip)
        }
    }

    private fun toonBarcodes(p: Catalogus.Product) {
        b.barcodeLijst.removeAllViews()
        val artikelen = info?.optJSONArray("artikelen")?.objecten()
        if (!artikelen.isNullOrEmpty()) return toonArtikelen(p, artikelen)
        if (p.barcodes.isEmpty()) {
            b.barcodeLijst.addView(regel(getString(R.string.nog_geen_barcode), zacht = true))
        }
        for (code in p.barcodes) {
            val wat = if (code.isDoos) getString(R.string.doos_van, code.aantal, p.eenheid) else getString(R.string.los_aantal, code.aantal, p.eenheid)
            b.barcodeLijst.addView(regel("${code.code}  ·  $wat"))
        }
    }

    private fun regel(tekst: String, zacht: Boolean = false) = TextView(this).apply {
        text = tekst
        textSize = 13f
        setTextColor(getColor(if (zacht) R.color.tekst_zacht else R.color.tekst))
        setPadding(0, dp(this@ProductActivity, 5), 0, dp(this@ProductActivity, 5))
    }

    private fun laadDetail() {
        bezig {
            val detail = Api.getJson(this, "/api/app/producten/$productId")
            val nieuw = Catalogus.product(detail.getJSONObject("product"))
            Catalogus.werkBij(this, nieuw)
            product = nieuw
            info = detail.optJSONObject("info")
            val telling = detail.optJSONObject("laatste_telling")
            val inEenheden = info?.takeIf { !it.isNull("in_besteleenheden") && nieuw.voorraad > 0 }?.optDouble("in_besteleenheden")
            b.voorraadSub.text = listOfNotNull(
                getString(R.string.minimum, nieuw.minVoorraad),
                inEenheden?.let { "= ${Lijst.getal(it)} ${info?.optString("besteleenheid_naam")}" },
                telling?.let { getString(R.string.geteld_op, datum(it.optString("datum")), it.optInt("geteld_aantal")) },
            ).joinToString(" · ")
            toonProduct()
            info?.let(::toonInfo)
            toonMutaties(detail.optJSONArray("mutaties")?.objecten() ?: emptyList())
            if (!verkoopGevraagd) laadVerkoop()
        }
    }

    private fun toonMutaties(mutaties: List<JSONObject>) {
        b.mutaties.removeAllViews()
        if (mutaties.isEmpty()) b.mutaties.addView(regel(getString(R.string.nog_geen_boekingen), zacht = true))
        val eenheid = product?.eenheid ?: ""
        for (m in mutaties.take(6)) {
            val teken = if (m.optString("type") == "in") "+" else "−"
            val wat = m.tekstOfNull("reden") ?: m.tekstOfNull("opmerking")
            val tekst = "$teken${m.optInt("aantal")} $eenheid  ·  ${datum(m.optString("datum"), metTijd = true)}" +
                (m.tekstOfNull("naam")?.let { "  ·  $it" } ?: "") + (wat?.let { "\n$it" } ?: "")
            b.mutaties.addView(regel(tekst))
        }
        // Derving: wat er de laatste 90 dagen met een reden is afgeboekt (breuk, over de datum, ...).
        val derving = info?.optJSONObject("derving")
        if (derving != null && derving.optInt("aantal") > 0) {
            val waarde = derving.takeIf { !it.isNull("waarde") }?.optDouble("waarde")
            b.mutaties.addView(regel(
                getString(R.string.derving_regel, derving.optInt("dagen"), derving.optInt("aantal"), eenheid, derving.optInt("keer")) +
                    (waarde?.let { getString(R.string.derving_waarde, Lijst.euro(it)) } ?: ""),
                zacht = true,
            ))
        }
    }

    // ---------------------------------------------------------------- productinformatie (zoals op de site)

    private var info: JSONObject? = null
    private var verkoop: JSONObject? = null
    private var verkoopGevraagd = false
    private var verkoopBlok: LinearLayout? = null

    private fun toonInfo(i: JSONObject) {
        val p = product ?: return
        val eenheid = p.eenheid

        val kenmerken = mutableListOf<String>()
        if (i.optBoolean("gearchiveerd")) kenmerken += getString(R.string.gearchiveerd)
        if ((i.optJSONArray("onderweg")?.length() ?: 0) > 0) kenmerken += getString(R.string.besteld)
        val meldingen = i.optInt("meldingen")
        if (meldingen > 0) kenmerken += if (meldingen > 1) getString(R.string.gemeld_n, meldingen) else getString(R.string.gemeld)
        if (i.optBoolean("op_prijzenscherm")) {
            kenmerken += getString(if (i.optBoolean("uitverkocht_op_scherm")) R.string.op_prijzenscherm_uitverkocht else R.string.op_prijzenscherm)
        }
        if (i.optBoolean("niet_tellen")) kenmerken += getString(R.string.telt_niet_mee)
        b.kenmerken.text = kenmerken.joinToString(" · ")
        b.kenmerken.isVisible = kenmerken.isNotEmpty()
        b.productOpmerking.text = i.tekstOfNull("opmerking")
        b.productOpmerking.isVisible = i.tekstOfNull("opmerking") != null

        val boven = b.infoBoven
        boven.removeAllViews()

        // Kerncijfers
        Lijst.kop(boven, getString(R.string.in_het_kort))
        val cijfers = mutableListOf<Lijst.Cijfer>()
        val opties = i.optJSONArray("prijsopties")?.length() ?: 0
        if (!i.isNull("glazen_per_fust")) {
            cijfers += Lijst.Cijfer(Lijst.euro(i.optDouble("prijs_per_glas")),
                getString(R.string.per_glas_uitleg, i.optInt("glazen_per_fust"), Lijst.euro(i.optDouble("verkoop_stuk"))))
        } else {
            cijfers += Lijst.Cijfer(
                if (i.isNull("verkoopprijs")) "—" else Lijst.euro(i.optDouble("verkoopprijs")),
                getString(R.string.verkoopprijs_per, eenheid) + if (opties > 0) " · " + resources.getQuantityString(R.plurals.n_prijsopties, opties, opties) else "",
            )
        }
        i.optJSONObject("marge")?.let { m ->
            cijfers += if (m.has("pct")) {
                Lijst.Cijfer(
                    "${m.optDouble("pct").roundToInt()}%",
                    getString(R.string.marge_uitleg, Lijst.euro(m.optDouble("stuk")), eenheid,
                        getString(if (m.optBoolean("onder_doel")) R.string.onder else R.string.boven), m.optInt("doel")),
                    waarschuwing = m.optBoolean("onder_doel"),
                )
            } else {
                Lijst.Cijfer("—", getString(R.string.marge_reden, m.optString("reden")))
            }
        }
        val tellingen = i.optJSONArray("tellingen")?.objecten().orEmpty()
        val laatste = tellingen.firstOrNull()
        cijfers += if (laatste != null) {
            Lijst.Cijfer(
                (i.tekstOfNull("laatst_geteld") ?: "").replaceFirstChar { it.uppercase() },
                getString(R.string.laatst_geteld_uitleg, Lijst.datum(laatste.tekstOfNull("datum"), metTijd = false),
                    laatste.optInt("geteld"), laatste.optInt("verkocht")),
            )
        } else {
            Lijst.Cijfer("—", getString(R.string.nog_niet_geteld))
        }
        if (!i.isNull("voorraadwaarde")) {
            cijfers += Lijst.Cijfer(Lijst.euro(i.optDouble("voorraadwaarde")), getString(R.string.voorraadwaarde_uitleg))
        }
        Lijst.cijfers(boven, cijfers)

        // Verkoop en verwachting (komt apart binnen)
        Lijst.kop(boven, getString(R.string.verkoop_en_verwachting))
        verkoopBlok = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }.also { boven.addView(it) }
        toonVerkoop()

        // Prijzen
        Lijst.kop(boven, getString(R.string.prijzen))
        val prijzen = Lijst.kaart(boven).apply { setPadding(0, dp(this@ProductActivity, 4), 0, dp(this@ProductActivity, 4)) }
        if (!i.isNull("glazen_per_fust")) {
            Lijst.info(prijzen, getString(R.string.per_glas), Lijst.euro(i.optDouble("prijs_per_glas")),
                getString(R.string.glazen_per_fust_is, i.optInt("glazen_per_fust"), Lijst.euro(i.optDouble("verkoop_stuk"))))
        } else {
            Lijst.info(prijzen, getString(R.string.verkoopprijs),
                if (i.isNull("verkoopprijs")) getString(R.string.nog_niet_ingevuld) else Lijst.euro(i.optDouble("verkoopprijs")),
                getString(R.string.per_eenheid, eenheid))
        }
        i.optJSONArray("prijsopties")?.objecten()?.forEach { o ->
            Lijst.info(prijzen, o.optString("naam"), Lijst.euro(o.optDouble("prijs")),
                o.takeIf { !it.isNull("glazen") }?.let { getString(R.string.n_glazen, it.optInt("glazen")) })
        }
        if (!i.isNull("inkoop_stuk")) {
            val perEenheid = i.takeIf { !it.isNull("inkoop_besteleenheid") }?.let {
                " · " + getString(R.string.prijs_per, Lijst.euro(it.optDouble("inkoop_besteleenheid")), i.optString("besteleenheid_naam"))
            } ?: ""
            Lijst.info(prijzen, getString(R.string.inkoop), Lijst.euro(i.optDouble("inkoop_stuk")), getString(R.string.per_eenheid, eenheid) + perEenheid)
        }
        if (!i.isNull("voorraadwaarde")) {
            Lijst.info(prijzen, getString(R.string.voorraadwaarde), Lijst.euro(i.optDouble("voorraadwaarde")), getString(R.string.tegen_inkoopprijs))
        }
        val gepland = i.optJSONArray("gepland")?.objecten().orEmpty()
        if (gepland.isNotEmpty()) {
            Lijst.subkop(prijzen, getString(R.string.gepland))
            gepland.forEach { g ->
                Lijst.info(prijzen, getString(R.string.vanaf, Lijst.datum(g.tekstOfNull("datum"), metTijd = false)),
                    "${g.optString("wat")} ${Lijst.euro(g.optDouble("prijs"))}", g.tekstOfNull("opmerking"))
            }
        }
        val wijzigingen = i.optJSONArray("prijs_geschiedenis")?.objecten().orEmpty()
        if (wijzigingen.isNotEmpty()) {
            Lijst.subkop(prijzen, getString(R.string.laatste_prijswijzigingen))
            wijzigingen.forEach { w ->
                Lijst.info(prijzen, Lijst.datum(w.tekstOfNull("datum"), metTijd = false),
                    "${w.optString("wat")} ${Lijst.euro(w.optDouble("oud"))} → ${Lijst.euro(w.optDouble("nieuw"))}", w.tekstOfNull("naam"))
            }
        }

        // Inkoop en bestellen
        Lijst.kop(boven, getString(R.string.inkoop_en_bestellen))
        val inkoop = Lijst.kaart(boven).apply { setPadding(0, dp(this@ProductActivity, 4), 0, 0) }
        Lijst.info(inkoop, getString(R.string.leverancier_label), i.tekstOfNull("leverancier") ?: getString(R.string.niet_ingevuld),
            i.tekstOfNull("besteldagen")?.let { getString(R.string.bestellen_op, it) })
        val factor = i.optInt("factor", 1)
        Lijst.info(inkoop, getString(R.string.bestellen_per), i.optString("besteleenheid_naam"),
            listOfNotNull(
                if (factor > 1) getString(R.string.van_n_eenheid, factor, eenheid) else null,
                i.takeIf { !it.isNull("bestel_hoeveelheid") }?.let { getString(R.string.vaste_bestelling, it.optInt("bestel_hoeveelheid"), eenheid) },
            ).joinToString(" · ").ifEmpty { null })
        Lijst.info(inkoop, getString(R.string.minimum_kort), "${p.minVoorraad} $eenheid")
        val levering = i.optJSONObject("laatste_levering")
        Lijst.info(inkoop, getString(R.string.laatst_binnen),
            levering?.let { getString(R.string.n_op_datum, it.optInt("aantal"), eenheid, Lijst.datum(it.tekstOfNull("datum"), metTijd = false)) }
                ?: getString(R.string.nog_niets_ingeboekt),
            levering?.tekstOfNull("leeftijd"))
        val onderweg = i.optJSONArray("onderweg")?.objecten().orEmpty()
        if (onderweg.isNotEmpty()) {
            Lijst.subkop(inkoop, getString(R.string.onderweg_kop))
            onderweg.forEach { o ->
                Lijst.info(inkoop, getString(R.string.bestelling_nr, o.optInt("id")),
                    if (factor > 1) "${o.optInt("in_besteleenheden")} ${i.optString("besteleenheid_naam")} (${o.optInt("aantal")} $eenheid)"
                    else "${o.optInt("aantal")} $eenheid",
                    listOfNotNull(o.tekstOfNull("referentie"), getString(R.string.van_datum, Lijst.datum(o.tekstOfNull("datum"), metTijd = false))).joinToString(" · "))
            }
        }
        Lijst.knop(inkoop, if (meldingen > 0) getString(R.string.op_de_bestellijst_nog_eens) else getString(R.string.op_de_bestellijst)) { meld() }

        // Onder de barcodes: de laatste tellingen, en wat alleen op de computer kan.
        val onder = b.infoOnder
        onder.removeAllViews()
        Lijst.kop(onder, getString(R.string.laatste_tellingen))
        if (tellingen.isEmpty()) Lijst.leeg(onder, getString(R.string.nog_niet_geteld))
        else {
            val kaart = Lijst.kaart(onder)
            tellingen.forEach { t ->
                Lijst.regel(kaart, Lijst.datum(t.tekstOfNull("datum"), metTijd = false) + (t.tekstOfNull("naam")?.let { " · $it" } ?: ""),
                    getString(R.string.was_geteld, t.optInt("voor"), t.optInt("geteld"), eenheid) + " · " + Lijst.euro(t.optDouble("omzet")),
                    getString(R.string.verkocht_n, t.optInt("verkocht")), R.color.tekst) { TellingenActivity.open(this, t.getInt("id")) }
            }
        }
        val beheer = Lijst.kaart(onder)
        if (inst.beheerder) Lijst.knop(beheer, getString(R.string.product_bewerken)) { nietInApp(getString(R.string.wat_product_bewerken)) }
        Lijst.knop(beheer, getString(R.string.schaplabel_printen)) { nietInApp(getString(R.string.wat_schaplabel)) }
    }

    private fun laadVerkoop() {
        verkoopGevraagd = true
        bezig {
            try {
                verkoop = Api.getJson(this, "/api/app/producten/$productId/verkoop")
            } finally {
                if (verkoop == null) verkoop = JSONObject().put("mislukt", true)
                toonVerkoop()
            }
        }
    }

    private fun toonVerkoop() {
        val blok = verkoopBlok ?: return
        blok.removeAllViews()
        val v = verkoop
        val eenheid = product?.eenheid ?: ""
        if (v == null) return Lijst.leeg(blok, getString(R.string.even_rekenen))
        if (v.optBoolean("mislukt")) return Lijst.leeg(blok, getString(R.string.verkoop_mislukt))
        if (!v.optBoolean("beschikbaar")) return Lijst.leeg(blok, getString(R.string.verkoop_nog_geen_tellingen))

        val zonder = v.optInt("zonder_verkoop")
        if (zonder > 0) {
            Lijst.tekst(Lijst.kaart(blok, R.drawable.rand_links_oranje), getString(R.string.weken_niets_verkocht, zonder), kleur = R.color.tekst)
        }
        val w = v.optJSONObject("verwachting")
        val cijfers = mutableListOf<Lijst.Cijfer>()
        val gemiddeld = v.optInt("weken_gemiddeld")
        cijfers += Lijst.Cijfer(
            if (v.isNull("per_week")) "—" else Lijst.getal(v.optDouble("per_week")),
            getString(R.string.per_week_uitleg, gemiddeld) +
                (v.optDouble("omzet_recent").takeIf { it > 0 }?.let { "\n" + getString(R.string.samen_omzet, Lijst.euro(it).substringBefore(',')) } ?: ""),
            eenheid,
        )
        if (w != null) {
            cijfers += Lijst.Cijfer(
                w.optDouble("verwacht").roundToInt().toString(),
                getString(R.string.verwacht_komende_dagen, v.optInt("prognose_dagen", 7), w.optDouble("laag").roundToInt(), w.optDouble("hoog").roundToInt()),
                eenheid,
            )
            val kans = w.optDouble("kans_tekort")
            val onderweg = w.optInt("onderweg")
            val urgent = w.optString("status") == "urgent"
            cijfers += when {
                w.optBoolean("nu_op") -> Lijst.Cijfer(getString(R.string.op), getString(R.string.niets_meer_op_voorraad), waarschuwing = true)
                !w.isNull("dekking_dagen") -> {
                    val dagen = w.optDouble("dekking_dagen")
                    Lijst.Cijfer(
                        if (dagen < 100) dagen.roundToInt().toString() else "100+",
                        getString(R.string.zo_lang_voorraad) + "\n" +
                            (if (kans >= 0.05) getString(R.string.kans_opraken, (kans * 100).roundToInt()) else getString(R.string.raakt_niet_op)) +
                            (if (onderweg > 0) getString(R.string.met_besteld, onderweg, eenheid) else ""),
                        getString(R.string.dagen), waarschuwing = urgent,
                    )
                }
                else -> Lijst.Cijfer("—", getString(R.string.nauwelijks_verkocht))
            }
        }
        Lijst.cijfers(blok, cijfers)

        val kaart = Lijst.kaart(blok)
        if (w != null && w.optString("status") != "ok" && w.optInt("advies_stuks") > 0) {
            val stuks = w.optInt("advies_stuks")
            val advies = if (!w.isNull("advies_eenheden")) {
                getString(R.string.advies_eenheden, w.optInt("advies_eenheden"), w.tekstOfNull("besteleenheid") ?: getString(R.string.besteleenheid), stuks, eenheid)
            } else getString(R.string.advies_stuks, stuks, eenheid)
            Lijst.tekst(kaart, advies + listOfNotNull(
                if (w.optInt("onderweg") > 0) getString(R.string.al_besteld, w.optInt("onderweg"), eenheid) else null,
                if (w.optBoolean("al_op_bestellijst")) getString(R.string.staat_al_op_bestellijst) else null,
            ).joinToString("") { " $it" }, grootte = 14f, kleur = R.color.tekst, vet = true)
        }
        val weken = v.optJSONArray("weken")?.objecten().orEmpty()
        if (weken.isNotEmpty()) {
            Lijst.subkop(kaart, getString(R.string.verkocht_per_week))
            kaart.addView(WeekGrafiek(this).apply {
                setPadding(dp(context, 8), 0, dp(context, 8), 0)
                this.weken = weken.map { WeekGrafiek.Week(it.optInt("week"), it.optDouble("aantal"), it.optBoolean("nog_niet_af")) }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                marginStart = dp(this@ProductActivity, 8)
                marginEnd = dp(this@ProductActivity, 8)
            })
            val tot = v.tekstOfNull("geteld_tot")?.take(10)?.split("-")?.reversed()?.joinToString("-") ?: ""
            Lijst.tekst(kaart, getString(R.string.grafiek_uitleg, tot) +
                (if (w?.optBoolean("weinig_data") == true) " " + getString(R.string.nog_weinig_tellingen) else ""), grootte = 11f)
        }
        if (kaart.childCount == 0) blok.removeView(kaart)
    }

    /** "Op de bestellijst", net als de knop op de productpagina van de site. */
    private fun meld() {
        val id = Api.nieuwVerzoekId()
        bezig {
            val antwoord = Api.post(this, "/api/app/producten/$productId/melden", verzoekId = id)
            tril(60)
            melding(antwoord.optString("melding"))
            laadDetail()
        }
    }

    /** De artikelen van dit product met hun barcodes (zoals "Artikelen en barcodes" op de site). */
    private fun toonArtikelen(p: Catalogus.Product, artikelen: List<JSONObject>) {
        for (a in artikelen) {
            val naam = listOfNotNull(a.optString("naam"), a.tekstOfNull("merk")?.takeIf { !a.optString("naam").contains(it, ignoreCase = true) })
                .joinToString(" · ")
            b.barcodeLijst.addView(regel(naam).apply { setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(0, dp(context, 6), 0, 0) })
            val prijs = a.takeIf { !it.isNull("inkoopprijs") }?.let {
                " " + getString(R.string.voor_prijs, Lijst.euro(it.optDouble("inkoopprijs"))) +
                    (it.takeIf { x -> !x.isNull("per_eenheid") && x.optInt("aantal") > 1 }?.let { x -> " (${getString(R.string.prijs_per, Lijst.euro(x.optDouble("per_eenheid")), p.eenheid)})" } ?: "")
            } ?: ""
            val wat = getString(R.string.los_aantal, a.optInt("aantal"), p.eenheid) + prijs + (a.tekstOfNull("leverancier")?.let { " · $it" } ?: "")
            b.barcodeLijst.addView(regel(wat, zacht = true).apply { setPadding(0, 0, 0, 0) })
            val codes = listOfNotNull(
                a.tekstOfNull("ean"),
                a.tekstOfNull("doos_ean")?.let { getString(R.string.doos_code, a.optInt("per_doos"), it) },
            ).joinToString("  ·  ").ifEmpty { getString(R.string.geen_barcode) }
            b.barcodeLijst.addView(regel(codes).apply { typeface = android.graphics.Typeface.MONOSPACE; textSize = 12f; setPadding(0, 0, 0, dp(context, 6)) })
        }
    }

    /** "2026-10-18 14:02" → "18-10 14:02" (of alleen "18-10"). */
    private fun datum(tekst: String, metTijd: Boolean = false): String {
        if (tekst.length < 10) return tekst
        val dag = "${tekst.substring(8, 10)}-${tekst.substring(5, 7)}"
        return if (metTijd && tekst.length >= 16) "$dag ${tekst.substring(11, 16)}" else dag
    }

    // ---------------------------------------------------------------- boeken

    private fun kiesRichting(nieuw: String) {
        richting = nieuw
        b.erinKnop.isSelected = nieuw == "in"
        b.eruitKnop.isSelected = nieuw == "uit"
        b.redenenScroll.isVisible = nieuw == "uit"
        verzoekId = null
        werkBoekKnopBij()
    }

    private fun zetAantal(nieuw: Int) {
        aantal = nieuw.coerceIn(1, 99_999)
        aantalAangepast = true
        verzoekId = null
        b.aantal.text = getString(R.string.aantal_eenheid, aantal, product?.eenheid ?: "")
        werkBoekKnopBij()
    }

    private fun werkBoekKnopBij() {
        val eenheid = product?.eenheid ?: ""
        b.boekKnop.isEnabled = richting != null && !boekt
        b.boekKnop.alpha = if (b.boekKnop.isEnabled) 1f else 0.5f
        b.boekKnop.text = when {
            boekt -> getString(R.string.bezig_met_boeken)
            richting == "in" -> getString(R.string.boek_erin, aantal, eenheid)
            richting == "uit" -> getString(R.string.boek_eruit, aantal, eenheid)
            else -> getString(R.string.kies_erin_of_eruit)
        }
    }

    private fun boek() {
        val r = richting ?: return
        if (boekt) return
        // Hetzelfde verzoek_id bij nog een keer proberen na een fout: dan boekt de site het nooit dubbel.
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        boekt = true
        werkBoekKnopBij()
        bezig {
            try {
                val body = JSONObject().put("type", r).put("aantal", aantal)
                if (r == "uit" && reden != null) body.put("reden", reden)
                val antwoord = Api.post(this, "/api/app/producten/$productId/boeken", body, verzoekId = id)
                val nieuw = Catalogus.product(antwoord.getJSONObject("product"))
                Catalogus.werkBij(this, nieuw)
                product = nieuw
                tril(60)
                melding(antwoord.optString("melding"))
                antwoord.tekstOfNull("waarschuwing")?.let {
                    AlertDialog.Builder(this).setMessage(it).setPositiveButton(R.string.ok, null).show()
                }
                // Klaar voor de volgende boeking.
                verzoekId = null
                richting = null
                reden = null
                aantal = 1
                aantalAangepast = false
                scans = 0
                losAlsVolle = null
                b.erinKnop.isSelected = false
                b.eruitKnop.isSelected = false
                b.redenenScroll.isVisible = false
                b.scanMelding.isVisible = false
                bouwRedenen()
                toonProduct()
                laadDetail()
            } finally {
                boekt = false
                werkBoekKnopBij()
            }
        }
    }

    // ---------------------------------------------------------------- scannen en koppelen

    override fun bijScan(code: String) {
        val treffer = Catalogus.opBarcode(code)
        when {
            treffer != null && treffer.product.id == productId -> gescand(treffer.barcode.code, eerste = false)
            treffer != null -> {
                ProductActivity.open(this, treffer.product.id, scan = treffer.barcode.code)
                finish()
            }
            Catalogus.normaliseerCode(code)?.length in setOf(8, 13, 14) -> vraagKoppelen(code)
            else -> openScan(code)
        }
    }

    /** Een barcode van dit product is gescand: het aantal erbij (de eerste keer: precies dat aantal). Is het een losse
     * verpakking terwijl er een doos of krat van bestaat, dan eerst de vraag of je de volle besteleenheid wilt
     * inboeken; dat antwoord geldt daarna ook voor de volgende losse scans op dit scherm. */
    private fun gescand(code: String, eerste: Boolean) {
        val p = product ?: return
        val barcode = p.barcodes.firstOrNull { it.code == Catalogus.normaliseerCode(code) } ?: return
        tril()
        val volle = p.volleEenheid(barcode)
        if (!barcode.isDoos && volle != null && losAlsVolle == null) {
            val doos = p.besteleenheid ?: getString(R.string.doos)
            AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.los_gescand_titel)))
                .setMessage(getString(R.string.los_gescand_vraag, getString(R.string.los_aantal, barcode.aantal, p.eenheid), barcode.artikel))
                .setPositiveButton(getString(R.string.los_gescand_vol, doos, volle, p.eenheid)) { _, _ ->
                    losAlsVolle = true
                    telOp(volle, eerste, getString(R.string.doos_van, volle, p.eenheid), barcode.artikel)
                    if (richting == null) kiesRichting("in")
                }
                .setNegativeButton(getString(R.string.los_gescand_los, barcode.aantal, p.eenheid)) { _, _ ->
                    losAlsVolle = false
                    telOp(barcode.aantal, eerste, getString(R.string.los_aantal, barcode.aantal, p.eenheid), barcode.artikel)
                }
                .show()
            return
        }
        val stap = if (!barcode.isDoos && losAlsVolle == true && volle != null) volle else barcode.aantal
        val wat = if (barcode.isDoos || stap != barcode.aantal) getString(R.string.doos_van, stap, p.eenheid)
        else getString(R.string.los_aantal, barcode.aantal, p.eenheid)
        telOp(stap, eerste, wat, barcode.artikel)
        if (barcode.isDoos && richting == null) kiesRichting("in")
    }

    private fun telOp(stap: Int, eerste: Boolean, wat: String, artikel: String) {
        scans = if (eerste) 1 else scans + 1
        zetAantal(if (eerste || !aantalAangepast) stap else aantal + stap)
        b.scanMelding.text = if (scans > 1) getString(R.string.n_keer_gescand, scans, wat, artikel) else getString(R.string.gescand, wat, artikel)
        b.scanMelding.isVisible = true
    }

    private fun koppelKnop() {
        if (Scanner.isAanwezig(this)) {
            Scanner.startScan(this)
            melding(getString(R.string.scan_de_barcode))
        } else {
            Cijferpad.vraag(this, getString(R.string.barcode_intikken), max = 14) { code ->
                if (code.isNotEmpty()) bijScan(code)
            }
        }
    }

    /** Onbekende barcode op dit scherm: hoort hij bij dit product? Eén tik en hij is gekoppeld. */
    private fun vraagKoppelen(code: String) {
        val p = product ?: return
        Koppelvraag.vraag(
            this, code, p, getString(R.string.onbekende_barcode_bij, Catalogus.normaliseerCode(code), p.naam),
            anderProduct = { KoppelenActivity.open(this, code) },
        ) { nieuw ->
            product = nieuw
            toonProduct()
            gescand(code, eerste = !aantalAangepast)
        }
    }

    companion object {
        private const val EXTRA_ID = "product_id"
        private const val EXTRA_SCAN = "scan"

        fun open(activity: Activity, productId: Int, scan: String? = null) {
            activity.startActivity(Intent(activity, ProductActivity::class.java).putExtra(EXTRA_ID, productId).putExtra(EXTRA_SCAN, scan))
        }
    }
}
