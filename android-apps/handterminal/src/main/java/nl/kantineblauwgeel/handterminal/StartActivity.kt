package nl.kantineblauwgeel.handterminal

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.annotation.ColorRes
import androidx.annotation.DrawableRes
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import nl.kantineblauwgeel.handterminal.databinding.ActivityStartBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemLetopBinding
import nl.kantineblauwgeel.handterminal.databinding.ItemOnderdeelBinding
import nl.kantineblauwgeel.handterminal.databinding.TegelBinding
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Het startscherm, zoals het overzicht op de site: de groet, zoeken of scannen, de vier dingen van het dagelijkse werk
 * samen op één bord (Factuur inboeken, Tellen, Boeken, Voorraad, elk met zijn stand), wat er nu moet (ook de taken die
 * een beheerder voor je klaarzette) en daaronder alle andere schermen per onderwerp (Voorraad en bestellen, Kantine en
 * keuken, Geld, Club), voor zover je er rechten voor hebt. Alles in de app zelf; de kantine-tv in KantineTvActivity.
 * Toont meteen het vorige antwoord van de site (bewaard op het toestel) en ververst op de achtergrond, ook de
 * productlijst. */
class StartActivity : BasisActivity() {

    private lateinit var b: ActivityStartBinding
    override val isStartscherm = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityStartBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtStartBalkIn(b.balk)
        // Een ingedrukt vak of een regel blijft binnen de hoeken van het paneel.
        b.tegels.clipToOutline = true
        b.letOpPaneel.clipToOutline = true
        b.startGroet.text = getString(R.string.hallo) + (Sessie.naam?.let { ", $it" } ?: "")
        b.startDatum.text = SimpleDateFormat("EEEE d MMMM", Locale("nl", "NL")).format(Date())

        b.zoekKnop.setOnClickListener { ProductenActivity.open(this, ProductenActivity.Modus.ZOEKEN) }
        tegel(b.tegelFactuur, R.drawable.ic_factuur, R.string.tegel_factuur) { startActivity(Intent(this, FacturenActivity::class.java)) }
        tegel(b.tegelTellen, R.drawable.ic_tellen, R.string.tegel_tellen) { startActivity(Intent(this, TellenActivity::class.java)) }
        tegel(b.tegelBoeken, R.drawable.ic_boeken, R.string.tegel_boeken) { ProductenActivity.open(this, ProductenActivity.Modus.BOEKEN) }
        tegel(b.tegelVoorraad, R.drawable.ic_voorraad, R.string.tegel_voorraad) { ProductenActivity.open(this, ProductenActivity.Modus.VOORRAAD) }
        b.verversen.setColorSchemeResources(R.color.blauw_donker)
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

    /** De regel onder de naam van een vak: gewoon zacht, of met [kleur] een stand (een woord met een gekleurde stip). */
    private fun zetTegel(tegel: TegelBinding, sub: String, @ColorRes kleur: Int? = null) {
        if (kleur == null) Lijst.zetZacht(tegel.tegelSub, sub) else Lijst.zetStand(tegel.tegelSub, sub, getColor(kleur))
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
        b.startGroet.text = "${start.optString("groet", getString(R.string.hallo))}, $naam"
        zetAvatar(naam)

        val voorraad = start.optJSONObject("toegang")?.optBoolean("voorraad") ?: true
        b.zoekKnop.isVisible = voorraad
        b.tegels.isVisible = voorraad
        val laag = start.optInt("laag")
        val facturen = start.optInt("open_facturen")
        if (facturen > 0) zetTegel(b.tegelFactuur, getString(R.string.n_bezig, facturen), R.color.oranje)
        else zetTegel(b.tegelFactuur, getString(R.string.dozen_scannen))
        zetTegel(b.tegelBoeken, getString(R.string.erin_of_eruit))
        if (laag > 0) zetTegel(b.tegelVoorraad, getString(R.string.n_onder_minimum, laag), R.color.rood)
        else zetTegel(b.tegelVoorraad, getString(R.string.alles_op_orde), R.color.groen)
        val looplijst = start.optJSONObject("looplijst")
        val telling = start.optJSONObject("telling")
        when {
            looplijst?.optBoolean("in_controle") == true -> zetTegel(b.tegelTellen, getString(R.string.verder_controleren), R.color.oranje)
            looplijst != null -> zetTegel(
                b.tegelTellen,
                getString(
                    R.string.verder_bij,
                    getString(if (looplijst.optString("fase") == "hok") R.string.fase_hok_kort else R.string.fase_bar_kort),
                    looplijst.optInt("nummer"), looplijst.optInt("totaal"),
                ),
                R.color.oranje,
            )
            // Te lang geleden (zoals "Te laat" op het overzicht van de site): rood.
            telling?.has("dagen_geleden") == true && !telling.isNull("dagen_geleden") -> zetTegel(
                b.tegelTellen, dagenGeleden(telling.optInt("dagen_geleden")), if (telling.optBoolean("ok", true)) R.color.groen else R.color.rood,
            )
            else -> zetTegel(b.tegelTellen, getString(R.string.telling_lopen))
        }

        // Wat moet er nu?
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
                R.color.amber,
            ) { BestellijstActivity.open(this) }
        }
        // De timers op de tv's (bijvoorbeeld de gehaktballen): wat er loopt, of wat klaar is.
        start.optJSONArray("timers")?.objecten()?.forEach { t ->
            val klaar = t.optBoolean("klaar")
            letOp(
                if (klaar) getString(R.string.letop_timer_klaar, t.optString("naam"))
                else getString(R.string.letop_timer_loopt, t.optString("naam"), t.optString("klaar_om")),
                getString(R.string.letop_timer_detail),
                if (klaar) R.color.amber else R.color.blauw,
            ) { TimerActivity.open(this) }
        }
        // Taken die een beheerder voor jou klaarzette: een eigen scherm met de stappen en afronden.
        start.optJSONArray("taken")?.objecten()?.forEach { t ->
            val rand = if (t.optBoolean("urgent")) R.color.rood else R.color.amber
            if (t.has("id")) letOp(t.optString("titel"), t.optString("detail"), rand) { TaakActivity.open(this, t.getInt("id")) }
            else letOp(t.optString("titel"), t.optString("detail"), rand, null)
        }
        val kassa = start.optJSONObject("kassa")
        if (kassa != null) {
            val concepten = kassa.optInt("concepten")
            if (concepten > 0) {
                letOp(resources.getQuantityString(R.plurals.kassatellingen_goedkeuren, concepten, concepten), getString(R.string.controleer_en_keur_goed),
                    R.color.amber) { GeldActivity.open(this, GeldActivity.KASSA) }
            } else if (kassa.optString("status") == "rood") {
                letOp(getString(R.string.kassa_tellen), kassa.optString("tekst"), R.color.rood) { GeldActivity.open(this, GeldActivity.KASSA) }
            }
        }
        val kluis = start.optInt("kluis_concepten")
        if (beheerder && kluis > 0) {
            letOp(resources.getQuantityString(R.plurals.kluistellingen_goedkeuren, kluis, kluis), getString(R.string.controleer_en_keur_goed),
                R.color.amber) { GeldActivity.open(this, GeldActivity.KLUIS) }
        }
        start.optJSONObject("frituurvet")?.takeIf { !it.optBoolean("ok") }?.let { vet ->
            letOp(getString(R.string.frituurvet_vervangen), if (vet.isNull("dagen_geleden")) getString(R.string.frituurvet_nooit)
                else getString(R.string.frituurvet_dagen, vet.optInt("dagen_geleden")), R.color.rood) { KeukenActivity.open(this) }
        }
        val aanmeldingen = start.optInt("aanmeldingen_open")
        if (aanmeldingen > 0) {
            letOp(resources.getQuantityString(R.plurals.aanmeldingen_open, aanmeldingen, aanmeldingen), getString(R.string.controleer_betaling),
                R.color.amber) { AanmeldingenActivity.open(this) }
        }
        if (voorraad && laag > 0) {
            letOp(resources.getQuantityString(R.plurals.onder_minimum, laag, laag), getString(R.string.bekijk_welke), R.color.rood) {
                ProductenActivity.open(this, ProductenActivity.Modus.VOORRAAD, alleenLaag = true)
            }
        }
        val bestellingen = start.optInt("open_bestellingen")
        if (voorraad && bestellingen > 0) {
            letOp(resources.getQuantityString(R.plurals.bestellingen_inboeken, bestellingen, bestellingen), getString(R.string.scan_de_levering), R.color.amber) {
                startActivity(Intent(this, FacturenActivity::class.java))
            }
        }
        val uitverkocht = start.optJSONArray("uitverkocht_op_tv")?.let { l -> (0 until l.length()).map { l.optString(it) } }.orEmpty()
        if (voorraad && uitverkocht.isNotEmpty()) {
            letOp(resources.getQuantityString(R.plurals.letop_uitverkocht, uitverkocht.size, uitverkocht.size),
                uitverkocht.joinToString(", "), R.color.amber) { UitverkochtActivity.open(this) }
        }
        val urgent = start.optInt("mededelingen_urgent")
        if (urgent > 0) {
            letOp(getString(R.string.prikbord_urgent, urgent), getString(R.string.n_open, start.optInt("mededelingen_open")), R.color.rood) {
                PrikbordActivity.open(this)
            }
        }
        val taken = b.letOpLijst.childCount
        b.letOpPaneel.isVisible = taken > 0
        b.letOpAantal.text = resources.getQuantityString(R.plurals.n_taken, taken, taken)

        // De andere schermen van de app, per onderwerp: een vak per onderwerp, dat een blad met de onderdelen opent
        // (zie openOnderwerp). Alleen wat bij je rechten hoort.
        fun aantal(id: Int, n: Int) = if (n > 0) resources.getQuantityString(id, n, n) else null
        val voorraadMeer = mutableListOf<Meer>()
        if (voorraad) {
            voorraadMeer += Meer(getString(R.string.bestellijst), getString(R.string.uitleg_bestellijst), R.drawable.ic_bestellijst,
                aantal(R.plurals.stand_in_te_boeken, bestellingen)) { BestellijstActivity.open(this) }
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
                R.drawable.ic_keuken, if (vetNodig) getString(R.string.stand_frituurvet) else null, rood = true) { KeukenActivity.open(this) }
        }
        // Met de rechten voor de kantine-tv het hele tv-scherm (met uitverkocht en de timer); anders alleen uitverkocht.
        if (heeft("kantine_tv")) {
            kantineMeer += Meer(getString(R.string.kantine_tv), getString(R.string.uitleg_kantine_tv), R.drawable.ic_kiosk,
                aantal(R.plurals.n_uitverkocht, uitverkocht.size)) { KantineTvActivity.open(this) }
        } else if (voorraad) {
            kantineMeer += Meer(getString(R.string.op_de_tv), getString(R.string.uitleg_op_de_tv), R.drawable.ic_kiosk,
                aantal(R.plurals.n_uitverkocht, uitverkocht.size)) { UitverkochtActivity.open(this) }
        }
        val timers = start.optJSONArray("timers")?.length() ?: 0
        kantineMeer += Meer(getString(R.string.timer), getString(R.string.uitleg_timer), R.drawable.ic_timer,
            aantal(R.plurals.stand_timers, timers)) { TimerActivity.open(this) }
        val geldMeer = mutableListOf<Meer>()
        if (heeft("kassa")) {
            geldMeer += Meer(getString(R.string.kassa), getString(R.string.uitleg_kassa), R.drawable.ic_kassa,
                aantal(R.plurals.stand_te_keuren, kassa?.optInt("concepten") ?: 0)) { GeldActivity.open(this, GeldActivity.KASSA) }
        }
        if (beheerder) geldMeer += Meer(getString(R.string.kluis), getString(R.string.uitleg_kluis), R.drawable.ic_kluis,
            aantal(R.plurals.stand_te_keuren, kluis)) { GeldActivity.open(this, GeldActivity.KLUIS) }
        val clubMeer = mutableListOf<Meer>()
        clubMeer += Meer(getString(R.string.prikbord), getString(R.string.uitleg_prikbord), R.drawable.ic_prikbord,
            aantal(R.plurals.stand_open, start.optInt("mededelingen_open")), urgent > 0) { PrikbordActivity.open(this) }
        clubMeer += Meer(getString(R.string.agenda), getString(R.string.uitleg_agenda), R.drawable.ic_agenda) { AgendaActivity.open(this) }
        if (heeft("club_van_20")) clubMeer += Meer(getString(R.string.club_van_20), getString(R.string.uitleg_club_van_20), R.drawable.ic_aanmeldingen,
            aantal(R.plurals.stand_open, aanmeldingen)) { AanmeldingenActivity.open(this) }
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

    /** Een schermpje van de app onder een onderwerp, met eventueel een [stand] ("4 in te boeken", rood als [rood]). */
    private class Meer(
        val naam: String,
        val uitleg: String,
        @DrawableRes val icoon: Int,
        val stand: String? = null,
        val rood: Boolean = false,
        val actie: () -> Unit,
    ) {
        @get:ColorRes val kleur get() = if (rood) R.color.rood else R.color.oranje
    }

    private class Onderwerp(val naam: String, @DrawableRes val icoon: Int, val onderdelen: List<Meer>) {
        /** Wat er het eerst aandacht vraagt (iets dringends gaat voor). */
        val belangrijkste get() = onderdelen.filter { it.stand != null }.minByOrNull { if (it.rood) 0 else 1 }
    }

    /** Een bord (een paneel met vakken, twee naast elkaar en een oneven laatste over de hele breedte), zoals bovenaan het
     * startscherm. */
    private fun bord(ouder: LinearLayout): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundResource(R.drawable.kaart)
        dividerDrawable = getDrawable(R.drawable.scheiding)
        showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
        clipToOutline = true
        ouder.addView(this)
    }

    private fun bordRij(bord: LinearLayout): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        dividerDrawable = getDrawable(R.drawable.scheiding_staand)
        showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
        bord.addView(this)
    }

    /** De onderwerpen als vakken op een bord, met de onderdelen eronder in het klein; vraagt een onderdeel aandacht, dan
     * staat daar zijn stand (zoals "4 in te boeken" bij Voorraad en bestellen). */
    private fun toonOnderwerpen(onderwerpen: List<Onderwerp>) {
        b.meerLijst.removeAllViews()
        val zichtbaar = onderwerpen.filter { it.onderdelen.isNotEmpty() }
        if (zichtbaar.isEmpty()) return
        Lijst.kop(b.meerLijst, getString(R.string.meer))
        val bord = bord(b.meerLijst)
        zichtbaar.chunked(2).forEach { paar ->
            val rij = bordRij(bord)
            paar.forEach { o ->
                val t = TegelBinding.inflate(LayoutInflater.from(this), rij, false)
                t.tegelIcoon.setImageResource(o.icoon)
                t.tegelNaam.text = o.naam
                t.root.setOnClickListener { openOnderwerp(o) }
                val m = o.belangrijkste
                if (m != null) zetTegel(t, m.stand ?: "", m.kleur) else zetTegel(t, o.onderdelen.joinToString(", ") { it.naam })
                rij.addView(t.root)
            }
        }
    }

    /** Een onderwerp openen: een blad dat van onderen omhoog schuift (zie [Blad]), met de onderdelen op een bord.
     * Heeft het maar één onderdeel (bijvoorbeeld alleen de kassa), dan meteen dat scherm. */
    private fun openOnderwerp(o: Onderwerp) {
        if (o.onderdelen.size == 1) return o.onderdelen[0].actie()
        Blad.toon(this, o.naam, resources.getQuantityString(R.plurals.n_onderdelen, o.onderdelen.size, o.onderdelen.size), o.icoon) { inhoud, blad ->
            val bord = bord(inhoud)
            o.onderdelen.chunked(2).forEach { paar ->
                val rij = bordRij(bord)
                paar.forEach { m ->
                    val vak = ItemOnderdeelBinding.inflate(layoutInflater, rij, false)
                    vak.onderdeelIcoon.setImageResource(m.icoon)
                    vak.onderdeelNaam.text = m.naam
                    vak.onderdeelUitleg.text = m.uitleg
                    vak.onderdeelTeller.isVisible = m.stand != null
                    m.stand?.let { Lijst.zetStand(vak.onderdeelTeller, it, getColor(m.kleur)) }
                    vak.root.setOnClickListener {
                        blad.sluit()
                        m.actie()
                    }
                    rij.addView(vak.root)
                }
            }
        }
    }

    /** Een regel onder "Wat moet er nu?", met links een streep in [streep] (rood: dringend, geel: straks, blauw: loopt). */
    private fun letOp(titel: String, detail: String, @ColorRes streep: Int, actie: (() -> Unit)?) {
        val regel = ItemLetopBinding.inflate(LayoutInflater.from(this), b.letOpLijst, false)
        regel.letOpStreep.background = GradientDrawable().apply {
            cornerRadius = dp(this@StartActivity, 2).toFloat()
            setColor(getColor(streep))
        }
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
