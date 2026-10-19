package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.kantineblauwgeel.handterminal.databinding.ItemProductBinding

/** De productlijst (zoeken, voorraad, koppelen): naam, categorie, voorraad en of hij laag of inactief is. */
class ProductAdapter(private val context: Context, private val bijKlik: (Catalogus.Product) -> Unit) :
    RecyclerView.Adapter<ProductAdapter.Regel>() {

    var lijst: List<Catalogus.Product> = emptyList()
        private set

    fun zet(nieuw: List<Catalogus.Product>) {
        lijst = nieuw
        @Suppress("NotifyDataSetChanged")
        notifyDataSetChanged()
    }

    class Regel(val v: ItemProductBinding) : RecyclerView.ViewHolder(v.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        Regel(ItemProductBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun getItemCount() = lijst.size

    override fun onBindViewHolder(regel: Regel, positie: Int) {
        val p = lijst[positie]
        val v = regel.v
        v.productNaam.text = p.naam
        v.productSub.text = listOf(p.categorie, p.subcategorie, p.merk).filter { it.isNotEmpty() }.distinct().joinToString(" · ")
        v.productVoorraad.text = p.voorraadTekst()
        v.productVoorraad.setTextColor(context.getColor(if (p.laag || p.voorraad < 0) R.color.rood_balk else R.color.tekst))
        v.productLabel.isVisible = p.laag || !p.actief
        v.productLabel.text = context.getString(if (!p.actief) R.string.inactief else R.string.laag)
        v.productLabel.setBackgroundResource(if (!p.actief) R.drawable.badge_grijs else R.drawable.badge_rood)
        v.productLabel.setTextColor(context.getColor(if (!p.actief) R.color.tekst_zacht else R.color.wit))
        v.root.alpha = if (p.actief) 1f else 0.6f
        v.root.setOnClickListener { bijKlik(p) }
    }

    /** De lijst klaarzetten in een RecyclerView, met dunne lijntjes tussen de regels. */
    fun koppel(lijstView: RecyclerView) {
        lijstView.layoutManager = LinearLayoutManager(context)
        lijstView.adapter = this
        lijstView.addItemDecoration(DividerItemDecoration(context, DividerItemDecoration.VERTICAL).apply {
            ContextCompat.getDrawable(context, R.drawable.scheiding)?.let { setDrawable(it) }
        })
    }
}
