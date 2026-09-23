package nl.kantineblauwgeel.tablet

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.kantineblauwgeel.tablet.databinding.ActivityActiesBinding
import org.json.JSONObject

private data class ActieProduct(val id: Int, val naam: String, val categorie: String)
private data class Actie(
    val id: Int,
    var productId: Int,
    var productNaam: String,
    var tekst: String,
    var actief: Boolean,
)

/** Native lijst van prijs-acties (zie kiosk_acties in routes/kiosk.py) --
 * aanmaken/bewerken kiest een actief product uit een Spinner (dezelfde
 * regel als op de website: een actie hergebruikt de foto/prijs van een
 * bestaand product) en een optionele tekst. Toon-schakelaar en verwijderen
 * gaan direct, tikken op een rij opent de bewerk-dialoog. */
class ActiesActivity : AppCompatActivity() {

    private lateinit var binding: ActivityActiesBinding
    private val acties = mutableListOf<Actie>()
    private var producten = listOf<ActieProduct>()
    private lateinit var adapter: ActiesAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityActiesBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.terugKnop.setOnClickListener { finish() }
        adapter = ActiesAdapter(acties, ::schakelActie, ::toonDialoog, ::vraagVerwijderenBevestiging)
        binding.lijst.layoutManager = LinearLayoutManager(this)
        binding.lijst.adapter = adapter

        binding.knopNieuw.setOnClickListener { toonDialoog(null) }
        binding.foutmelding.setOnClickListener { laadActies() }
        laadActies()
    }

    private fun laadActies() {
        binding.laadindicator.visibility = View.VISIBLE
        binding.foutmelding.visibility = View.GONE
        binding.lijst.visibility = View.GONE

        Thread {
            try {
                val antwoord = Api.get(this, "/api/tablet/acties")
                val actiesJson = antwoord.getJSONArray("acties")
                val nieuweActies = mutableListOf<Actie>()
                for (i in 0 until actiesJson.length()) {
                    val a = actiesJson.getJSONObject(i)
                    nieuweActies.add(
                        Actie(
                            a.getInt("id"), a.getInt("product_id"), a.getString("product_naam"),
                            a.getString("tekst"), a.getBoolean("actief"),
                        )
                    )
                }
                val productenJson = antwoord.getJSONArray("producten")
                val nieuweProducten = mutableListOf<ActieProduct>()
                for (i in 0 until productenJson.length()) {
                    val p = productenJson.getJSONObject(i)
                    nieuweProducten.add(ActieProduct(p.getInt("id"), p.getString("naam"), p.getString("categorie")))
                }
                runOnUiThread {
                    acties.clear()
                    acties.addAll(nieuweActies)
                    producten = nieuweProducten
                    adapter.notifyDataSetChanged()
                    binding.laadindicator.visibility = View.GONE
                    binding.lijst.visibility = View.VISIBLE
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.laadindicator.visibility = View.GONE
                    binding.foutmelding.visibility = View.VISIBLE
                }
            }
        }.start()
    }

    private fun schakelActie(actie: Actie, gewenst: Boolean, herstel: () -> Unit) {
        Thread {
            try {
                val antwoord = Api.postForm(this, "/kiosk/prijzen/acties/${actie.id}/toon", emptyMap())
                if (antwoord.optBoolean("ok", false)) {
                    actie.actief = gewenst
                } else {
                    runOnUiThread { herstel() }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    herstel()
                    Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }

    private fun vraagVerwijderenBevestiging(actie: Actie) {
        AlertDialog.Builder(this)
            .setMessage(R.string.bevestig_verwijderen_actie)
            .setPositiveButton(R.string.verwijderen) { _, _ -> verwijderActie(actie) }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun verwijderActie(actie: Actie) {
        Thread {
            try {
                Api.postForm(this, "/kiosk/prijzen/acties/${actie.id}/verwijderen", emptyMap())
                runOnUiThread { laadActies() }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }

    private fun toonDialoog(actie: Actie?) {
        if (producten.isEmpty()) {
            Toast.makeText(this, R.string.fout_laden, Toast.LENGTH_SHORT).show()
            return
        }
        val view = LayoutInflater.from(this).inflate(R.layout.dialog_actie, null)
        val spinner = view.findViewById<Spinner>(R.id.productSpinner)
        val tekstVeld = view.findViewById<EditText>(R.id.tekstVeld)
        val actiefVinkje = view.findViewById<CheckBox>(R.id.actiefVinkje)

        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, producten.map { it.naam })
        val huidigeIndex = actie?.let { a -> producten.indexOfFirst { it.id == a.productId } } ?: -1
        if (huidigeIndex >= 0) spinner.setSelection(huidigeIndex)
        tekstVeld.setText(actie?.tekst ?: "")
        actiefVinkje.isChecked = actie?.actief ?: true

        AlertDialog.Builder(this)
            .setTitle(if (actie == null) R.string.nieuwe_actie_titel else R.string.actie_bewerken_titel)
            .setView(view)
            .setPositiveButton(R.string.opslaan) { _, _ ->
                val gekozenProduct = producten[spinner.selectedItemPosition]
                slaActieOp(actie, gekozenProduct.id, tekstVeld.text.toString().trim(), actiefVinkje.isChecked)
            }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun slaActieOp(actie: Actie?, productId: Int, tekst: String, actief: Boolean) {
        val pad = if (actie == null) "/kiosk/prijzen/acties/nieuw" else "/kiosk/prijzen/acties/${actie.id}/bewerken"
        val velden = mutableMapOf("product_id" to productId.toString(), "tekst" to tekst)
        if (actief) velden["actief"] = "on"

        Thread {
            try {
                val antwoord = Api.postForm(this, pad, velden)
                if (antwoord.optBoolean("ok", false)) {
                    runOnUiThread { laadActies() }
                } else {
                    runOnUiThread {
                        Toast.makeText(this, antwoord.optString("fout", getString(R.string.fout_opslaan)), Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }
}

private class ActiesAdapter(
    private val items: List<Actie>,
    private val onToggle: (Actie, Boolean, () -> Unit) -> Unit,
    private val onBewerken: (Actie) -> Unit,
    private val onVerwijderen: (Actie) -> Unit,
) : RecyclerView.Adapter<ActiesAdapter.Houder>() {

    class Houder(view: View) : RecyclerView.ViewHolder(view) {
        val inhoud: View = view.findViewById(R.id.inhoud)
        val productNaam: TextView = view.findViewById(R.id.productNaam)
        val tekst: TextView = view.findViewById(R.id.tekst)
        val schakelaar: Switch = view.findViewById(R.id.schakelaar)
        val verwijderKnop: View = view.findViewById(R.id.verwijderKnop)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Houder =
        Houder(LayoutInflater.from(parent.context).inflate(R.layout.item_actie, parent, false))

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(houder: Houder, positie: Int) {
        val actie = items[positie]
        houder.productNaam.text = actie.productNaam
        houder.tekst.text = actie.tekst
        houder.tekst.visibility = if (actie.tekst.isBlank()) View.GONE else View.VISIBLE

        fun zetSchakelaarOp(waarde: Boolean) {
            houder.schakelaar.setOnCheckedChangeListener(null)
            houder.schakelaar.isChecked = waarde
            houder.schakelaar.setOnCheckedChangeListener { _, gewenst ->
                onToggle(actie, gewenst) { zetSchakelaarOp(actie.actief) }
            }
        }
        zetSchakelaarOp(actie.actief)

        houder.inhoud.setOnClickListener { onBewerken(actie) }
        houder.verwijderKnop.setOnClickListener { onVerwijderen(actie) }
    }
}
