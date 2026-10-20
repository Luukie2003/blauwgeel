package nl.kantineblauwgeel.tv

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
 * Een gekoppeld scherm (zie Screens.GEKOPPELD) onthoudt zijn eigen adres op de site, en krijgt de grootte (zoom) van
 * de site: de pagina roept daarvoor KantineTv.zoom() aan (zie templates/_kiosk_herstel.html op de site). */
class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private lateinit var schermSleutel: String
    private lateinit var startUrl: String
    private val klok = Handler(Looper.getMainLooper())
    private var fout = false
    private var opnieuwOver = 0
    private var netwerkTerug: ConnectivityManager.NetworkCallback? = null

    companion object {
        private const val EXTRA_URL = "extra_url"
        private const val EXTRA_SCHERM_SLEUTEL = "extra_scherm_sleutel"
        private const val OPNIEUW_NA_SECONDEN = 15
        private const val GEKOPPELD_PAD = "/kiosk/t/"

        fun intentVoor(context: Context, scherm: Screen): Intent =
            Intent(context, PlayerActivity::class.java)
                .putExtra(EXTRA_URL, scherm.url)
                .putExtra(EXTRA_SCHERM_SLEUTEL, scherm.sleutel)
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

        val scherm = Screens.opSleutel(intent.getStringExtra(EXTRA_SCHERM_SLEUTEL))
        schermSleutel = scherm.sleutel
        startUrl = if (scherm == Screens.GEKOPPELD) {
            Prefs.getGekoppeldUrl(this) ?: scherm.url
        } else {
            intent.getStringExtra(EXTRA_URL) ?: scherm.url
        }

        binding.webview.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            mediaPlaybackRequiresUserGesture = false
            textZoom = Prefs.getZoom(this@PlayerActivity, schermSleutel)
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
                if (schermSleutel == Screens.GEKOPPELD.sleutel && finishedUrl != null && GEKOPPELD_PAD in finishedUrl) {
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

    override fun onResume() {
        super.onResume()
        // De zoom kan gewijzigd zijn via het instellingenscherm; opnieuw toepassen.
        binding.webview.settings.textZoom = Prefs.getZoom(this, schermSleutel)
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

        /** De grootte die op de site voor deze tv is gekozen; is die anders dan nu, dan opnieuw laden met de nieuwe. */
        @JavascriptInterface
        fun zoom(procent: Int) {
            val nieuw = procent.coerceIn(50, 200)
            klok.post {
                if (binding.webview.settings.textZoom == nieuw) return@post
                Prefs.setZoom(this@PlayerActivity, schermSleutel, nieuw)
                binding.webview.settings.textZoom = nieuw
                binding.webview.reload()
            }
        }
    }

    private fun verbergSysteembalken() {
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )
    }

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
