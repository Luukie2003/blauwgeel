package nl.kantineblauwgeel.tablet

import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivityUitgelichtBinding

private data class UitgelichtProduct(val id: Int, val naam: String, val categorie: String)

/** Native scherm voor het "uitgelicht"-product (zie
 * kiosk_uitgelicht_product_instellingen in routes/kiosk.py) -- 1 product
 * groot en omlijnd op het prijzenscherm, los van zijn eigen categorie.
 * "Geen (uitzetten)" bovenaan de Spinner stuurt een leeg product_id mee,
 * precies zoals de website-pagina de kaart weer uitzet. */
class UitgelichtActivity : AppCompatActivity() {

    private lateinit var binding: ActivityUitgelichtBinding
    private var producten = listOf<UitgelichtProduct>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityUitgelichtBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.terugKnop.setOnClickListener { finish() }
        binding.foutmelding.setOnClickListener { laadGegevens() }
        binding.opslaanKnop.setOnClickListener { slaOp() }
        laadGegevens()
    }

    private fun laadGegevens() {
        binding.laadindicator.visibility = View.VISIBLE
        binding.foutmelding.visibility = View.GONE
        binding.inhoud.visibility = View.GONE

        Thread {
            try {
                val antwoord = Api.get(this, "/api/tablet/uitgelicht")
                val productenJson = antwoord.getJSONArray("producten")
                val nieuweProducten = mutableListOf<UitgelichtProduct>()
                for (i in 0 until productenJson.length()) {
                    val p = productenJson.getJSONObject(i)
                    nieuweProducten.add(UitgelichtProduct(p.getInt("id"), p.getString("naam"), p.getString("categorie")))
                }
                val huidig = antwoord.optJSONObject("huidig")
                runOnUiThread {
                    producten = nieuweProducten
                    toonGegevens(huidig?.getInt("product_id"), huidig?.getString("titel"), huidig?.getString("naam"))
                    binding.laadindicator.visibility = View.GONE
                    binding.inhoud.visibility = View.VISIBLE
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.laadindicator.visibility = View.GONE
                    binding.foutmelding.visibility = View.VISIBLE
                }
            }
        }.start()
    }

    private fun toonGegevens(huidigProductId: Int?, huidigTitel: String?, huidigNaam: String?) {
        binding.huidigTekst.text = if (huidigNaam != null) {
            getString(R.string.uitgelicht_huidig, huidigNaam)
        } else {
            getString(R.string.uitgelicht_niets_huidig)
        }

        val namen = listOf(getString(R.string.uitgelicht_geen_optie)) + producten.map { it.naam }
        binding.productSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, namen)
        val huidigeIndex = huidigProductId?.let { id -> producten.indexOfFirst { it.id == id } } ?: -1
        binding.productSpinner.setSelection(if (huidigeIndex >= 0) huidigeIndex + 1 else 0)

        binding.titelVeld.setText(huidigTitel ?: "")
    }

    private fun slaOp() {
        val positie = binding.productSpinner.selectedItemPosition
        val productId = if (positie == 0) "" else producten[positie - 1].id.toString()
        val titel = binding.titelVeld.text.toString().trim()

        Thread {
            try {
                val antwoord = Api.postForm(this, "/kiosk/prijzen/uitgelicht", mapOf("product_id" to productId, "titel" to titel))
                if (antwoord.optBoolean("ok", false)) {
                    runOnUiThread { laadGegevens() }
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
