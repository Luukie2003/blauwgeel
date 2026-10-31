package nl.kantineblauwgeel.tv

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tv.databinding.ActivityPlayerBinding

/** Toont één scherm van de site, schermvullend, zonder dat iemand iets hoeft te doen.
 *
 * Herstelt zichzelf: lukt het laden niet (geen wifi, de site start net opnieuw op), dan staat er een melding en
 * probeert de app het elke 15 seconden vanzelf opnieuw, en meteen zodra er weer netwerk is. Ook als de webweergave
 * zelf vastloopt, begint het scherm opnieuw. Vroeger bleef de tv dan op de foutmelding staan tot iemand met de
 * afstandsbediening op "Opnieuw proberen" drukte.
 *
 * Het gekoppelde scherm onthoudt zijn eigen adres op de site, en krijgt de grootte (zoom) van de site: de pagina roept
 * daarvoor KantineTv.zoom() aan (zie templates/_kiosk_herstel.html op de site).
 *
 * Met de afstandsbediening: knop omlaag toont de prijzenlijst, knop omhoog de dia's. Dat wordt de instelling van deze
 * tv op de site (POST /kiosk/t/<token>/scherm), dus je ziet het ook op de site en de handterminal, en het blijft zo na
 * een herstart. OK opent de instellingen (de zoom per scherm, SettingsActivity). Terug sluit de app.
 *
 * Geheim (1.3): links, links, rechts, rechts, links, rechts opent het spel van de club (SpelActivity); Terug brengt je
 * hier terug. Links en rechts doen hier verder niets, dus per ongeluk gebeurt dat niet.
 *
 * De zoom: de pagina vertelt via KantineTv.scherm() wat hij toont en welke zoom de site voor deze tv heeft; heeft de tv
 * voor dat scherm een eigen zoom ingesteld, dan geldt die (Prefs.zoomVoor). */
class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private lateinit var startUrl: String
    private var wisselt = false

    /** Wat de pagina nu toont ("prijzen" of "dias"), zoals de pagina het via KantineTv.scherm() meldt. */
    private var toont: String? = null
    private val klok = Handler(Looper.getMainLooper())
    private var fout = false
    private var opnieuwOver = 0
    private var netwerkTerug: ConnectivityManager.NetworkCallback? = null

    /** De laatste toetsen van de afstandsbediening (toets, tijdstip), voor de geheime optie. */
    private val laatsteToetsen = ArrayDeque<Pair<Int, Long>>()

    companion object {
        private const val OPNIEUW_NA_SECONDEN = 15
        private const val GEKOPPELD_PAD = "/kiosk/t/"

        /** De geheime toetsen voor het spel, kort na elkaar (allemaal binnen GEHEIM_BINNEN_MS). */
        private val GEHEIM = listOf(
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
        )
        private const val GEHEIM_BINNEN_MS = 5000L

        fun intent(context: Context): Intent = Intent(context, PlayerActivity::class.java)
    }

    private val aftellen = object : Runnable {
        override fun run() {
            if (!fout) return
            if (opnieuwOver <= 0) {
                laad()
                return
            }
            binding.opnieuwOver.text = resources.getQuantityString(R.plurals.opnieuw_over, opnieuwOver, opnieuwOver)
            opnieuwOver--
            klok.postDelayed(this, 1000)
        }
    }

    @SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPlayerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        verbergSysteembalken()

        startUrl = Prefs.getGekoppeldUrl(this) ?: Screens.KOPPELEN_URL

        binding.webview.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            mediaPlaybackRequiresUserGesture = false
            textZoom = Prefs.zoomVoor(this@PlayerActivity, null)
            cacheMode = WebSettings.LOAD_DEFAULT
        }
        binding.webview.addJavascriptInterface(Brug(), "KantineTv")

        binding.webview.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                fout = false
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request?.isForMainFrame == true) mislukt()
            }

            override fun onReceivedHttpError(view: WebView?, request: WebResourceRequest?, errorResponse: WebResourceResponse?) {
                // Een foutpagina van de server zelf (bijvoorbeeld tijdens het opnieuw opstarten): ook opnieuw proberen.
                if (request?.isForMainFrame == true && (errorResponse?.statusCode ?: 0) >= 500) mislukt()
            }

            override fun onPageFinished(view: WebView?, finishedUrl: String?) {
                if (fout) return
                binding.foutmelding.visibility = View.GONE
                klok.removeCallbacks(aftellen)
                // Het eigen adres van een gekoppelde tv bewaren (zonder ?voorbeeld of andere toevoegingen).
                if (finishedUrl != null && GEKOPPELD_PAD in finishedUrl) {
                    val adres = finishedUrl.substringBefore('?').substringBefore('#')
                    if (adres != Prefs.getGekoppeldUrl(this@PlayerActivity)) Prefs.setGekoppeldUrl(this@PlayerActivity, adres)
                }
            }

            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                // De webweergave is vastgelopen of door het systeem gestopt: het scherm begint opnieuw.
                recreate()
                return true
            }
        }

        binding.opnieuwProberen.setOnClickListener { laad() }
        laad()
    }

    override fun onStart() {
        super.onStart()
        // Komt het netwerk terug terwijl de foutmelding er staat, dan meteen opnieuw proberen.
        val netwerk = getSystemService(ConnectivityManager::class.java) ?: return
        val terug = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                klok.post { if (fout) laad() }
            }
        }
        try {
            netwerk.registerDefaultNetworkCallback(terug)
            netwerkTerug = terug
        } catch (e: RuntimeException) {
            // Geen toestemming of te veel callbacks: het aftellen hierboven probeert het toch vanzelf opnieuw.
        }
    }

    override fun onStop() {
        super.onStop()
        netwerkTerug?.let {
            try {
                getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(it)
            } catch (e: RuntimeException) {
            }
        }
        netwerkTerug = null
    }

    private fun laad() {
        klok.removeCallbacks(aftellen)
        binding.opnieuwOver.text = getString(R.string.opnieuw_nu)
        binding.webview.loadUrl(startUrl)
    }

    private fun mislukt() {
        fout = true
        binding.foutmelding.visibility = View.VISIBLE
        opnieuwOver = OPNIEUW_NA_SECONDEN
        klok.removeCallbacks(aftellen)
        klok.post(aftellen)
    }

    /** Wat de pagina's van de site aan de app kunnen vragen (window.KantineTv). */
    private inner class Brug {
        @JavascriptInterface
        fun versie(): String = BuildConfig.VERSION_NAME

        /** Wat de pagina toont ("prijzen", "dias" of leeg bij de koppelcode) en de grootte die op de site voor deze tv is
         * gekozen. Geldt er voor dat scherm een andere zoom dan nu, dan opnieuw laden met de nieuwe. */
        @JavascriptInterface
        fun scherm(wat: String, siteZoom: Int) {
            klok.post {
                toont = wat.takeIf { it == Prefs.PRIJZEN || it == Prefs.DIAS }
                Prefs.setSiteZoom(this@PlayerActivity, siteZoom.coerceIn(50, 200))
                pasZoomToe()
            }
        }

        /** Voor een pagina van voor tv-app 1.2: alleen de zoom van de site. */
        @JavascriptInterface
        fun zoom(procent: Int) = scherm(toont ?: "", procent)
    }

    /** De zoom die nu geldt (eigen zoom van de tv voor dit scherm, anders de site); anders dan nu: opnieuw laden. */
    private fun pasZoomToe() {
        val nieuw = Prefs.zoomVoor(this, toont)
        if (binding.webview.settings.textZoom == nieuw) return
        binding.webview.settings.textZoom = nieuw
        binding.webview.reload()
    }

    override fun onResume() {
        super.onResume()
        binding.webview.onResume()  // terug uit het spel
        // Terug uit de instellingen: de zoom kan veranderd zijn.
        pasZoomToe()
    }

    /** Onthoudt de laatste toetsen; zijn dat de geheime (GEHEIM, binnen GEHEIM_BINNEN_MS), dan opent het spel. */
    private fun geheimeToets(toets: Int): Boolean {
        val nu = SystemClock.uptimeMillis()
        laatsteToetsen.addLast(toets to nu)
        while (laatsteToetsen.size > GEHEIM.size) laatsteToetsen.removeFirst()
        if (laatsteToetsen.map { it.first } != GEHEIM || nu - laatsteToetsen.first().second > GEHEIM_BINNEN_MS) return false
        laatsteToetsen.clear()
        binding.webview.onPause()  // de kantine-tv even stil, zodat er geen geluid van een video-dia onder het spel zit
        startActivity(Intent(this, SpelActivity::class.java))
        return true
    }

    /** Knop omlaag: de prijzenlijst; knop omhoog: de dia's (vóór de webweergave, die de pijltjes anders zelf gebruikt). */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0 && geheimeToets(event.keyCode)) return true
        // OK (de middelste knop): de instellingen, met de zoom per scherm.
        if ((event.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || event.keyCode == KeyEvent.KEYCODE_ENTER) &&
            binding.foutmelding.visibility != View.VISIBLE
        ) {
            if (event.action == KeyEvent.ACTION_UP) startActivity(Intent(this, SettingsActivity::class.java))
            return true
        }
        val naar = when (event.keyCode) {
            KeyEvent.KEYCODE_DPAD_DOWN -> "prijzen"
            KeyEvent.KEYCODE_DPAD_UP -> "dias"
            else -> null
        }
        if (naar == null || binding.foutmelding.visibility == View.VISIBLE) return super.dispatchKeyEvent(event)
        if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) wissel(naar)
        return true
    }

    /** Vraagt de site deze tv iets anders te laten tonen, en laadt dan meteen opnieuw. */
    private fun wissel(toont: String) {
        val adres = Prefs.getGekoppeldUrl(this) ?: return melding(getString(R.string.eerst_koppelen))
        if (wisselt) return
        wisselt = true
        Thread {
            val code = try {
                val verbinding = java.net.URL("$adres/scherm").openConnection() as java.net.HttpURLConnection
                verbinding.requestMethod = "POST"
                verbinding.connectTimeout = 8000
                verbinding.readTimeout = 8000
                verbinding.doOutput = true
                verbinding.setRequestProperty("Content-Type", "application/json")
                verbinding.outputStream.use { it.write("{\"toont\": \"$toont\"}".toByteArray()) }
                val antwoord = verbinding.responseCode
                verbinding.disconnect()
                antwoord
            } catch (e: java.io.IOException) {
                0
            }
            klok.post {
                wisselt = false
                when (code) {
                    200 -> {
                        melding(getString(if (toont == "prijzen") R.string.toont_prijzen else R.string.toont_dias))
                        binding.webview.loadUrl(adres)
                    }
                    404 -> melding(getString(R.string.eerst_koppelen))  // de tv toont nog de koppelcode
                    else -> melding(getString(R.string.wisselen_mislukt))
                }
            }
        }.start()
    }

    private fun melding(tekst: String) = android.widget.Toast.makeText(this, tekst, android.widget.Toast.LENGTH_SHORT).show()

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (binding.webview.canGoBack()) {
                binding.webview.goBack()
            } else {
                finish()
            }
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        klok.removeCallbacksAndMessages(null)
        binding.webview.destroy()
        super.onDestroy()
    }
}
