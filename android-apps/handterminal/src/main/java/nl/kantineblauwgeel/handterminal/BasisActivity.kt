package nl.kantineblauwgeel.handterminal

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.KeyEvent
import android.view.Menu
import android.view.MotionEvent
import android.view.View
import android.widget.PopupMenu
import android.widget.Toast
import androidx.annotation.ColorRes
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.BalkBinding
import org.json.JSONObject

/** Wat elk scherm van de app gemeen heeft:
 * - de kopbalk (titel, wie er is ingelogd, de verbindingsstip en het menu);
 * - de scanner: een scan komt binnen in [bijScan]; standaard opent die het product (of het koppelen van een
 *   onbekende barcode), een scherm kan dat zelf anders doen;
 * - automatisch uitloggen na een tijd niets doen (iedereen gebruikt dezelfde handterminal met een eigen code);
 * - de wifi op volle kracht zolang de app voorin staat;
 * - foutmeldingen: sessie verlopen of noodstop gaat terug naar het inlogscherm, de rest wordt kort gemeld. */
abstract class BasisActivity : AppCompatActivity() {

    protected lateinit var inst: Instellingen
    private lateinit var verbinding: Verbinding
    private var scanOntvanger: BroadcastReceiver? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var balk: BalkBinding? = null
    private var balkSub: String? = null
    private var laatsteOpslag = 0L
    private val hoofdThread = Handler(Looper.getMainLooper())

    /** Is er nu netwerk (wifi of mobiel)? */
    protected var verbonden = true
        private set

    /** Het inlogscherm en de instellingen kunnen zonder ingelogd te zijn. */
    protected open val vereistInlog = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        inst = Instellingen(this)
        Sessie.laad(this)
        Catalogus.laad(this)
        verbinding = Verbinding(this) { bijVerbinding(it) }
        val wifi = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        wifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "kantine:handterminal").apply {
            setReferenceCounted(false)
        }
    }

    override fun onResume() {
        super.onResume()
        if (vereistInlog && !Sessie.isIngelogd(this)) {
            val verlopen = Sessie.naam != null && inst.isVerlopen()
            naarInlog(if (verlopen) getString(R.string.uitgelogd_automatisch, inst.uitlogMinuten) else null)
            return
        }
        verbinding.start()
        bijVerbinding(verbinding.huidig())
        scanOntvanger = Scanner.luister(this) { code, _ ->
            hoofdThread.post {
                activiteit()
                bijScan(code)
            }
        }
        wifiLock?.acquire()
        hoofdThread.postDelayed(inactiviteitTik, 30_000)
    }

    override fun onPause() {
        super.onPause()
        scanOntvanger?.let { unregisterReceiver(it) }
        scanOntvanger = null
        verbinding.stop()
        if (wifiLock?.isHeld == true) wifiLock?.release()
        hoofdThread.removeCallbacks(inactiviteitTik)
    }

    // ---------------------------------------------------------------- automatisch uitloggen

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        if (ev.actionMasked == MotionEvent.ACTION_DOWN) activiteit()
        return super.dispatchTouchEvent(ev)
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        activiteit()
        return super.dispatchKeyEvent(event)
    }

    fun activiteit(direct: Boolean = false) {
        val nu = System.currentTimeMillis()
        if (direct || nu - laatsteOpslag > 5_000) {
            inst.laatsteActiviteit = nu
            laatsteOpslag = nu
        }
    }

    private val inactiviteitTik = object : Runnable {
        override fun run() {
            if (vereistInlog && Sessie.naam != null && inst.isVerlopen()) {
                naarInlog(getString(R.string.uitgelogd_automatisch, inst.uitlogMinuten))
            } else {
                hoofdThread.postDelayed(this, 30_000)
            }
        }
    }

    /** Uitloggen en terug naar het inlogscherm, met alle andere schermen weg. */
    fun naarInlog(melding: String?) {
        Sessie.wis(this)
        startActivity(
            Intent(this, InlogActivity::class.java)
                .putExtra(InlogActivity.EXTRA_MELDING, melding)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        finish()
    }

    // ---------------------------------------------------------------- de kopbalk

    protected fun richtBalkIn(balk: BalkBinding, titel: String, sub: String? = Sessie.naam, terug: Boolean = true) {
        this.balk = balk
        balk.balkTitel.text = titel
        balk.balkTerug.isVisible = terug
        balk.balkLogo.isVisible = !terug
        balk.balkTerug.setOnClickListener { onBackPressedDispatcher.onBackPressed() }
        balk.balkMenu.setOnClickListener { toonMenu(it) }
        zetBalkSub(sub)
    }

    protected fun zetBalkTitel(titel: String) {
        balk?.balkTitel?.text = titel
    }

    protected fun zetBalkSub(sub: String?) {
        balkSub = sub
        werkBalkBij()
    }

    private fun werkBalkBij() {
        val b = balk ?: return
        val tekst = if (!verbonden) getString(R.string.balk_offline) else balkSub
        b.balkSub.text = tekst
        b.balkSub.isVisible = !tekst.isNullOrEmpty()
        b.balkSub.setTextColor(ContextCompat.getColor(this, if (verbonden) R.color.tekst_zacht_op_navy else R.color.oranje))
        kleurStip(b.balkStip, if (verbonden) R.color.groen else R.color.rood)
    }

    fun kleurStip(stip: View, @ColorRes kleur: Int) {
        (stip.background.mutate() as? GradientDrawable)?.setColor(ContextCompat.getColor(this, kleur))
    }

    private fun bijVerbinding(toestand: Verbinding.Toestand) {
        val was = verbonden
        verbonden = toestand.verbonden
        werkBalkBij()
        verbindingGewijzigd(toestand)
        if (verbonden && !was) weerVerbonden()
    }

    /** Elke keer dat de verbinding (of de wifi-sterkte) verandert. */
    protected open fun verbindingGewijzigd(toestand: Verbinding.Toestand) {}

    /** Het netwerk is terug: een scherm kan dan zijn gegevens opnieuw ophalen. */
    protected open fun weerVerbonden() {}

    /** Extra menu-items van een scherm (id's vanaf 100); [bijMenu] handelt ze af. */
    protected open fun vulMenu(menu: Menu) {}

    protected open fun bijMenu(id: Int): Boolean = false

    protected open val isStartscherm = false

    private fun toonMenu(anker: View) {
        val popup = PopupMenu(this, anker)
        vulMenu(popup.menu)
        if (!isStartscherm) popup.menu.add(0, 1, 50, R.string.menu_start)
        if (Scanner.isAanwezig(this)) popup.menu.add(0, 2, 51, R.string.menu_scannen)
        popup.menu.add(0, 3, 52, R.string.menu_verbinding)
        popup.menu.add(0, 4, 53, R.string.menu_instellingen)
        popup.menu.add(0, 5, 54, getString(R.string.menu_uitloggen) + (Sessie.naam?.let { " ($it)" } ?: ""))
        popup.setOnMenuItemClickListener {
            when (it.itemId) {
                1 -> startActivity(Intent(this, StartActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
                2 -> Scanner.startScan(this)
                3 -> testVerbinding()
                4 -> startActivity(Intent(this, InstellingenActivity::class.java))
                5 -> naarInlog(getString(R.string.uitgelogd))
                else -> bijMenu(it.itemId)
            }
            true
        }
        popup.show()
    }

    // ---------------------------------------------------------------- scannen

    /** Een scan van de Zebra-scanner. Standaard: het product openen, of het koppelen van een onbekende barcode. */
    open fun bijScan(code: String) = openScan(code)

    private var scanZoeken: Job? = null

    fun openScan(code: String) {
        tril()
        // Een QR-code van de site (zoals op een schaplabel: /scan/12): het product openen in de app.
        val link = Uri.parse(code)
        if ((link.scheme == "https" || link.scheme == "http") && link.host?.endsWith(inst.siteHost.removePrefix("www.")) == true) {
            val id = Regex("^/(?:scan|producten)/(\\d+)").find(link.path ?: "")?.groupValues?.get(1)?.toIntOrNull()
            if (id != null) ProductActivity.open(this, id) else melding(getString(R.string.qr_niet_voor_app))
            return
        }
        Catalogus.opBarcode(code)?.let {
            ProductActivity.open(this, it.product.id, scan = it.barcode.code)
            return
        }
        if (Catalogus.normaliseerCode(code) == null) {
            melding(getString(R.string.scan_geen_barcode, code))
            return
        }
        // Onbekend op het toestel: misschien is hij net op een ander toestel gekoppeld. Eerst de lijst verversen.
        scanZoeken?.cancel()
        scanZoeken = lifecycleScope.launch {
            try {
                Catalogus.ververs(this@BasisActivity)
            } catch (e: Api.Fout) {
                // Geen verbinding: dan gewoon met wat we hebben.
            }
            val treffer = Catalogus.opBarcode(code)
            if (treffer != null) ProductActivity.open(this@BasisActivity, treffer.product.id, scan = treffer.barcode.code)
            else KoppelenActivity.open(this@BasisActivity, code)
        }
    }

    fun tril(ms: Long = 35) {
        if (!inst.trillen) return
        val trilmotor = getSystemService(VIBRATOR_SERVICE) as? Vibrator ?: return
        if (Build.VERSION.SDK_INT >= 26) {
            trilmotor.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            trilmotor.vibrate(ms)
        }
    }

    // ---------------------------------------------------------------- fouten en meldingen

    fun melding(tekst: String, lang: Boolean = false) {
        Toast.makeText(this, tekst, if (lang) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
    }

    /** Een fout van de site: niet meer ingelogd of noodstop gaat naar het inlogscherm, de rest wordt gemeld. */
    fun toonFout(fout: Throwable) {
        val f = fout as? Api.Fout ?: Api.Fout(Api.Soort.SERVER, fout.message ?: getString(R.string.fout_server_kort))
        when (f.soort) {
            Api.Soort.NIET_INGELOGD -> naarInlog(getString(R.string.uitgelogd_sessie))
            Api.Soort.NOODSTOP -> naarInlog(f.message)
            else -> {
                tril(150)
                melding(f.message ?: getString(R.string.fout_server_kort), lang = true)
            }
        }
    }

    /** Iets op de achtergrond doen (ophalen, opslaan); een fout van de site wordt netjes gemeld. */
    fun bezig(blok: suspend () -> Unit): Job = lifecycleScope.launch {
        try {
            blok()
        } catch (f: Api.Fout) {
            toonFout(f)
        }
    }

    /** Meet drie keer hoe snel de site antwoordt, en vertelt in gewone taal hoe het ervoor staat. */
    fun testVerbinding() {
        val dialoog = AlertDialog.Builder(this)
            .setTitle(R.string.test_titel)
            .setMessage(R.string.test_bezig)
            .setPositiveButton(R.string.sluiten, null)
            .show()
        val t = verbinding.huidig()
        lifecycleScope.launch {
            val tijden = mutableListOf<Long>()
            var versie: String? = null
            repeat(3) {
                try {
                    val (ms, v) = Api.meet(applicationContext)
                    tijden += ms
                    versie = v ?: versie
                } catch (e: Exception) {
                }
            }
            if (!dialoog.isShowing) return@launch
            val netwerk = when (t.soort) {
                Verbinding.Soort.WIFI -> if (t.signaal != null && t.dbm != null) {
                    getString(R.string.test_wifi, signaalWoord(t.signaal), t.dbm)
                } else getString(R.string.verbonden_wifi)
                Verbinding.Soort.MOBIEL -> getString(R.string.test_mobiel)
                Verbinding.Soort.GEEN -> getString(R.string.test_geen)
            }
            val regels = mutableListOf(getString(R.string.test_netwerk, netwerk))
            if (tijden.isEmpty()) {
                regels += getString(R.string.test_website_fout)
                regels += ""
                regels += getString(R.string.test_oordeel_fout)
            } else {
                val gemiddeld = maxOf(1, tijden.average().toInt())
                regels += getString(R.string.test_website_ok, gemiddeld)
                versie?.let { regels += getString(R.string.test_versie, it) }
                regels += ""
                regels += getString(if (gemiddeld > 1500 || tijden.size < 3) R.string.test_oordeel_traag else R.string.test_oordeel_goed)
            }
            dialoog.setMessage(regels.joinToString("\n"))
        }
    }

    /** Een titel voor een venster die niet wordt afgekapt (de standaardtitel past maar twee regels). */
    fun dialoogTitel(tekst: String) = android.widget.TextView(this).apply {
        text = tekst
        textSize = 18f
        setTextColor(getColor(R.color.tekst))
        setTypeface(typeface, android.graphics.Typeface.BOLD)
        setPadding(dp(context, 24), dp(context, 20), dp(context, 24), dp(context, 4))
    }

    /** Iets wat alleen op de website kan (corrigeren, bewerken, de kantine-tv, een bestelling klaarzetten): de app
     * stuurt je niet naar de site, maar zegt dat het hier niet kan. */
    fun nietInApp(wat: String) {
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.niet_in_app_titel)))
            .setMessage(getString(R.string.niet_in_app_tekst, wat))
            .setPositiveButton(R.string.ok, null)
            .show()
    }

    /** Na het opslaan: taken die je hiermee misschien hebt afgerond ("taak_vragen" in het antwoord van de site)? Dan
     * per taak de vraag of hij klaar is, net als op de site. Daarna [daarna]. */
    fun vraagTaken(antwoord: JSONObject, daarna: () -> Unit = {}) {
        val vragen = antwoord.optJSONArray("taak_vragen")?.objecten().orEmpty()
        fun volgende(i: Int) {
            if (i >= vragen.size) return daarna()
            val taak = vragen[i]
            AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.taak_klaar_titel)))
                .setMessage(getString(R.string.taak_klaar_vraag, taak.optString("titel")))
                .setCancelable(false)
                .setPositiveButton(R.string.ja_klaar) { _, _ ->
                    bezig {
                        try {
                            val uit = Api.post(this, "/api/app/taken/${taak.getInt("id")}/afronden", verzoekId = Api.nieuwVerzoekId())
                            uit.tekstOfNull("melding")?.let { melding(it, lang = true) }
                        } finally {
                            volgende(i + 1)
                        }
                    }
                }
                .setNegativeButton(R.string.nog_niet) { _, _ -> volgende(i + 1) }
                .show()
        }
        volgende(0)
    }

    fun signaalWoord(signaal: Int) = getString(
        when (signaal) {
            3 -> R.string.signaal_uitstekend
            2 -> R.string.signaal_goed
            1 -> R.string.signaal_matig
            else -> R.string.signaal_zwak
        },
    )

    companion object {
        fun dp(context: Context, waarde: Int) = (waarde * context.resources.displayMetrics.density).toInt()
    }
}
