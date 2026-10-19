package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De bestellijst om te bekijken: wat onder het minimum zit (en nog niet besteld is), wat bezoekers via de QR-code
 * meldden, en wat er onderweg is (inboeken: Factuur inboeken). Een bestelling klaarzetten kan alleen op de website. */
class BestellijstActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

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

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/bestellijst"))
            } finally {
                b.verversen.isRefreshing = false
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

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val bestellen = data.getJSONArray("bestellen").objecten()
        Lijst.kop(inhoud, getString(R.string.bestellen_kop, bestellen.size))
        if (bestellen.isEmpty()) Lijst.leeg(inhoud, getString(R.string.niets_bestellen))
        else {
            val kaart = Lijst.kaart(inhoud)
            for (p in bestellen) {
                Lijst.regel(kaart, p.optString("naam"), hoeveelheid(p), getString(R.string.laag), R.color.rood_balk) {
                    ProductActivity.open(this, p.getInt("id"))
                }
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
                            bezig { toon(Api.post(this, "/api/app/bestellijst/gemeld/${p.getInt("id")}/afhandelen", herhaalbaar = true)) }
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
                ) { startActivity(Intent(this, FacturenActivity::class.java)) }
            }
        }

        Lijst.kop(inhoud, getString(R.string.op_de_computer))
        Lijst.knop(Lijst.kaart(inhoud), getString(R.string.bestelling_klaarzetten)) { nietInApp(getString(R.string.wat_bestelling_klaarzetten)) }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, BestellijstActivity::class.java))
    }
}
