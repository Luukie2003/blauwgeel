package nl.kantineblauwgeel.handterminal

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.WindowManager
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.annotation.DrawableRes
import androidx.appcompat.app.AppCompatDialog
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import nl.kantineblauwgeel.handterminal.databinding.ActivityStartBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemLetopBinding
import nl.kantineblauwgeel.handterminal.databinding.DialogOnderwerpBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemOnderdeelBinding
import nl.kantineblauwgeel.handterminal.databinding.TegelBinding
import kotlinx.coroutines.launch
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
        openGevraagd(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        openGevraagd(intent)
    }

    /** Vanuit een notificatie (zie Herinneringen.kt), na het inloggen: meteen door naar de bestellijst. */
    private fun openGevraagd(intent: Intent?) {
        if (intent?.getStringExtra(InlogActivity.EXTRA_OPEN) == InlogActivity.OPEN_BESTELLIJST) {
            intent.removeExtra(InlogActivity.EXTRA_OPEN)
            BestellijstActivity.open(this)
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
                planHerinneringen(start.optJSONArray("bestelmomenten"))
                warmOp(start)
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

    /** Het voorspelmodel op de site alvast laten rekenen (/voorspelling/opwarmen): na een nieuwe telling rekent het dan
     * op de achtergrond, en hoeft niemand bij de bestellijst of een product te wachten. Staat het al klaar, dan kost het
     * bijna niets. Hooguit eens per 10 minuten, en maar één poging: lukt het niet, dan rekent de pagina het zelf. */
    private fun warmOp(start: JSONObject) {
        if (start.optJSONObject("toegang")?.optBoolean("voorraad") != true) return
        val nu = System.currentTimeMillis()
        if (nu - laatsteOpwarmen < OPWARMEN_ELKE_MS) return
        laatsteOpwarmen = nu
        lifecycleScope.launch {
            try {
                Api.get(this@StartActivity, "/voorspelling/opwarmen", pogingen = 1)
            } catch (e: Exception) {
                // Niet erg: dan rekent de pagina die het nodig heeft het zelf.
            }
        }
    }

    /** De herinneringen om te bestellen bijwerken (zie Herinneringen.kt). Vanaf Android 13 is er toestemming nodig voor
     * een notificatie: die vragen we één keer, zodra er iets te herinneren is. */
    private fun planHerinneringen(momenten: org.json.JSONArray?) {
        Herinneringen.plan(this, momenten)
        if (Build.VERSION.SDK_INT >= 33 && (momenten?.length() ?: 0) > 0 && inst.bestelHerinnering &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            !inst.meldingenGevraagd
        ) {
            inst.meldingenGevraagd = true
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
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
        // Bestellen: het uiterste bestelmoment van een leverancier komt eraan (vanaf de herinnering tot het moment zelf).
        val nu = System.currentTimeMillis()
        start.optJSONArray("bestelmomenten")?.objecten()?.forEach { m ->
            val herinnering = Herinneringen.tijd(m.tekstOfNull("herinnering")) ?: return@forEach
            val uiterst = Herinneringen.tijd(m.tekstOfNull("uiterst")) ?: return@forEach
            if (m.optBoolean("al_besteld") || nu < herinnering || nu >= uiterst) return@forEach
            val aantal = m.optInt("aantal")
            letOp(
                getString(R.string.letop_bestellen, Herinneringen.wanneerTekst(this, uiterst, m.optString("uiterst_tekst"))
                    .replaceFirstChar { it.uppercase() }, m.optString("tijd"), m.optString("leverancier")),
                getString(R.string.letop_bestellen_detail,
                    if (aantal > 0) resources.getQuantityString(R.plurals.n_producten_klaar, aantal, aantal) else getString(R.string.letop_bestellen_niets),
                    m.optString("levering_tekst")),
                R.drawable.rand_links_oranje,
            ) { BestellijstActivity.open(this) }
        }
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

        // De andere schermen van de app, per onderwerp: een tegel per onderwerp, die een blad met de onderdelen opent
        // (zie openOnderwerp). Alleen wat bij je rechten hoort.
        val voorraadMeer = mutableListOf<Meer>()
        if (voorraad) {
            voorraadMeer += Meer(getString(R.string.bestellijst), getString(R.string.uitleg_bestellijst), R.drawable.ic_bestellijst, bestellingen) { BestellijstActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.boodschappen), getString(R.string.uitleg_boodschappen), R.drawable.ic_boodschappen) { BoodschappenActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.prognose), getString(R.string.uitleg_prognose), R.drawable.ic_prognose) { PrognoseActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.tellingen), getString(R.string.uitleg_tellingen), R.drawable.ic_tellingen) { TellingenActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.geschiedenis), getString(R.string.uitleg_geschiedenis), R.drawable.ic_geschiedenis) { GeschiedenisActivity.open(this) }
            voorraadMeer += Meer(getString(R.string.barcodes), getString(R.string.uitleg_barcodes), R.drawable.ic_barcodes) { BarcodesActivity.open(this) }
        }
        val kantineMeer = mutableListOf<Meer>()
        if (heeft("keuken")) {
            val vetNodig = start.optJSONObject("frituurvet")?.optBoolean("ok") == false
            kantineMeer += Meer(getString(R.string.keuken), getString(if (vetNodig) R.string.uitleg_keuken_vet else R.string.uitleg_keuken),
                R.drawable.ic_keuken, if (vetNodig) 1 else 0, vetNodig, label = "!") { KeukenActivity.open(this) }
        }
        // Met de rechten voor de kantine-tv het hele tv-scherm (met uitverkocht en de timer); anders alleen uitverkocht.
        if (heeft("kantine_tv")) {
            kantineMeer += Meer(getString(R.string.kantine_tv), getString(R.string.uitleg_kantine_tv), R.drawable.ic_kiosk, uitverkocht.size) { KantineTvActivity.open(this) }
        } else if (voorraad) {
            kantineMeer += Meer(getString(R.string.op_de_tv), getString(R.string.uitleg_op_de_tv), R.drawable.ic_kiosk, uitverkocht.size) { UitverkochtActivity.open(this) }
        }
        val timers = start.optJSONArray("timers")?.length() ?: 0
        kantineMeer += Meer(getString(R.string.timer), getString(R.string.uitleg_timer), R.drawable.ic_timer, timers) { TimerActivity.open(this) }
        val geldMeer = mutableListOf<Meer>()
        if (heeft("kassa")) {
            geldMeer += Meer(getString(R.string.kassa), getString(R.string.uitleg_kassa), R.drawable.ic_kassa, kassa?.optInt("concepten") ?: 0) { GeldActivity.open(this, GeldActivity.KASSA) }
        }
        if (beheerder) geldMeer += Meer(getString(R.string.kluis), getString(R.string.uitleg_kluis), R.drawable.ic_kluis, kluis) { GeldActivity.open(this, GeldActivity.KLUIS) }
        val clubMeer = mutableListOf<Meer>()
        clubMeer += Meer(getString(R.string.prikbord), getString(R.string.uitleg_prikbord), R.drawable.ic_prikbord, start.optInt("mededelingen_open"), urgent > 0) { PrikbordActivity.open(this) }
        clubMeer += Meer(getString(R.string.agenda), getString(R.string.uitleg_agenda), R.drawable.ic_agenda) { AgendaActivity.open(this) }
        if (heeft("club_van_20")) clubMeer += Meer(getString(R.string.club_van_20), getString(R.string.uitleg_club_van_20), R.drawable.ic_aanmeldingen, aanmeldingen) { AanmeldingenActivity.open(this) }
        toonOnderwerpen(listOf(
            Onderwerp(getString(R.string.groep_voorraad), R.drawable.ic_voorraad, voorraadMeer),
            Onderwerp(getString(R.string.groep_kantine), R.drawable.ic_keuken, kantineMeer),
            Onderwerp(getString(R.string.groep_geld), R.drawable.ic_kassa, geldMeer),
            Onderwerp(getString(R.string.groep_club), R.drawable.ic_prikbord, clubMeer),
        ))

        b.standTekst.text = telling?.tekstOfNull("datum")?.let {
            getString(R.string.laatst_geteld, it.take(10).split("-").reversed().joinToString("-"), telling.tekstOfNull("door") ?: "?")
        } ?: ""

        val nieuwste = start.optString("app_versie")
        b.updateMelding.isVisible = nieuwer(nieuwste, BuildConfig.VERSION_NAME)
        b.updateMelding.text = getString(R.string.update_beschikbaar, nieuwste)
    }

    /** Een schermpje van de app onder een onderwerp. [teller]: een getal op de kaart (rood als [rood]), of [label]. */
    private class Meer(
        val naam: String,
        val uitleg: String,
        @DrawableRes val icoon: Int,
        val teller: Int = 0,
        val rood: Boolean = false,
        val label: String? = null,
        val actie: () -> Unit,
    )

    private class Onderwerp(val naam: String, @DrawableRes val icoon: Int, val onderdelen: List<Meer>) {
        val teller get() = onderdelen.sumOf { it.teller }
        val rood get() = onderdelen.any { it.rood && it.teller > 0 }
    }

    /** De onderwerpen als tegels, twee naast elkaar: met de onderdelen eronder in het klein, en het totaal van de
     * tellers (rood als er iets dringends bij zit). */
    private fun toonOnderwerpen(onderwerpen: List<Onderwerp>) {
        b.meerLijst.removeAllViews()
        val zichtbaar = onderwerpen.filter { it.onderdelen.isNotEmpty() }
        if (zichtbaar.isEmpty()) return
        Lijst.kop(b.meerLijst, getString(R.string.meer))
        zichtbaar.chunked(2).forEach { paar ->
            val rij = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            paar.forEach { o ->
                val t = TegelBinding.inflate(LayoutInflater.from(this), rij, false)
                t.tegelIcoon.setImageResource(o.icoon)
                t.tegelNaam.text = o.naam
                t.root.setOnClickListener { openOnderwerp(o) }
                zetTegel(t, o.onderdelen.joinToString(", ") { it.naam }, o.teller, rood = o.rood)
                rij.addView(t.root)
            }
            // Een lege plek even breed als een tegel (die heeft 4dp marge rondom), zodat de laatste rij niet breder wordt.
            if (paar.size == 1) {
                rij.addView(android.view.View(this), LinearLayout.LayoutParams(0, 1, 1f).apply { setMargins(dp(this@StartActivity, 4), 0, dp(this@StartActivity, 4), 0) })
            }
            b.meerLijst.addView(rij)
        }
    }

    /** Een onderwerp openen: een blad dat van onderen omhoog schuift, met de onderdelen als kaarten. Dicht met terug,
     * door ernaast te tikken of door de kop omlaag te vegen. Heeft het maar één onderdeel (bijvoorbeeld alleen de
     * kassa), dan meteen dat scherm. */
    @SuppressLint("ClickableViewAccessibility")  // vegen is een extra; terug en ernaast tikken werken ook
    private fun openOnderwerp(o: Onderwerp) {
        if (o.onderdelen.size == 1) return o.onderdelen[0].actie()
        val blad = DialogOnderwerpBinding.inflate(layoutInflater)
        val dialoog = AppCompatDialog(this, R.style.Blad)
        blad.bladIcoon.setImageResource(o.icoon)
        blad.bladTitel.text = o.naam
        blad.bladSub.text = resources.getQuantityString(R.plurals.n_onderdelen, o.onderdelen.size, o.onderdelen.size)
        o.onderdelen.chunked(2).forEach { paar ->
            val rij = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            paar.forEach { m ->
                val kaart = ItemOnderdeelBinding.inflate(layoutInflater, rij, false)
                kaart.onderdeelIcoon.setImageResource(m.icoon)
                kaart.onderdeelNaam.text = m.naam
                kaart.onderdeelUitleg.text = m.uitleg
                kaart.onderdeelTeller.isVisible = m.teller > 0
                kaart.onderdeelTeller.text = m.label ?: m.teller.toString()
                if (m.rood) {
                    kaart.onderdeelTeller.setBackgroundResource(R.drawable.badge_rood)
                    kaart.onderdeelTeller.setTextColor(getColor(R.color.wit))
                }
                kaart.root.setOnClickListener {
                    dialoog.dismiss()
                    m.actie()
                }
                rij.addView(kaart.root)
            }
            if (paar.size == 1) {
                rij.addView(android.view.View(this), LinearLayout.LayoutParams(0, 1, 1f).apply { setMargins(dp(this@StartActivity, 5), 0, dp(this@StartActivity, 5), 0) })
            }
            blad.bladLijst.addView(rij)
        }
        // De kop omlaag vegen: het blad gaat mee, en verder dan een kwart is dicht.
        var beginY = 0f
        // Eén keer sluiten: tijdens dismiss() krijgt de kop zelf nog een ACTION_CANCEL (het venster gaat weg), nog voordat
        // isShowing false is. Twee keer dismiss() laat de app vastlopen.
        var gesloten = false
        blad.bladKop.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> beginY = e.rawY
                MotionEvent.ACTION_MOVE -> if (!gesloten) blad.root.translationY = maxOf(0f, e.rawY - beginY)
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> when {
                    gesloten -> Unit
                    blad.root.translationY > blad.root.height / 4f -> {
                        gesloten = true
                        dialoog.dismiss()
                    }
                    else -> blad.root.animate().translationY(0f).setDuration(150).start()
                }
            }
            true
        }
        dialoog.setContentView(blad.root)
        dialoog.setCanceledOnTouchOutside(true)
        dialoog.window?.apply {
            setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT)
            setGravity(Gravity.BOTTOM)
        }
        tril(15)
        dialoog.show()
    }

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
        private const val OPWARMEN_ELKE_MS = 10 * 60_000L
        /** Wanneer de app het voorspelmodel voor het laatst liet rekenen (zie warmOp); voor het hele proces. */
        private var laatsteOpwarmen = 0L

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
