package nl.kantineblauwgeel.handterminal

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.annotation.DrawableRes
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityStartBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemLetopBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemMeerBinding
import nl.kantineblauwgeel.handterminal.databinding.TegelBinding
import org.json.JSONObject

/** Het startscherm: zoeken of scannen, de vier dingen van het dagelijkse werk (Factuur inboeken, Tellen, Boeken,
 * Voorraad), wat aandacht nodig heeft, en de pagina's die nog als website openen. Toont meteen het vorige antwoord van
 * de site (bewaard op het toestel) en ververst op de achtergrond, ook de productlijst. */
class StartActivity : BasisActivity() {

    private lateinit var b: ActivityStartBinding
    override val isStartscherm = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityStartBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.app_naam), sub = Sessie.naam, terug = false)

        b.zoekKnop.setOnClickListener { ProductenActivity.open(this, ProductenActivity.Modus.ZOEKEN) }
        tegel(b.tegelFactuur, R.drawable.ic_factuur, R.string.tegel_factuur) { startActivity(Intent(this, FacturenActivity::class.java)) }
        tegel(b.tegelTellen, R.drawable.ic_tellen, R.string.tegel_tellen) { startActivity(Intent(this, TellenActivity::class.java)) }
        tegel(b.tegelBoeken, R.drawable.ic_boeken, R.string.tegel_boeken) { ProductenActivity.open(this, ProductenActivity.Modus.BOEKEN) }
        tegel(b.tegelVoorraad, R.drawable.ic_voorraad, R.string.tegel_voorraad) { ProductenActivity.open(this, ProductenActivity.Modus.VOORRAAD) }
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                moveTaskToBack(true)
            }
        })

        inst.startCache?.let {
            try {
                toon(JSONObject(it))
            } catch (e: Exception) {
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) {
            laad()
            bezig { Catalogus.ververs(this) }
        }
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                val start = Api.getJson(this, "/api/app/start")
                inst.startCache = start.toString()
                toon(start)
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun tegel(tegel: TegelBinding, @DrawableRes icoon: Int, naam: Int, actie: () -> Unit) {
        tegel.tegelIcoon.setImageResource(icoon)
        tegel.tegelNaam.setText(naam)
        tegel.root.setOnClickListener { actie() }
    }

    private fun zetTegel(tegel: TegelBinding, sub: String, teller: Int?, rood: Boolean = true) {
        tegel.tegelSub.text = sub
        tegel.tegelTeller.isVisible = teller != null && teller > 0
        tegel.tegelTeller.text = teller?.toString()
        tegel.tegelTeller.setBackgroundResource(if (rood) R.drawable.badge_rood else R.drawable.badge_geel)
        tegel.tegelTeller.setTextColor(getColor(if (rood) R.color.wit else R.color.navy))
    }

    private fun toon(start: JSONObject) {
        val naam = start.tekstOfNull("naam") ?: Sessie.naam ?: ""
        zetBalkTitel("${start.optString("groet", getString(R.string.hallo))}, $naam")
        zetBalkSub(null)

        val voorraad = start.optJSONObject("toegang")?.optBoolean("voorraad") ?: true
        b.zoekKnop.isVisible = voorraad
        b.tegels.isVisible = voorraad
        val laag = start.optInt("laag")
        val facturen = start.optInt("open_facturen")
        zetTegel(b.tegelFactuur, if (facturen > 0) getString(R.string.n_bezig, facturen) else getString(R.string.dozen_scannen), facturen, rood = false)
        zetTegel(b.tegelBoeken, getString(R.string.erin_of_eruit), null)
        zetTegel(b.tegelVoorraad, if (laag > 0) getString(R.string.n_onder_minimum, laag) else getString(R.string.alles_op_orde), laag)
        val looplijst = start.optJSONObject("looplijst")
        val telling = start.optJSONObject("telling")
        zetTegel(
            b.tegelTellen,
            when {
                looplijst?.optBoolean("in_controle") == true -> getString(R.string.verder_controleren)
                looplijst != null -> getString(
                    R.string.verder_bij,
                    getString(if (looplijst.optString("fase") == "hok") R.string.fase_hok_kort else R.string.fase_bar_kort),
                    looplijst.optInt("nummer"), looplijst.optInt("totaal"),
                )
                telling?.has("dagen_geleden") == true && !telling.isNull("dagen_geleden") ->
                    dagenGeleden(telling.optInt("dagen_geleden"))
                else -> getString(R.string.telling_lopen)
            },
            if (looplijst != null) 1 else null,
            rood = false,
        )
        if (looplijst != null) b.tegelTellen.tegelTeller.text = "•"

        // Let op
        b.letOpLijst.removeAllViews()
        start.optJSONArray("taken")?.objecten()?.forEach { t ->
            letOp(t.optString("titel"), t.optString("detail"), if (t.optBoolean("urgent")) R.drawable.rand_links_rood else R.drawable.rand_links_oranje) {
                WebActivity.open(this, t.optString("pad"), t.optString("titel"))
            }
        }
        if (voorraad && laag > 0) {
            letOp(resources.getQuantityString(R.plurals.onder_minimum, laag, laag), getString(R.string.bekijk_welke), R.drawable.rand_links_rood) {
                ProductenActivity.open(this, ProductenActivity.Modus.VOORRAAD, alleenLaag = true)
            }
        }
        val bestellingen = start.optInt("open_bestellingen")
        if (voorraad && bestellingen > 0) {
            letOp(resources.getQuantityString(R.plurals.bestellingen_inboeken, bestellingen, bestellingen), getString(R.string.scan_de_levering), R.drawable.rand_links_oranje) {
                startActivity(Intent(this, FacturenActivity::class.java))
            }
        }
        val urgent = start.optInt("mededelingen_urgent")
        if (urgent > 0) {
            letOp(getString(R.string.prikbord_urgent, urgent), getString(R.string.n_open, start.optInt("mededelingen_open")), R.drawable.rand_links_rood) {
                WebActivity.open(this, "/bijzonderheden", getString(R.string.prikbord))
            }
        }
        b.letOpKop.isVisible = b.letOpLijst.childCount > 0

        // Meer (op de website)
        b.meerLijst.removeAllViews()
        val paginas = start.optJSONArray("paginas")?.objecten() ?: emptyList()
        b.meerKop.isVisible = paginas.isNotEmpty()
        paginas.chunked(3).forEach { rij ->
            val regel = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            rij.forEach { p ->
                val item = ItemMeerBinding.inflate(LayoutInflater.from(this), regel, false)
                item.meerNaam.text = p.optString("label")
                item.meerIcoon.setImageResource(icoonVoor(p.optString("label")))
                val teller = if (p.isNull("teller")) 0 else p.optInt("teller")
                item.meerTeller.isVisible = teller > 0
                item.meerTeller.text = teller.toString()
                if (p.optBoolean("let_op")) {
                    item.meerTeller.setBackgroundResource(R.drawable.badge_rood)
                    item.meerTeller.setTextColor(getColor(R.color.wit))
                }
                item.root.setOnClickListener { WebActivity.open(this, p.optString("pad"), p.optString("label")) }
                regel.addView(item.root)
            }
            repeat(3 - rij.size) { regel.addView(android.view.View(this), LinearLayout.LayoutParams(0, 1, 1f)) }
            b.meerLijst.addView(regel)
        }

        b.standTekst.text = telling?.tekstOfNull("datum")?.let {
            getString(R.string.laatst_geteld, it.take(10).split("-").reversed().joinToString("-"), telling.tekstOfNull("door") ?: "?")
        } ?: ""

        val nieuwste = start.optString("app_versie")
        b.updateMelding.isVisible = nieuwer(nieuwste, BuildConfig.VERSION_NAME)
        b.updateMelding.text = getString(R.string.update_beschikbaar, nieuwste)
    }

    private fun letOp(titel: String, detail: String, @DrawableRes rand: Int, actie: () -> Unit) {
        val regel = ItemLetopBinding.inflate(LayoutInflater.from(this), b.letOpLijst, false)
        regel.root.setBackgroundResource(rand)
        regel.letOpTitel.text = titel
        regel.letOpDetail.text = detail
        regel.letOpDetail.isVisible = detail.isNotEmpty()
        regel.root.setOnClickListener { actie() }
        b.letOpLijst.addView(regel.root)
    }

    private fun dagenGeleden(dagen: Int) = when (dagen) {
        0 -> getString(R.string.vandaag_geteld)
        1 -> getString(R.string.gisteren_geteld)
        else -> getString(R.string.dagen_geleden_geteld, dagen)
    }

    @DrawableRes
    private fun icoonVoor(label: String) = when (label) {
        "Bestellijst" -> R.drawable.ic_bestellijst
        "Boodschappen" -> R.drawable.ic_boodschappen
        "Prognose" -> R.drawable.ic_prognose
        "Agenda" -> R.drawable.ic_agenda
        "Tellingen" -> R.drawable.ic_tellingen
        "Geschiedenis" -> R.drawable.ic_geschiedenis
        "Barcodes" -> R.drawable.ic_barcodes
        "Prikbord" -> R.drawable.ic_prikbord
        "Kassa" -> R.drawable.ic_kassa
        "Keuken" -> R.drawable.ic_keuken
        "Kantine-tv" -> R.drawable.ic_kiosk
        "Kluis" -> R.drawable.ic_kluis
        "Club van 20" -> R.drawable.ic_aanmeldingen
        else -> R.drawable.ic_website
    }

    companion object {
        /** Is versie a (bijv. "2.1.0") nieuwer dan b? */
        fun nieuwer(a: String, b: String): Boolean {
            val x = a.split('.').map { it.toIntOrNull() ?: 0 }
            val y = b.split('.').map { it.toIntOrNull() ?: 0 }
            for (i in 0 until maxOf(x.size, y.size)) {
                val verschil = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
                if (verschil != 0) return verschil > 0
            }
            return false
        }
    }
}
