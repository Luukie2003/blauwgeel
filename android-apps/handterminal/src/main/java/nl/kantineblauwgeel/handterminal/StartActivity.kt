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
 * Voorraad), wat aandacht nodig heeft (ook de taken die een beheerder voor je klaarzette) en daaronder alle andere
 * schermen per onderwerp (Voorraad en bestellen, Kantine en keuken, Geld, Club), voor zover je er rechten voor hebt. Alles in de app zelf; de kantine-tv in KantineTvActivity. Toont meteen het vorige antwoord van de site (bewaard op het toestel) en ververst op de
 * achtergrond, ook de productlijst. */
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

    /** Een scan in het menu: alleen de informatie van het product, boeken staat onderaan. */
    override fun bijScan(code: String) = openScan(code, alleenInfo = true)

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
        val toegang = start.optJSONObject("toegang")
        fun heeft(sectie: String) = toegang?.optBoolean(sectie) ?: false
        val beheerder = start.optBoolean("beheerder")
        // De timers op de tv's (bijvoorbeeld de gehaktballen): wat er loopt, of wat klaar is.
        start.optJSONArray("timers")?.objecten()?.forEach { t ->
            val klaar = t.optBoolean("klaar")
            letOp(
                if (klaar) getString(R.string.letop_timer_klaar, t.optString("naam"))
                else getString(R.string.letop_timer_loopt, t.optString("naam"), t.optString("klaar_om")),
                getString(R.string.letop_timer_detail),
                if (klaar) R.drawable.rand_links_oranje else R.drawable.rand_links_navy,
            ) { TimerActivity.open(this) }
        }
        // Taken die een beheerder voor jou klaarzette: een eigen scherm met de stappen en afronden.
        start.optJSONArray("taken")?.objecten()?.forEach { t ->
            val rand = if (t.optBoolean("urgent")) R.drawable.rand_links_rood else R.drawable.rand_links_oranje
            if (t.has("id")) letOp(t.optString("titel"), t.optString("detail"), rand) { TaakActivity.open(this, t.getInt("id")) }
            else letOp(t.optString("titel"), t.optString("detail"), rand, null)
        }
        val kassa = start.optJSONObject("kassa")
        if (kassa != null) {
            val concepten = kassa.optInt("concepten")
            if (concepten > 0) {
                letOp(resources.getQuantityString(R.plurals.kassatellingen_goedkeuren, concepten, concepten), getString(R.string.controleer_en_keur_goed),
                    R.drawable.rand_links_oranje) { GeldActivity.open(this, GeldActivity.KASSA) }
            } else if (kassa.optString("status") == "rood") {
                letOp(getString(R.string.kassa_tellen), kassa.optString("tekst"), R.drawable.rand_links_rood) { GeldActivity.open(this, GeldActivity.KASSA) }
            }
        }
        val kluis = start.optInt("kluis_concepten")
        if (beheerder && kluis > 0) {
            letOp(resources.getQuantityString(R.plurals.kluistellingen_goedkeuren, kluis, kluis), getString(R.string.controleer_en_keur_goed),
                R.drawable.rand_links_oranje) { GeldActivity.open(this, GeldActivity.KLUIS) }
        }
        start.optJSONObject("frituurvet")?.takeIf { !it.optBoolean("ok") }?.let { vet ->
            letOp(getString(R.string.frituurvet_vervangen), if (vet.isNull("dagen_geleden")) getString(R.string.frituurvet_nooit)
                else getString(R.string.frituurvet_dagen, vet.optInt("dagen_geleden")), R.drawable.rand_links_rood) { KeukenActivity.open(this) }
        }
        val aanmeldingen = start.optInt("aanmeldingen_open")
        if (aanmeldingen > 0) {
            letOp(resources.getQuantityString(R.plurals.aanmeldingen_open, aanmeldingen, aanmeldingen), getString(R.string.controleer_betaling),
                R.drawable.rand_links_oranje) { AanmeldingenActivity.open(this) }
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
        val uitverkocht = start.optJSONArray("uitverkocht_op_tv")?.let { l -> (0 until l.length()).map { l.optString(it) } }.orEmpty()
        if (voorraad && uitverkocht.isNotEmpty()) {
            letOp(resources.getQuantityString(R.plurals.letop_uitverkocht, uitverkocht.size, uitverkocht.size),
                uitverkocht.joinToString(", "), R.drawable.rand_links_oranje) { UitverkochtActivity.open(this) }
        }
        val urgent = start.optInt("mededelingen_urgent")
        if (urgent > 0) {
            letOp(getString(R.string.prikbord_urgent, urgent), getString(R.string.n_open, start.optInt("mededelingen_open")), R.drawable.rand_links_rood) {
                PrikbordActivity.open(this)
            }
        }
        b.letOpKop.isVisible = b.letOpLijst.childCount > 0

        // De andere schermen van de app, per onderwerp, voor zover je er rechten voor hebt.
        b.meerLijst.removeAllViews()
        val voorraadMeer = mutableListOf<Meer>()
        if (voorraad) {
            voorraadMeer += Meer(getString(R.string.bestellijst), R.drawable.ic_bestellijst, bestellingen, false) { BestellijstActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.boodschappen), R.drawable.ic_boodschappen, 0, false) { BoodschappenActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.prognose), R.drawable.ic_prognose, 0, false) { PrognoseActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.tellingen), R.drawable.ic_tellingen, 0, false) { TellingenActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.geschiedenis), R.drawable.ic_geschiedenis, 0, false) { GeschiedenisActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.barcodes), R.drawable.ic_barcodes, 0, false) { BarcodesActivity.open(this) }
        }
        val kantineMeer = mutableListOf<Meer>()
        if (heeft("keuken")) {
            val vetNodig = start.optJSONObject("frituurvet")?.optBoolean("ok") == false
            kantineMeer += Meer(getString(R.string.keuken), R.drawable.ic_keuken, if (vetNodig) 1 else 0, vetNodig, label = "!") { KeukenActivity.open(this) }
        }
        // Met de rechten voor de kantine-tv het hele tv-scherm (met uitverkocht en de timer); anders alleen uitverkocht.
        if (heeft("kantine_tv")) kantineMeer += Meer(getString(R.string.kantine_tv), R.drawable.ic_kiosk, uitverkocht.size, false) { KantineTvActivity.open(this) }
        else if (voorraad) kantineMeer += Meer(getString(R.string.op_de_tv), R.drawable.ic_kiosk, uitverkocht.size, false) { UitverkochtActivity.open(this) }
        val timers = start.optJSONArray("timers")?.length() ?: 0
        kantineMeer += Meer(getString(R.string.timer), R.drawable.ic_timer, timers, false) { TimerActivity.open(this) }
        val geldMeer = mutableListOf<Meer>()
        if (heeft("kassa")) {
            geldMeer += Meer(getString(R.string.kassa), R.drawable.ic_kassa, kassa?.optInt("concepten") ?: 0, false) { GeldActivity.open(this, GeldActivity.KASSA) }
        }
        if (beheerder) geldMeer += Meer(getString(R.string.kluis), R.drawable.ic_kluis, kluis, false) { GeldActivity.open(this, GeldActivity.KLUIS) }
        val clubMeer = mutableListOf<Meer>()
        clubMeer += Meer(getString(R.string.prikbord), R.drawable.ic_prikbord, start.optInt("mededelingen_open"), urgent > 0) { PrikbordActivity.open(this) }
        clubMeer += Meer(getString(R.string.agenda), R.drawable.ic_agenda, 0, false) { AgendaActivity.open(this) }
        if (heeft("club_van_20")) clubMeer += Meer(getString(R.string.club_van_20), R.drawable.ic_aanmeldingen, aanmeldingen, false) { AanmeldingenActivity.open(this) }
        val groepen = listOf(
            R.string.groep_voorraad to voorraadMeer,
            R.string.groep_kantine to kantineMeer,
            R.string.groep_geld to geldMeer,
            R.string.groep_club to clubMeer,
        )
        for ((kop, groep) in groepen) {
            if (groep.isEmpty()) continue
            Lijst.kop(b.meerLijst, getString(kop))
            toonMeer(groep)
        }

        b.standTekst.text = telling?.tekstOfNull("datum")?.let {
            getString(R.string.laatst_geteld, it.take(10).split("-").reversed().joinToString("-"), telling.tekstOfNull("door") ?: "?")
        } ?: ""

        val nieuwste = start.optString("app_versie")
        b.updateMelding.isVisible = nieuwer(nieuwste, BuildConfig.VERSION_NAME)
        b.updateMelding.text = getString(R.string.update_beschikbaar, nieuwste)
    }

    /** Een groep kleine tegels, drie naast elkaar. */
    private fun toonMeer(groep: List<Meer>) {
        groep.chunked(3).forEach { rij ->
            val regel = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            rij.forEach { m ->
                val item = ItemMeerBinding.inflate(LayoutInflater.from(this), regel, false)
                item.meerNaam.text = m.naam
                item.meerIcoon.setImageResource(m.icoon)
                item.meerTeller.isVisible = m.teller > 0
                item.meerTeller.text = m.label ?: m.teller.toString()
                if (m.rood) {
                    item.meerTeller.setBackgroundResource(R.drawable.badge_rood)
                    item.meerTeller.setTextColor(getColor(R.color.wit))
                }
                item.root.setOnClickListener { m.actie() }
                regel.addView(item.root)
            }
            // Lege plekken even breed als een tegel (die heeft 3dp marge rondom), zodat de laatste rij niet breder wordt.
            repeat(3 - rij.size) {
                regel.addView(android.view.View(this), LinearLayout.LayoutParams(0, 1, 1f).apply { setMargins(dp(this@StartActivity, 3), 0, dp(this@StartActivity, 3), 0) })
            }
            b.meerLijst.addView(regel)
        }
    }

    private class Meer(
        val naam: String,
        @DrawableRes val icoon: Int,
        val teller: Int,
        val rood: Boolean,
        val label: String? = null,
        val actie: () -> Unit,
    )

    private fun letOp(titel: String, detail: String, @DrawableRes rand: Int, actie: (() -> Unit)?) {
        val regel = ItemLetopBinding.inflate(LayoutInflater.from(this), b.letOpLijst, false)
        regel.root.setBackgroundResource(rand)
        regel.letOpTitel.text = titel
        regel.letOpDetail.text = detail
        regel.letOpDetail.isVisible = detail.isNotEmpty()
        regel.letOpPijl.isVisible = actie != null
        if (actie != null) regel.root.setOnClickListener { actie() } else regel.root.isClickable = false
        b.letOpLijst.addView(regel.root)
    }

    private fun dagenGeleden(dagen: Int) = when (dagen) {
        0 -> getString(R.string.vandaag_geteld)
        1 -> getString(R.string.gisteren_geteld)
        else -> getString(R.string.dagen_geleden_geteld, dagen)
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
