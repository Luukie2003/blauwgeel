package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.TextView
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityProductenBinding

/** Zoeken, de voorraad bekijken of een product kiezen om te boeken: allemaal dezelfde lijst, op het toestel zelf
 * doorzocht (zie Catalogus), dus zonder wachten. Per categorie te filteren, of alleen wat onder het minimum zit.
 * Een product aantikken opent het; scannen opent meteen het gescande product. */
class ProductenActivity : BasisActivity() {

    enum class Modus { ZOEKEN, VOORRAAD, BOEKEN }

    private lateinit var b: ActivityProductenBinding
    private lateinit var modus: Modus
    private var categorie: String? = null
    private var alleenLaag = false
    private val adapter by lazy { ProductAdapter(this) { ProductActivity.open(this, it.id, alleenInfo = alleenInfo) } }

    /** Bij Boeken staat boeken bovenaan; bij zoeken en Voorraad opent het product als informatie. */
    private val alleenInfo get() = modus != Modus.BOEKEN

    override fun bijScan(code: String) = openScan(code, alleenInfo)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityProductenBinding.inflate(layoutInflater)
        setContentView(b.root)
        modus = Modus.valueOf(intent.getStringExtra(EXTRA_MODUS) ?: Modus.ZOEKEN.name)
        alleenLaag = intent.getBooleanExtra(EXTRA_LAAG, false)
        richtBalkIn(
            b.balk,
            getString(when (modus) {
                Modus.ZOEKEN -> R.string.titel_zoeken
                Modus.VOORRAAD -> R.string.titel_voorraad
                Modus.BOEKEN -> R.string.titel_boeken
            }),
            sub = if (modus == Modus.BOEKEN) getString(R.string.kies_of_scan) else Sessie.naam,
        )

        adapter.koppel(b.lijst)
        b.zoekVeld.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) = filter()
        })
        b.zoekVeld.setOnEditorActionListener { _, actie, _ ->
            if (actie == EditorInfo.IME_ACTION_SEARCH) {
                verbergToetsenbord()
                // Een ingetikte barcode, of precies één uitkomst: meteen openen.
                val term = b.zoekVeld.text.toString()
                if (Catalogus.normaliseerCode(term)?.length in setOf(8, 13, 14)) openScan(term, alleenInfo)
                else adapter.lijst.singleOrNull()?.let { ProductActivity.open(this, it.id, alleenInfo = alleenInfo) }
            }
            true
        }
        b.laagKnop.isSelected = alleenLaag
        b.laagKnop.setOnClickListener {
            alleenLaag = !alleenLaag
            it.isSelected = alleenLaag
            filter()
        }
        bouwCategorieen()
        filter()
        if (modus == Modus.ZOEKEN) {
            b.zoekVeld.requestFocus()
            b.zoekVeld.post {
                (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showSoftInput(b.zoekVeld, 0)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!Sessie.isIngelogd(this)) return
        // Na boeken staat de lijst al goed (Catalogus.werkBij); verder op de achtergrond verversen.
        filter()
        bezig {
            if (Catalogus.ververs(this)) {
                bouwCategorieen()
                filter()
            }
        }
    }

    override fun weerVerbonden() {
        bezig { if (Catalogus.ververs(this)) filter() }
    }

    private fun verbergToetsenbord() {
        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(b.zoekVeld.windowToken, 0)
    }

    private fun bouwCategorieen() {
        b.categorieen.removeAllViews()
        val namen = listOf<String?>(null) + Catalogus.categorieen()
        for (naam in namen) {
            val chip = LayoutInflater.from(this).inflate(R.layout.keuze, b.categorieen, false) as TextView
            chip.text = naam ?: getString(R.string.alles)
            chip.isSelected = naam == categorie
            chip.setOnClickListener {
                categorie = naam
                for (i in 0 until b.categorieen.childCount) b.categorieen.getChildAt(i).isSelected = false
                chip.isSelected = true
                filter()
            }
            b.categorieen.addView(chip)
        }
    }

    private fun filter() {
        val term = b.zoekVeld.text.toString()
        val lijst = Catalogus.zoek(term, categorie, alleenLaag)
        adapter.zet(lijst)
        b.aantalTekst.text = resources.getQuantityString(R.plurals.n_producten, lijst.size, lijst.size)
        b.leegTekst.isVisible = lijst.isEmpty()
        b.leegTekst.text = when {
            Catalogus.leeg -> getString(R.string.producten_laden)
            alleenLaag && term.isEmpty() -> getString(R.string.niets_laag)
            else -> getString(R.string.geen_producten)
        }
    }

    companion object {
        private const val EXTRA_MODUS = "modus"
        private const val EXTRA_LAAG = "laag"

        fun open(activity: Activity, modus: Modus, alleenLaag: Boolean = false) {
            activity.startActivity(
                Intent(activity, ProductenActivity::class.java).putExtra(EXTRA_MODUS, modus.name).putExtra(EXTRA_LAAG, alleenLaag),
            )
        }
    }
}
