package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De bestellijst: wat onder het minimum zit (en nog niet besteld is), met de prognose erbij (wat er de komende week
 * verwacht wordt, en hoeveel je dan bestelt), wat bij een vorige bestelling niet geleverd is, wat waarschijnlijk opraakt
 * terwijl het nog boven het minimum zit, wat bezoekers via de QR-code meldden, en wat er onderweg is (tik om de levering
 * in te scannen). "Bestelling klaarzetten" opent [KlaarzettenActivity]; een scan hier ook, met het gescande product er
 * meteen bij. De prognose rekent soms enkele seconden en komt er apart bij. */
class BestellijstActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var data: JSONObject? = null
    private var prognose: JSONObject? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.bestellijst))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    /** Een product scannen op de bestellijst: een nieuwe bestelling klaarzetten, met dit product erbij. */
    override fun bijScan(code: String) = KlaarzettenActivity.open(this, code)

    private fun laad() {
        bezig {
            try {
                data = Api.getJson(this, "/api/app/bestellijst")
                toon()
            } finally {
                b.verversen.isRefreshing = false
            }
            if (prognose == null) {
                prognose = Api.getJson(this, "/api/app/bestellijst/prognose")
                toon()
            }
        }
    }

    private fun hoeveelheid(p: JSONObject): String {
        val per = p.optInt("per_besteleenheid", 1)
        val naam = p.tekstOfNull("besteleenheid")
        val tekort = p.optInt("min_voorraad") - p.optInt("voorraad")
        if (naam == null || per <= 1 || tekort <= 0) return getString(R.string.voorraad_min, p.optInt("voorraad"), p.optInt("min_voorraad"), p.optString("eenheid"))
        val eenheden = (tekort + per - 1) / per
        return getString(R.string.voorraad_min, p.optInt("voorraad"), p.optInt("min_voorraad"), p.optString("eenheid")) +
            " · " + getString(R.string.minstens_n, eenheden, naam)
    }

    /** Wat de prognose bij een voorgesteld product zegt: de verwachte verkoop, en een hoger aantal als de komende week
     * meer vraagt dan het minimum. */
    private fun metPrognose(p: JSONObject): String {
        val basis = hoeveelheid(p)
        val pr = prognose ?: return basis + "\n" + getString(R.string.prognose_bezig)
        val x = pr.optJSONObject("producten")?.optJSONObject(p.getInt("id").toString()) ?: return basis
        val eenheid = p.tekstOfNull("besteleenheid") ?: p.optString("eenheid")
        var tekst = basis + "\n" + getString(R.string.verwacht_7_dagen, x.optInt("verwacht"), p.optString("eenheid"))
        if (x.optInt("advies_eenheden") > x.optInt("basis_eenheden")) {
            tekst += " · " + getString(R.string.bestel_liever, x.optInt("advies_eenheden"), eenheid)
        }
        return tekst
    }

    private fun toon() {
        val data = data ?: return
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        Lijst.kaart(inhoud).let {
            Lijst.knop(it, getString(R.string.bestelling_klaarzetten)) { KlaarzettenActivity.open(this) }
            Lijst.tekst(it, getString(R.string.bestellijst_scan_uitleg), grootte = 12f)
        }
        val bestellen = data.getJSONArray("bestellen").objecten()
        Lijst.kop(inhoud, getString(R.string.bestellen_kop, bestellen.size))
        if (bestellen.isEmpty()) Lijst.leeg(inhoud, getString(R.string.niets_bestellen))
        else {
            val kaart = Lijst.kaart(inhoud)
            for (p in bestellen) {
                Lijst.regel(kaart, p.optString("naam"), metPrognose(p), getString(R.string.laag), R.color.rood_balk) {
                    ProductActivity.open(this, p.getInt("id"))
                }
            }
        }

        val manco = data.optJSONArray("manco")?.objecten().orEmpty()
        if (manco.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.klaarzetten_manco))
            val kaart = Lijst.kaart(inhoud, R.drawable.rand_links_oranje)
            for (p in manco) {
                Lijst.regel(kaart, p.optString("naam"),
                    getString(R.string.niet_geleverd_detail, p.optInt("tekort"), p.optString("eenheid")),
                    getString(R.string.n_eenheid, p.optInt("tekort_besteleenheden"), p.tekstOfNull("besteleenheid") ?: p.optString("eenheid")),
                    R.color.oranje_balk) { ProductActivity.open(this, p.getInt("id")) }
            }
        }

        val extra = prognose?.optJSONArray("extra")?.objecten().orEmpty()
        if (extra.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.kan_opraken))
            val kaart = Lijst.kaart(inhoud, R.drawable.rand_links_oranje)
            for (p in extra) {
                val urgent = p.optString("status") == "urgent"
                Lijst.regel(
                    kaart, p.optString("naam"),
                    getString(R.string.voorraad_verwacht, p.optInt("voorraad"), p.optInt("verwacht"), p.optString("eenheid")) + " · " +
                        getString(R.string.advies_kort_eenheden, p.optInt("advies_eenheden"), p.optString("besteleenheid")),
                    "${Math.round(p.optDouble("kans_tekort") * 100)}%", if (urgent) R.color.rood_balk else R.color.oranje_balk,
                ) { ProductActivity.open(this, p.getInt("id")) }
            }
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
                val regels = best.getJSONArray("regels").objecten()
                Lijst.regel(
                    kaart,
                    best.tekstOfNull("referentie") ?: getString(R.string.bestelling_nr, best.getInt("id")),
                    regels.joinToString(", ") { "${it.optInt("aantal")} ${it.optString("product")}" },
                    Lijst.datum(best.tekstOfNull("aangemaakt_op"), metTijd = false),
                    R.color.tekst_zacht,
                ) { FacturenActivity.inboeken(this, best.getInt("id")) }
            }
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, BestellijstActivity::class.java))
    }
}
