package nl.kantineblauwgeel.tablet

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.kantineblauwgeel.tablet.databinding.ActivityProductenBinding
import org.json.JSONObject

private data class Product(
    val id: Int,
    val naam: String,
    val categorie: String,
    var actief: Boolean,
    var uitverkocht: Boolean,
)

/** Native lijst van alle producten met 2 schakelaars per stuk: Actief (de
 * echte voorraad/assortiment-status, zie product_actief_wisselen in
 * routes/producten.py) en Uitverkocht (puur een snelle markering voor het
 * prijzenscherm, zie kiosk_product_uitverkocht_wisselen in routes/kiosk.py
 * -- raakt de voorraad niet aan). Geen WebView, dit praat rechtstreeks met
 * de bestaande website-routes (zie Api.kt). Wie de vereiste sectie niet
 * heeft krijgt van de server gewoon een foutmelding terug bij het
 * schakelen, precies zoals op de website zelf. */
class ProductenActivity : AppCompatActivity() {

    private lateinit var binding: ActivityProductenBinding
    private val producten = mutableListOf<Product>()
    private lateinit var adapter: ProductenAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityProductenBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.terugKnop.setOnClickListener { finish() }
        adapter = ProductenAdapter(producten, ::schakelActief, ::schakelUitverkocht)
        binding.lijst.layoutManager = LinearLayoutManager(this)
        binding.lijst.adapter = adapter

        binding.foutmelding.setOnClickListener { laadProducten() }
        laadProducten()
    }

    private fun laadProducten() {
        binding.laadindicator.visibility = View.VISIBLE
        binding.foutmelding.visibility = View.GONE
        binding.lijst.visibility = View.GONE

        Thread {
            try {
                val antwoord = Api.get(this, "/api/tablet/producten")
                val lijst = antwoord.getJSONArray("producten")
                val nieuw = mutableListOf<Product>()
                for (i in 0 until lijst.length()) {
                    val p = lijst.getJSONObject(i)
                    nieuw.add(
                        Product(
                            p.getInt("id"), p.getString("naam"), p.getString("categorie"),
                            p.getBoolean("actief"), p.getBoolean("uitverkocht"),
                        )
                    )
                }
                runOnUiThread {
                    producten.clear()
                    producten.addAll(nieuw)
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

    private fun schakelActief(product: Product, gewenst: Boolean, herstel: () -> Unit) {
        schakel("/producten/${product.id}/actief", gewenst, herstel,
            pas = { product.actief = it }, huidig = { product.actief })
    }

    private fun schakelUitverkocht(product: Product, gewenst: Boolean, herstel: () -> Unit) {
        schakel("/kiosk/prijzen/product/${product.id}/uitverkocht", gewenst, herstel,
            pas = { product.uitverkocht = it }, huidig = { product.uitverkocht })
    }

    private fun schakel(
        pad: String,
        gewenst: Boolean,
        herstel: () -> Unit,
        pas: (Boolean) -> Unit,
        huidig: () -> Boolean,
    ) {
        Thread {
            try {
                val antwoord = Api.postForm(this, pad, emptyMap())
                if (antwoord.optBoolean("ok", false)) {
                    pas(gewenst)
                    runOnUiThread { if (huidig() != gewenst) herstel() }
                } else {
                    runOnUiThread {
                        herstel()
                        Toast.makeText(this, antwoord.optString("fout", getString(R.string.fout_opslaan)), Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    herstel()
                    Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }
}

private class ProductenAdapter(
    private val items: List<Product>,
    private val onToggleActief: (Product, Boolean, () -> Unit) -> Unit,
    private val onToggleUitverkocht: (Product, Boolean, () -> Unit) -> Unit,
) : RecyclerView.Adapter<ProductenAdapter.Houder>() {

    class Houder(view: View) : RecyclerView.ViewHolder(view) {
        val naam: TextView = view.findViewById(R.id.naam)
        val categorie: TextView = view.findViewById(R.id.categorie)
        val schakelaarActief: Switch = view.findViewById(R.id.schakelaarActief)
        val schakelaarUitverkocht: Switch = view.findViewById(R.id.schakelaarUitverkocht)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Houder =
        Houder(LayoutInflater.from(parent.context).inflate(R.layout.item_product, parent, false))

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(houder: Houder, positie: Int) {
        val product = items[positie]
        houder.naam.text = product.naam
        houder.categorie.text = product.categorie

        fun zetOp(schakelaar: Switch, waarde: Boolean, callback: (Product, Boolean, () -> Unit) -> Unit, huidig: () -> Boolean) {
            schakelaar.setOnCheckedChangeListener(null)
            schakelaar.isChecked = waarde
            schakelaar.setOnCheckedChangeListener { _, gewenst ->
                callback(product, gewenst) { zetOp(schakelaar, huidig(), callback, huidig) }
            }
        }
        zetOp(houder.schakelaarActief, product.actief, onToggleActief) { product.actief }
        zetOp(houder.schakelaarUitverkocht, product.uitverkocht, onToggleUitverkocht) { product.uitverkocht }
    }
}
