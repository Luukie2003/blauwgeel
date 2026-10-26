package nl.kantineblauwgeel.handterminal

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.widget.ArrayAdapter
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityFacturenBinding
import nl.kantineblauwgeel.handterminal.databinding.DialogNieuweFactuurBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemLetopBinding
import org.json.JSONObject

/** Factuur inboeken: een klaargezette bestelling inboeken (het concept van de factuur, met wat er besteld is), verder
 * met een die nog open staat, of een nieuwe factuur beginnen (leverancier, bestelling en factuurnummer mogen leeg). Het
 * scannen zelf gebeurt in FactuurActivity. Gebruikt de factuur-API van de site (routes/facturen.py). */
class FacturenActivity : BasisActivity() {

    private lateinit var b: ActivityFacturenBinding
    private var gegevens: JSONObject? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityFacturenBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.tegel_factuur))
        b.nieuwKnop.setOnClickListener { nieuweFactuur() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            val data = Api.getJson(this, "/api/facturen")
            gegevens = data
            val klaar = data.optJSONArray("bestellingen")?.objecten().orEmpty().filter { it.isNull("ronde_id") }
            b.klaarKop.isVisible = klaar.isNotEmpty()
            b.klaarLijst.removeAllViews()
            for (best in klaar) {
                val regel = ItemLetopBinding.inflate(LayoutInflater.from(this), b.klaarLijst, false)
                regel.root.setBackgroundResource(R.drawable.rand_links_navy)
                regel.letOpTitel.text = (best.tekstOfNull("referentie")?.let { getString(R.string.bestelling_ref, best.getInt("id"), it) }
                    ?: getString(R.string.bestelling_nr, best.getInt("id"))) + (best.tekstOfNull("leverancier")?.let { " · $it" } ?: "")
                regel.letOpDetail.text = best.optString("samenvatting")
                regel.root.setOnClickListener { inboeken(this, best.getInt("id")) }
                b.klaarLijst.addView(regel.root)
            }
            val open = data.getJSONArray("open").objecten()
            b.openKop.isVisible = open.isNotEmpty()
            b.openLijst.removeAllViews()
            for (r in open) {
                val regel = ItemLetopBinding.inflate(LayoutInflater.from(this), b.openLijst, false)
                regel.root.setBackgroundResource(R.drawable.rand_links_oranje)
                regel.letOpTitel.text = FactuurActivity.naam(this, r)
                regel.letOpDetail.text = getString(
                    R.string.factuur_regel, r.optInt("scans"), FactuurActivity.euro(r.optDouble("totaal")),
                    r.optString("gestart_op").let { if (it.length >= 16) "${it.substring(8, 10)}-${it.substring(5, 7)} ${it.substring(11, 16)}" else it },
                ) + if (!r.isNull("bestelling_id") && !r.isNull("leverancier")) " · " + getString(R.string.bij_bestelling, r.optInt("bestelling_id")) else ""
                regel.root.setOnClickListener { FactuurActivity.open(this, r.getInt("id")) }
                b.openLijst.addView(regel.root)
            }
        }
    }

    /** Leverancier, bestelling en factuurnummer zijn handig maar niet nodig: gewoon beginnen kan ook. */
    private fun nieuweFactuur() {
        val data = gegevens
        val d = DialogNieuweFactuurBinding.inflate(layoutInflater)
        val leveranciers = data?.optJSONArray("leveranciers")?.objecten() ?: emptyList()
        val bestellingen = data?.optJSONArray("bestellingen")?.objecten() ?: emptyList()
        d.leverancier.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            listOf(getString(R.string.weet_ik_niet)) + leveranciers.map { it.optString("naam") })
        d.bestelling.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            listOf(getString(R.string.geen_bestelling)) + bestellingen.map {
                (it.tekstOfNull("referentie") ?: getString(R.string.bestelling_nr, it.optInt("id"))) +
                    " · " + it.optString("aangemaakt_op").take(10).split("-").reversed().joinToString("-")
            })
        AlertDialog.Builder(this)
            .setTitle(R.string.nieuwe_factuur)
            .setView(d.root)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.beginnen) { _, _ ->
                val body = JSONObject()
                d.leverancier.selectedItemPosition.takeIf { it > 0 }?.let { body.put("leverancier_id", leveranciers[it - 1].getInt("id")) }
                d.bestelling.selectedItemPosition.takeIf { it > 0 }?.let { body.put("bestelling_id", bestellingen[it - 1].getInt("id")) }
                d.factuurnummer.text.toString().trim().takeIf { it.isNotEmpty() }?.let { body.put("factuurnummer", it) }
                bezig {
                    val ronde = Api.post(this, "/api/facturen", body)
                    FactuurActivity.open(this, ronde.getInt("id"))
                }
            }
            .show()
    }

    companion object {
        fun open(activity: android.app.Activity) = activity.startActivity(Intent(activity, FacturenActivity::class.java))

        /** Een klaargezette bestelling inboeken: de site geeft de ronde die er al bij hoort, of begint een nieuwe. */
        fun inboeken(activity: BasisActivity, bestellingId: Int) {
            activity.bezig {
                val ronde = Api.post(activity, "/api/facturen/bestelling/$bestellingId", herhaalbaar = true)
                FactuurActivity.open(activity, ronde.getInt("id"))
            }
        }
    }
}
