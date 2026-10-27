package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De bestellijst: hier loop je de bestelling na en zet je hem klaar, zoals met de handterminal van de supermarkt.
 * Bovenaan wat besteld moet worden (onder het minimum, met het advies van de prognose; wat bij een vorige bestelling
 * niet geleverd is; wat iemand bij het product zelf koos), daaronder wat je erbij scant of zoekt, en wat kan opraken
 * (nog op 0). Tik op een product: er schuift een blad omhoog (zie [Blad]) met het aantal colli, − en +, en Bevestigen;
 * dan krijgt de regel een vinkje. Dat wordt meteen op de site bewaard (api_app_bestellijst_controleren), dus na
 * uitloggen staat het er nog. "Klaarzetten" neemt alleen wat gecontroleerd is, maakt een bestelling per leverancier (die
 * staan dan bij Factuur inboeken) en opent het overzicht om bij de leverancier te bestellen ([BesteloverzichtActivity]).
 * Daaronder wat er gemeld is en wat onderweg is (tik voor het overzicht). De prognose rekent soms enkele seconden en
 * komt er apart bij. */
class BestellijstActivity : BasisActivity() {

    private enum class Soort { LAAG, MANCO, GEKOZEN, ERBIJ, OPRAKEN }

    /** Een product op de lijst. [soort]: LAAG (onder het minimum), MANCO (niet geleverd), GEKOZEN (bij het product zelf
     * gekozen, of eerder erbij gezet en bevestigd), ERBIJ (nu gescand of gezocht), OPRAKEN (kan opraken, nog op 0).
     * [aantal] in colli. [vast]: iemand koos of bevestigde het aantal, dus de prognose verandert het niet meer. */
    private class Regel(val p: JSONObject, val soort: Soort, var aantal: Int, var gecontroleerd: Boolean = false, var vast: Boolean = false) {
        val id get() = p.getInt("id")
    }

    private lateinit var b: ActivityLijstBinding
    private var data: JSONObject? = null
    private var prognose: JSONObject? = null
    private val regels = mutableListOf<Regel>()
    private var geladen = false
    /** Een scan van voordat de lijst er was (of waarmee een ander scherm de bestellijst opende). */
    private var wachtendeScan: String? = null
    private var verzoekId: String? = null
    /** Het blad dat nu open is: voor welk product, en wat nog een scan van dat product doet (één colli meer). */
    private var openBlad: Blad.Open? = null
    private var openId: Int? = null
    private var bladMeer: (() -> Unit)? = null

    private val kiezen = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val id = r.data?.getIntExtra(ProductenActivity.EXTRA_PRODUCT, -1) ?: -1
        if (r.resultCode == RESULT_OK && id > 0) voegToe(id)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.bestellijst))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = true
        b.onderKnop.setOnClickListener { klaarzetten() }
        wachtendeScan = intent.getStringExtra(EXTRA_SCAN)
        werkKnopBij()
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                val nieuw = Api.getJson(this, "/api/app/bestellijst")
                data = nieuw
                bouwRegels(nieuw)
                geladen = true
                toon()
            } finally {
                b.verversen.isRefreshing = false
            }
            wachtendeScan?.let {
                wachtendeScan = null
                bijScan(it)
            }
            val pr = Api.getJson(this, "/api/app/bestellijst/prognose")
            prognose = pr
            pasPrognoseToe(pr)
            toon()
        }
    }

    /** De regels uit de bestellijst van de site; wat hier gescand of gezocht is en nog niet bevestigd, blijft erbij. */
    private fun bouwRegels(data: JSONObject) {
        val nieuw = mutableListOf<Regel>()
        fun voeg(p: JSONObject, soort: Soort, standaard: Int) {
            if (nieuw.any { it.id == p.getInt("id") }) return
            val gekozen = if (p.has("gekozen") && !p.isNull("gekozen")) p.optInt("gekozen") else null
            nieuw += Regel(p, soort, gekozen ?: standaard, p.optBoolean("gecontroleerd"), vast = gekozen != null)
        }
        data.getJSONArray("bestellen").objecten().forEach { voeg(it, Soort.LAAG, basis(it)) }
        data.optJSONArray("manco")?.objecten()?.forEach { voeg(it, Soort.MANCO, it.optInt("tekort_besteleenheden")) }
        data.optJSONArray("gekozen")?.objecten()?.forEach { voeg(it, Soort.GEKOZEN, 0) }
        regels.filter { it.soort == Soort.ERBIJ && !it.gecontroleerd && nieuw.none { n -> n.id == it.id } }.forEach { nieuw += it }
        // Wat kan opraken komt uit de prognose: die van de vorige keer blijft staan tot de nieuwe er is.
        regels.filter { it.soort == Soort.OPRAKEN && nieuw.none { n -> n.id == it.id } }.forEach { nieuw += it }
        regels.clear()
        regels += nieuw
        prognose?.let { pasPrognoseToe(it) }
    }

    /** Het advies van de prognose bij elk product, en wat kan opraken (nog op 0). */
    private fun pasPrognoseToe(pr: JSONObject) {
        val advies = pr.optJSONObject("producten")
        for (r in regels) {
            val x = advies?.optJSONObject(r.id.toString()) ?: continue
            r.p.put("advies", x.optInt("advies_eenheden")).put("verwacht", x.optInt("verwacht")).put("dagen", x.optInt("dagen"))
            // Hoger als de prognose meer vraagt dan het minimum; wat iemand zelf koos of bevestigde, blijft.
            if (r.soort == Soort.LAAG && !r.vast && x.optInt("advies_eenheden") > r.aantal) r.aantal = x.optInt("advies_eenheden")
        }
        regels.removeAll { it.soort == Soort.OPRAKEN && !it.gecontroleerd }
        val al = regels.map { it.id }.toSet()
        pr.optJSONArray("extra")?.objecten()?.filter { it.getInt("id") !in al }?.forEach {
            it.put("advies", it.optInt("advies_eenheden"))
            regels += Regel(it, Soort.OPRAKEN, 0)
        }
    }

    /** Het gewone voorstel: de vaste bestelhoeveelheid, of tot het minimum, in hele besteleenheden. */
    private fun basis(p: JSONObject): Int {
        val tekort = if (p.optInt("bestel_hoeveelheid") > 0) p.optInt("bestel_hoeveelheid") else p.optInt("min_voorraad") - p.optInt("voorraad")
        return maxOf(1, (tekort + factor(p) - 1) / factor(p))
    }

    /** Wat er staat als het aantal weer het advies volgt. */
    private fun standaard(r: Regel) = when (r.soort) {
        Soort.LAAG -> maxOf(basis(r.p), r.p.optInt("advies"))
        Soort.MANCO -> r.p.optInt("tekort_besteleenheden")
        else -> 0
    }

    private fun factor(p: JSONObject) = maxOf(1, p.optInt("per_besteleenheid", p.optInt("factor", 1)))

    private fun colli(p: JSONObject) = p.tekstOfNull("besteleenheid") ?: p.optString("eenheid")

    private fun leverancier(r: Regel) = r.p.tekstOfNull("leverancier") ?: Catalogus.opId(r.id)?.leverancier

    /** Telt mee bij "x van y gecontroleerd": alles behalve wat kan opraken en nog op 0 staat. */
    private fun telt(r: Regel) = r.soort != Soort.OPRAKEN || r.gecontroleerd || r.aantal > 0

    // ---------------------------------------------------------------- de lijst

    private fun toon() {
        val data = data ?: return
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        Lijst.kaart(inhoud, R.drawable.melding_info).let { Lijst.tekst(it, getString(R.string.bestellijst_uitleg), kleur = R.color.tekst) }

        val teBestellen = regels.filter { it.soort == Soort.LAAG || it.soort == Soort.MANCO || it.soort == Soort.GEKOZEN }
        Lijst.kop(inhoud, getString(R.string.te_bestellen_kop, teBestellen.size))
        if (teBestellen.isEmpty()) Lijst.leeg(inhoud, getString(R.string.niets_bestellen))
        else Lijst.kaart(inhoud).let { kaart -> teBestellen.forEach { regel(kaart, it) } }

        Lijst.kop(inhoud, getString(R.string.erbij_kop))
        Lijst.kaart(inhoud).let { kaart ->
            regels.filter { it.soort == Soort.ERBIJ }.forEach { regel(kaart, it) }
            Lijst.knop(kaart, getString(R.string.product_zoeken)) { kiezen.launch(ProductenActivity.kiesIntent(this)) }
        }

        val opraken = regels.filter { it.soort == Soort.OPRAKEN }
        if (opraken.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.kan_opraken))
            Lijst.kaart(inhoud, R.drawable.rand_links_oranje).let { kaart -> opraken.forEach { regel(kaart, it) } }
        }

        val gemeld = data.getJSONArray("gemeld").objecten()
        val teksten = data.getJSONArray("teksten").objecten()
        if (gemeld.isNotEmpty() || teksten.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.gemeld_kop))
            val kaart = Lijst.kaart(inhoud)
            for (p in gemeld) {
                Lijst.regel(kaart, p.optString("naam"), getString(R.string.gemeld_detail, Lijst.datum(p.tekstOfNull("laatste_melding"))),
                    getString(R.string.n_keer, p.optInt("keer")), R.color.oranje_balk) {
                    AlertDialog.Builder(this)
                        .setTitle(p.optString("naam"))
                        .setMessage(R.string.melding_afhandelen_vraag)
                        .setPositiveButton(R.string.afhandelen) { _, _ ->
                            bezig {
                                this@BestellijstActivity.data = Api.post(this, "/api/app/bestellijst/gemeld/${p.getInt("id")}/afhandelen", herhaalbaar = true)
                                toon()
                            }
                        }
                        .setNeutralButton(R.string.naar_product) { _, _ -> ProductActivity.open(this, p.getInt("id")) }
                        .setNegativeButton(R.string.annuleren, null)
                        .show()
                }
            }
            for (t in teksten) Lijst.regel(kaart, t.optString("tekst"), Lijst.datum(t.tekstOfNull("aangemaakt_op")))
        }

        val onderweg = data.getJSONArray("onderweg").objecten()
        if (onderweg.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.onderweg_kop))
            val kaart = Lijst.kaart(inhoud)
            for (best in onderweg) {
                val nr = best.tekstOfNull("referentie") ?: getString(R.string.bestelling_nr, best.getInt("id"))
                Lijst.regel(
                    kaart,
                    listOfNotNull(best.tekstOfNull("leverancier"), nr).joinToString(" · "),
                    best.getJSONArray("regels").objecten().joinToString(", ") { "${it.optInt("aantal")} ${it.optString("eenheid")} ${it.optString("product")}" },
                    Lijst.datum(best.tekstOfNull("aangemaakt_op"), metTijd = false),
                    R.color.tekst_zacht,
                ) { BesteloverzichtActivity.open(this, intArrayOf(best.getInt("id"))) }
            }
        }
        werkKnopBij()
    }

    /** Een product op de lijst: links het vinkje (of een leeg rondje), rechts het aantal colli. */
    private fun regel(kaart: LinearLayout, r: Regel) {
        val p = r.p
        val detail = listOfNotNull(
            if (r.gecontroleerd) p.tekstOfNull("gekozen_door")?.let { getString(R.string.gecontroleerd_door, it) } ?: getString(R.string.gecontroleerd) else null,
            when (r.soort) {
                Soort.MANCO -> getString(R.string.niet_geleverd_detail, p.optInt("tekort_besteleenheden"), colli(p))
                Soort.GEKOZEN -> if (r.gecontroleerd) null else p.tekstOfNull("gekozen_door")?.let { getString(R.string.zelf_gekozen_door, it) }
                Soort.OPRAKEN -> getString(R.string.kans_n, Math.round(p.optDouble("kans_tekort") * 100).toInt())
                else -> null
            },
            getString(R.string.voorraad_min, p.optInt("voorraad"), p.optInt("min_voorraad"), p.optString("eenheid")),
            when {
                p.has("advies") -> getString(R.string.advies_n, p.optInt("advies"), colli(p))
                prognose == null && r.soort == Soort.LAAG -> getString(R.string.prognose_bezig)
                else -> null
            },
        ).joinToString(" · ")
        val rechts = when {
            r.aantal > 0 -> getString(R.string.n_eenheid, r.aantal, colli(p))
            r.gecontroleerd -> getString(R.string.niet)
            else -> "–"
        }
        Lijst.regel(
            kaart, p.optString("naam"), detail, rechts,
            when {
                r.gecontroleerd -> R.color.navy
                r.aantal > 0 -> R.color.tekst
                else -> R.color.tekst_zacht
            },
            icoon = if (r.gecontroleerd) R.drawable.ic_gecontroleerd else R.drawable.ic_te_controleren,
        ) { openBladVoor(r) }
    }

    // ---------------------------------------------------------------- het blad: −, + en Bevestigen

    /** Het blad van een product: wat de prognose zegt, het aantal colli met − en + (tik op het getal om het in te
     * vullen) en Bevestigen. Wat kan opraken begint op het advies. */
    private fun openBladVoor(r: Regel) {
        openBlad?.sluit()
        val p = r.p
        val colli = colli(p)
        val factor = factor(p)
        val eenheid = p.optString("eenheid")
        var n = if (r.soort == Soort.OPRAKEN && !r.gecontroleerd && r.aantal == 0) p.optInt("advies") else r.aantal
        val sub = listOfNotNull(
            getString(R.string.voorraad_kort, p.optInt("voorraad"), eenheid),
            getString(R.string.minimum, p.optInt("min_voorraad")),
            p.optInt("onderweg").takeIf { it > 0 }?.let { getString(R.string.n_onderweg, it) },
        ).joinToString(" · ")
        var dit: Blad.Open? = null
        val bijDicht = {
            if (openBlad === dit) {
                openBlad = null
                openId = null
                bladMeer = null
            }
        }
        val blad = Blad.toon(this, p.optString("naam"), sub, R.drawable.ic_bestellijst, bijDicht) { inhoud, blad ->
            val uitleg = listOfNotNull(
                when (r.soort) {
                    Soort.MANCO -> getString(R.string.niet_geleverd_detail, p.optInt("tekort_besteleenheden"), colli)
                    Soort.OPRAKEN -> getString(R.string.kans_n, Math.round(p.optDouble("kans_tekort") * 100).toInt())
                    else -> null
                },
                if (p.has("verwacht") && p.has("dagen")) getString(R.string.prognose_in_dagen, p.optInt("verwacht"), eenheid, p.optInt("dagen")) else null,
                if (p.has("advies")) getString(R.string.advies_n, p.optInt("advies"), colli) else null,
            ).joinToString(" · ")
            if (uitleg.isNotEmpty()) inhoud.addView(TextView(this).apply {
                text = uitleg
                textSize = 13f
                gravity = Gravity.CENTER
                setTextColor(getColor(R.color.tekst_zacht))
                setPadding(dp(this@BestellijstActivity, 8), dp(this@BestellijstActivity, 2), dp(this@BestellijstActivity, 8), dp(this@BestellijstActivity, 8))
            })

            // − [aantal colli] +
            val rij = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(this@BestellijstActivity, 8), 0, dp(this@BestellijstActivity, 8), 0)
            }
            val getal = TextView(this).apply {
                textSize = 26f
                gravity = Gravity.CENTER
                setTextColor(getColor(R.color.navy))
                setTypeface(typeface, Typeface.BOLD)
            }
            val stuks = TextView(this).apply {
                textSize = 12f
                gravity = Gravity.CENTER
                setTextColor(getColor(R.color.tekst_zacht))
            }
            val min = ImageButton(this)
            val plus = ImageButton(this)
            fun zet(nieuw: Int) {
                n = nieuw.coerceIn(0, 999)
                getal.text = if (n > 0) getString(R.string.n_eenheid, n, colli) else getString(R.string.niet_bestellen)
                stuks.text = if (n > 0 && factor > 1) getString(R.string.is_n_stuks, n * factor, eenheid) else " "
                min.isEnabled = n > 0
                min.alpha = if (n > 0) 1f else 0.35f
            }
            fun knop(k: ImageButton, icoon: Int, beschrijving: String, stap: Int) = k.apply {
                setImageResource(icoon)
                setColorFilter(getColor(R.color.navy))
                contentDescription = beschrijving
                setBackgroundResource(R.drawable.toets_licht)
                setOnClickListener {
                    tril(15)
                    zet(n + stap)
                }
            }
            val maat = dp(this, 60)
            rij.addView(knop(min, R.drawable.ic_min, getString(R.string.een_minder, colli), -1), LinearLayout.LayoutParams(maat, maat))
            val midden = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setBackgroundResource(R.drawable.regel_klik_kaart)
                setPadding(0, dp(this@BestellijstActivity, 6), 0, dp(this@BestellijstActivity, 6))
                setOnClickListener {
                    Cijferpad.vraag(this@BestellijstActivity, getString(R.string.hoeveel_bestellen, p.optString("naam")), n.toString(),
                        eenheid = colli, max = 3) { tekst -> tekst.toIntOrNull()?.let { zet(it) } }
                }
            }
            midden.addView(getal)
            midden.addView(stuks)
            rij.addView(midden, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = dp(this@BestellijstActivity, 8)
                marginEnd = dp(this@BestellijstActivity, 8)
            })
            rij.addView(knop(plus, R.drawable.ic_plus, getString(R.string.een_meer, colli), 1), LinearLayout.LayoutParams(maat, maat))
            inhoud.addView(rij)
            zet(n)
            bladMeer = {
                tril(15)
                zet(n + 1)
            }

            val bevestig = Button(this).apply {
                text = getString(R.string.bevestigen)
                textSize = 17f
                isAllCaps = false
                stateListAnimator = null
                setTypeface(typeface, Typeface.BOLD)
                setTextColor(getColor(R.color.navy))
                setBackgroundResource(R.drawable.knop_geel)
                setOnClickListener { bewaar(r.id, n, blad, this) }
            }
            inhoud.addView(bevestig, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(this, 52)).apply {
                topMargin = dp(this@BestellijstActivity, 14)
                marginStart = dp(this@BestellijstActivity, 6)
                marginEnd = dp(this@BestellijstActivity, 6)
            })

            // Daaronder: niet bestellen, terug naar het advies (of weghalen) en de productinformatie.
            val onder = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, dp(this@BestellijstActivity, 8), 0, 0)
            }
            fun link(tekst: String, actie: () -> Unit) = onder.addView(TextView(this).apply {
                text = tekst
                textSize = 13.5f
                gravity = Gravity.CENTER
                minHeight = dp(this@BestellijstActivity, 44)
                setTextColor(getColor(R.color.navy))
                setTypeface(typeface, Typeface.BOLD)
                setBackgroundResource(R.drawable.regel_klik)
                setOnClickListener { actie() }
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            link(getString(R.string.niet_bestellen)) { bewaar(r.id, 0, blad, bevestig) }
            if (r.soort == Soort.ERBIJ || r.soort == Soort.GEKOZEN) link(getString(R.string.weghalen)) { bewaar(r.id, null, blad, bevestig) }
            else if (r.gecontroleerd || r.vast) link(getString(R.string.terug_naar_advies)) { bewaar(r.id, null, blad, bevestig) }
            link(getString(R.string.productinfo)) {
                blad.sluit()
                ProductActivity.open(this, r.id)
            }
            inhoud.addView(onder)
        }
        dit = blad
        openBlad = blad
        openId = r.id
    }

    /** Bevestigd: zoveel colli (0 = niet bestellen), gecontroleerd, meteen op de site bewaard. [eenheden] null: weer het
     * advies (of weghalen, bij wat erbij gezet is). Het blad gaat pas dicht als het bewaard is. */
    private fun bewaar(id: Int, eenheden: Int?, blad: Blad.Open, knop: Button) {
        knop.isEnabled = false
        bezig {
            try {
                // Herhaalbaar: het zet een stand, twee keer is hetzelfde als één keer.
                val antwoord = Api.post(this, "/api/app/bestellijst/controleren",
                    JSONObject().put("product_id", id).put("eenheden", eenheden ?: JSONObject.NULL), herhaalbaar = true)
                regels.firstOrNull { it.id == id }?.let { r ->
                    when {
                        eenheden != null -> {
                            r.aantal = eenheden
                            r.gecontroleerd = true
                            r.vast = true
                        }
                        r.soort == Soort.ERBIJ || r.soort == Soort.GEKOZEN -> regels.remove(r)
                        else -> {
                            r.gecontroleerd = false
                            r.vast = false
                            r.aantal = standaard(r)
                        }
                    }
                    r.p.put("gekozen_door", antwoord.opt("gekozen_door") ?: JSONObject.NULL)
                }
                verzoekId = null
                tril(30)
                blad.sluit()
                toon()
            } finally {
                knop.isEnabled = true
            }
        }
    }

    // ---------------------------------------------------------------- scannen en zoeken

    /** Een product scannen (barcode, ook van de doos, of de QR-code van een schaplabel): is zijn blad al open, dan één
     * colli meer; staat het op de lijst, dan zijn blad; anders komt het bij Erbij, met het blad meteen open. De
     * QR-code van een verbruiksvoorwerp vraagt of het op de bestellijst moet (zie BasisActivity). */
    override fun bijScan(code: String) {
        if (!geladen) {
            tril()
            wachtendeScan = code
            return
        }
        if (Uri.parse(code).path?.startsWith("/scan/verbruiksvoorwerp/") == true) return openScan(code)
        tril()
        val id = Regex("/(?:scan|producten)/(\\d+)").find(code)?.groupValues?.get(1)?.toIntOrNull()
            ?: Catalogus.opBarcode(code)?.product?.id
        if (id != null) return gescand(id)
        if (Catalogus.normaliseerCode(code) == null) return melding(getString(R.string.scan_geen_barcode, code))
        // Onbekend op het toestel: misschien net op een ander toestel gekoppeld. Eerst de lijst verversen.
        bezig {
            try {
                Catalogus.ververs(this)
            } catch (e: Api.Fout) {
                // Geen verbinding: dan met wat we hebben.
            }
            val treffer = Catalogus.opBarcode(code)
            if (treffer != null) gescand(treffer.product.id) else melding(getString(R.string.barcode_onbekend_bestellen, code), lang = true)
        }
    }

    private fun gescand(id: Int) {
        if (openId == id) bladMeer?.invoke() else voegToe(id)
    }

    /** Een product erbij (gescand of gezocht): onderaan bij Erbij, met 1 colli en het blad meteen open. Niet uit de
     * keuken: die koopt zelf in (de boodschappenlijst). */
    private fun voegToe(id: Int) {
        regels.firstOrNull { it.id == id }?.let { return openBladVoor(it) }
        val c = Catalogus.opId(id) ?: return melding(getString(R.string.product_niet_gevonden))
        if (c.categorie.equals("Keuken", ignoreCase = true)) return melding(getString(R.string.keuken_niet_op_bestellijst), lang = true)
        val p = JSONObject()
            .put("id", c.id).put("naam", c.naam).put("eenheid", c.eenheid)
            .put("voorraad", c.voorraad).put("min_voorraad", c.minVoorraad)
            .put("besteleenheid", if (c.perBesteleenheid > 1) c.besteleenheid else JSONObject.NULL)
            .put("per_besteleenheid", c.perBesteleenheid)
            .put("leverancier", c.leverancier ?: JSONObject.NULL)
        val r = Regel(p, Soort.ERBIJ, 1)
        regels += r
        toon()
        openBladVoor(r)
    }

    // ---------------------------------------------------------------- klaarzetten

    private fun werkKnopBij() {
        val tellen = regels.filter { telt(it) }
        b.onderKnop.text = if (tellen.isEmpty()) getString(R.string.klaarzetten)
            else getString(R.string.klaarzetten_gecontroleerd, tellen.count { it.gecontroleerd }, tellen.size)
        b.onderKnop.alpha = if (regels.any { it.gecontroleerd && it.aantal > 0 }) 1f else 0.6f
    }

    /** Alleen wat gecontroleerd is (en niet op 0 staat), een bestelling per leverancier. Wat nog niet gecontroleerd is,
     * gaat niet mee; dat staat erbij in de vraag. */
    private fun klaarzetten() {
        val mee = regels.filter { it.gecontroleerd && it.aantal > 0 }
        if (mee.isEmpty()) return melding(getString(R.string.eerst_bevestigen), lang = true)
        val open = regels.filter { telt(it) && !it.gecontroleerd }
        val perLeverancier = mee.groupBy { leverancier(it) }.entries
            .sortedWith(compareBy({ it.key == null }, { it.key?.lowercase() }))
        var tekst = perLeverancier.joinToString("\n\n") { (lev, groep) ->
            (lev ?: getString(R.string.zonder_leverancier)) + ":\n" +
                groep.joinToString("\n") { "${it.aantal} ${colli(it.p)} ${it.p.optString("naam")}" }
        }
        if (open.isNotEmpty()) {
            tekst += "\n\n" + resources.getQuantityString(R.plurals.niet_gecontroleerd, open.size, open.size,
                open.joinToString(", ") { it.p.optString("naam") })
        }
        AlertDialog.Builder(this)
            .setTitle(if (perLeverancier.size > 1) getString(R.string.n_bestellingen_klaarzetten, perLeverancier.size) else getString(R.string.bestelling_klaarzetten))
            .setMessage(tekst)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.klaarzetten) { _, _ -> verstuur(mee) }
            .show()
    }

    private fun verstuur(mee: List<Regel>) {
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        val aantallen = JSONObject()
        mee.forEach { aantallen.put(it.id.toString(), it.aantal) }
        b.onderKnop.isEnabled = false
        bezig {
            try {
                val antwoord = Api.post(this, "/api/app/bestellijst/bestellen", JSONObject().put("aantallen", aantallen), verzoekId = id)
                verzoekId = null
                tril(60)
                // De ronde is voorbij (zie wis_controle op de site): bij terugkomen staat de nieuwe bestellijst er.
                regels.removeAll { it.gecontroleerd }
                val ids = antwoord.optJSONArray("bestellingen")?.objecten()?.map { it.getInt("id") }.orEmpty()
                BesteloverzichtActivity.open(this, ids.toIntArray(), nieuw = true)
            } finally {
                b.onderKnop.isEnabled = true
            }
        }
    }

    companion object {
        private const val EXTRA_SCAN = "scan"

        /** [scan]: een product dat net gescand is; dat komt er meteen bij. */
        fun open(context: Context, scan: String? = null) =
            context.startActivity(Intent(context, BestellijstActivity::class.java).putExtra(EXTRA_SCAN, scan))
    }
}
