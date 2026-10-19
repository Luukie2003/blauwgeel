package nl.kantineblauwgeel.handterminal

import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.SslErrorHandler
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.ActivityWebBinding
import org.json.JSONObject

/** Een pagina van de site die (nog) geen eigen scherm in de app heeft, zoals het prikbord, de kassa of de bestellijst:
 * de handterminal-weergave van de site, ingelogd met dezelfde sessie als de app.
 *
 * - Een link naar een product opent het productscherm van de app; naar de startpagina gaat terug naar de app.
 * - Valt de verbinding weg, dan een duidelijk foutscherm dat vanzelf opnieuw probeert zodra er weer netwerk is. Een
 *   formulier wordt nooit vanzelf opnieuw verstuurd (geen dubbele boekingen).
 * - Op Android 6 kent de WebView het rootcertificaat van de site niet; zie Beveiliging.kt.
 * - Een scan komt in het scanveld van de pagina (assets/scan.js); is er geen, dan opent de app het product. */
class WebActivity : BasisActivity() {

    private enum class Fout { GEEN_NETWERK, SERVER, BEVEILIGING, VERSTUREN }

    private lateinit var b: ActivityWebBinding
    private lateinit var scanJs: String
    private val hoofdThread = Handler(Looper.getMainLooper())

    private var paginaLaadt = false
    private var foutTijdensLaden: Fout? = null
    private var huidigeFout: Fout? = null
    private var foutUrl: String? = null
    private var laatsteGoedeUrl: String? = null
    @Volatile private var laatsteMethode = "GET"
    private var pogingen = 0
    private var resterend = 0
    private var eerstePagina = true

    private var bestandTerug: ValueCallback<Array<Uri>>? = null
    private val kiesBestand = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        bestandTerug?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(r.resultCode, r.data))
        bestandTerug = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityWebBinding.inflate(layoutInflater)
        setContentView(b.root)
        scanJs = assets.open("scan.js").bufferedReader().use { it.readText() }
        richtBalkIn(b.balk, intent.getStringExtra(EXTRA_TITEL) ?: getString(R.string.website))

        val w = b.webView
        w.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            allowFileAccess = false
            allowContentAccess = false
            setSupportMultipleWindows(false)
            javaScriptCanOpenWindowsAutomatically = false
            builtInZoomControls = false
            setSupportZoom(false)
            textZoom = inst.tekstGrootte
            userAgentString = "$userAgentString KantineHandterminal/${BuildConfig.VERSION_NAME}"
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        CookieManager.getInstance().setAcceptCookie(true)
        w.webViewClient = SiteClient()
        w.webChromeClient = SiteChrome()
        w.setDownloadListener { url, userAgent, beschrijving, mime, _ -> download(url, userAgent, beschrijving, mime) }

        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { if (huidigeFout != null) probeerOpnieuw() else w.reload() }
        b.foutKnop.setOnClickListener { probeerOpnieuw() }
        b.foutTestKnop.setOnClickListener { testVerbinding() }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = terug()
        })

        waarschuwOudeWebView()
        Sessie.naarWebView(this)
        val pad = intent.getStringExtra(EXTRA_PAD) ?: "/"
        if (savedInstanceState == null || w.restoreState(savedInstanceState) == null) w.loadUrl(inst.basisUrl + pad)
    }

    override fun onResume() {
        super.onResume()
        b.webView.onResume()
        b.webView.settings.textZoom = inst.tekstGrootte
        if (huidigeFout == Fout.GEEN_NETWERK || huidigeFout == Fout.SERVER) probeerOpnieuw()
    }

    override fun onPause() {
        super.onPause()
        b.webView.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        b.webView.saveState(outState)
    }

    override fun onDestroy() {
        hoofdThread.removeCallbacksAndMessages(null)
        (b.webView.parent as? android.view.ViewGroup)?.removeView(b.webView)
        b.webView.destroy()
        super.onDestroy()
    }

    override fun weerVerbonden() {
        if (huidigeFout == Fout.GEEN_NETWERK || huidigeFout == Fout.SERVER) probeerOpnieuw()
    }

    // ---------------------------------------------------------------- navigatie

    private fun isSite(uri: Uri): Boolean {
        val host = uri.host?.lowercase() ?: return false
        val site = inst.siteHost.lowercase()
        return host == site || host == site.removePrefix("www.") || "www.$host" == site
    }

    /** Waar gaat een link heen? Een paar adressen van de site hebben een eigen scherm in de app; de rest van de site
     * blijft hier, en alles daarbuiten opent in een andere app. */
    private fun onderschep(uri: Uri): Boolean {
        when (uri.scheme?.lowercase()) {
            "about", "javascript", "data", "blob" -> return false
            "http", "https" -> if (isSite(uri)) {
                val pad = uri.path ?: "/"
                val product = Regex("^/producten/(\\d+)/?$").find(pad)?.groupValues?.get(1)?.toIntOrNull()
                return when {
                    pad == "/logout" -> { naarInlog(getString(R.string.uitgelogd)); true }
                    pad == "/login" || pad.startsWith("/login/") -> { naarInlog(getString(R.string.uitgelogd_sessie)); true }
                    pad == "/" -> { finish(); true }
                    product != null -> { ProductActivity.open(this, product); true }
                    pad == "/scannen" && Scanner.isAanwezig(this) -> { Scanner.startScan(this); true }
                    else -> false
                }
            }
        }
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (e: ActivityNotFoundException) {
            melding(getString(R.string.geen_app))
        }
        return true
    }

    private fun terug() {
        if (huidigeFout != null) {
            verbergFout()
            if (b.webView.canGoBack()) b.webView.goBack() else finish()
            return
        }
        // Eerst een open venster of de zoekresultaten van de site sluiten, dan pas een pagina terug.
        b.webView.evaluateJavascript(
            "(function(){var m=document.querySelector('.modal-overlay.open');if(m){m.classList.remove('open');return 1;}" +
                "var r=document.getElementById('pda-zoek-resultaten');if(r&&!r.hidden){r.hidden=true;return 1;}return 0;})()",
        ) { gesloten ->
            if (gesloten == "1") return@evaluateJavascript
            if (b.webView.canGoBack()) b.webView.goBack() else finish()
        }
    }

    override fun bijScan(code: String) {
        if (huidigeFout != null) return openScan(code)
        b.webView.evaluateJavascript("($scanJs)(${JSONObject.quote(code)})") { uitkomst ->
            when (uitkomst) {
                "\"geen_veld\"" -> openScan(code)
                "\"genegeerd\"" -> melding(getString(R.string.scan_genegeerd))
                else -> tril()
            }
        }
    }

    private inner class SiteClient : WebViewClient() {

        @Deprecated("Alleen nog voor Android 6", ReplaceWith(""))
        override fun shouldOverrideUrlLoading(view: WebView, url: String): Boolean = onderschep(Uri.parse(url))

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
            request.isForMainFrame && onderschep(request.url)

        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
            if (request.isForMainFrame) laatsteMethode = request.method ?: "GET"
            return null
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            val uri = Uri.parse(url ?: "")
            // Vangnet: een doorverwijzing naar de inlogpagina (sessie verlopen) die niet langs shouldOverrideUrlLoading kwam.
            if (isSite(uri) && (uri.path == "/login" || uri.path?.startsWith("/login/") == true)) {
                view.stopLoading()
                naarInlog(getString(R.string.uitgelogd_sessie))
                return
            }
            foutTijdensLaden = null
            paginaLaadt = true
            hoofdThread.removeCallbacks(waakhond)
            hoofdThread.postDelayed(waakhond, 40_000)
        }

        override fun onPageCommitVisible(view: WebView, url: String?) {
            paginaLaadt = false
            hoofdThread.removeCallbacks(waakhond)
            // In de app is de weergave al gekozen.
            view.evaluateJavascript("(function(){var m=document.getElementById('welkom-modal');if(m&&m.parentNode)m.parentNode.removeChild(m);})();", null)
        }

        override fun onPageFinished(view: WebView, url: String?) {
            paginaLaadt = false
            hoofdThread.removeCallbacks(waakhond)
            b.verversen.isRefreshing = false
            b.voortgang.isVisible = false
            if (foutTijdensLaden == null && url != null && url != "about:blank") {
                verbergFout()
                pogingen = 0
                if (isSite(Uri.parse(url))) laatsteGoedeUrl = url
                // De eerste pagina houdt de naam van de knop waarmee je hem opende; daarna de titel van de pagina.
                if (eerstePagina) eerstePagina = false
                else view.title?.takeIf { it.isNotBlank() && !it.startsWith("http") }?.let { zetBalkTitel(it.substringBefore(" · ")) }
            }
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (!request.isForMainFrame) return
            val soort = when {
                request.method.equals("POST", ignoreCase = true) -> Fout.VERSTUREN
                !verbonden -> Fout.GEEN_NETWERK
                else -> Fout.SERVER
            }
            foutTijdensLaden = soort
            toonFout(soort, request.url.toString())
        }

        override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
            if (!request.isForMainFrame) return
            val post = request.method.equals("POST", ignoreCase = true)
            when (response.statusCode) {
                502, 504 -> {
                    foutTijdensLaden = if (post) Fout.VERSTUREN else Fout.SERVER
                    toonFout(foutTijdensLaden!!, request.url.toString())
                }
                503 -> controleerNoodstop(request.url.toString(), post)
            }
        }

        override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
            val uri = Uri.parse(error.url ?: "")
            if (error.primaryError != SslError.SSL_UNTRUSTED || !isSite(uri)) {
                handler.cancel()
                if (isSite(uri)) sslMislukt(error.url)
                return
            }
            // Op Android 6/7.0 kent de WebView het rootcertificaat van de site niet; zie Beveiliging.kt.
            val certificaat = error.certificate
            val adres = "https://" + uri.host
            Thread {
                val goed = Beveiliging.isZelfdeAlsGecontroleerd(applicationContext, certificaat, adres)
                runOnUiThread {
                    if (goed) handler.proceed() else {
                        handler.cancel()
                        sslMislukt(error.url)
                    }
                }
            }.start()
        }

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            recreate()
            return true
        }
    }

    private inner class SiteChrome : WebChromeClient() {
        override fun onProgressChanged(view: WebView, voortgang: Int) {
            b.voortgang.progress = voortgang
            b.voortgang.isVisible = voortgang < 100
        }

        override fun onShowFileChooser(view: WebView, terugroep: ValueCallback<Array<Uri>>, parameters: FileChooserParams): Boolean {
            bestandTerug?.onReceiveValue(null)
            bestandTerug = terugroep
            return try {
                kiesBestand.launch(parameters.createIntent())
                true
            } catch (e: ActivityNotFoundException) {
                bestandTerug = null
                false
            }
        }
    }

    // ---------------------------------------------------------------- fouten

    // Na 40 seconden geven we het op. Was het een formulier, dan niet opnieuw: misschien is het al opgeslagen.
    private val waakhond = Runnable {
        if (paginaLaadt) {
            val soort = if (laatsteMethode.equals("POST", ignoreCase = true)) Fout.VERSTUREN else Fout.SERVER
            foutTijdensLaden = soort
            b.webView.stopLoading()
            toonFout(soort, b.webView.url ?: laatsteGoedeUrl ?: inst.basisUrl)
        }
    }

    private fun sslMislukt(url: String?) {
        foutTijdensLaden = Fout.BEVEILIGING
        b.webView.stopLoading()
        toonFout(Fout.BEVEILIGING, url ?: laatsteGoedeUrl ?: inst.basisUrl)
    }

    private fun controleerNoodstop(url: String, post: Boolean) {
        lifecycleScope.launch {
            val noodstop = try {
                Api.getJson(this@WebActivity, "/noodstop/status").optBoolean("actief", false)
            } catch (e: Exception) {
                false
            }
            if (noodstop) {
                naarInlog(getString(R.string.code_noodstop))
            } else {
                foutTijdensLaden = if (post) Fout.VERSTUREN else Fout.SERVER
                toonFout(foutTijdensLaden!!, url)
            }
        }
    }

    private fun toonFout(soort: Fout, url: String) {
        huidigeFout = soort
        foutUrl = url
        paginaLaadt = false
        hoofdThread.removeCallbacks(waakhond)
        b.verversen.isRefreshing = false
        b.voortgang.isVisible = false
        val (icoon, titel, tekst) = when (soort) {
            Fout.GEEN_NETWERK -> Triple(R.drawable.ic_wifi_uit, R.string.fout_geen_netwerk_titel, R.string.fout_geen_netwerk_tekst)
            Fout.SERVER -> Triple(R.drawable.ic_wolk_uit, R.string.fout_server_titel, R.string.fout_server_tekst)
            Fout.BEVEILIGING -> Triple(R.drawable.ic_slot, R.string.fout_beveiliging_titel, R.string.fout_beveiliging_tekst)
            Fout.VERSTUREN -> Triple(R.drawable.ic_let_op, R.string.fout_versturen_titel, R.string.fout_versturen_tekst)
        }
        b.foutIcoon.setImageResource(icoon)
        b.foutTitel.setText(titel)
        b.foutTekst.setText(tekst)
        b.foutKnop.setText(if (soort == Fout.VERSTUREN) R.string.fout_pagina_laden else R.string.fout_opnieuw)
        b.foutLaag.isVisible = true
        if (soort == Fout.VERSTUREN || soort == Fout.BEVEILIGING) {
            hoofdThread.removeCallbacks(aftelTik)
            b.foutAftellen.isVisible = false
        } else {
            planOpnieuw()
        }
    }

    private fun verbergFout() {
        huidigeFout = null
        hoofdThread.removeCallbacks(aftelTik)
        b.foutLaag.isVisible = false
    }

    /** Steeds iets langer wachten (3, 6, 12, 24, 30 s), en zonder netwerk wachten tot het er weer is. */
    private fun planOpnieuw() {
        hoofdThread.removeCallbacks(aftelTik)
        b.foutAftellen.isVisible = true
        if (!verbonden) {
            b.foutAftellen.setText(R.string.fout_wacht_netwerk)
            return
        }
        resterend = minOf(3 shl minOf(pogingen, 4), 30)
        hoofdThread.post(aftelTik)
    }

    private val aftelTik = object : Runnable {
        override fun run() {
            if (resterend <= 0) {
                probeerOpnieuw()
                return
            }
            b.foutAftellen.text = getString(R.string.fout_aftellen, resterend)
            resterend--
            hoofdThread.postDelayed(this, 1_000)
        }
    }

    private fun probeerOpnieuw() {
        hoofdThread.removeCallbacks(aftelTik)
        val soort = huidigeFout
        pogingen++
        b.foutAftellen.text = getString(R.string.balk_laden)
        val doel = if (soort == Fout.VERSTUREN) laatsteGoedeUrl ?: inst.basisUrl else foutUrl ?: laatsteGoedeUrl ?: inst.basisUrl
        if (soort == Fout.VERSTUREN) verbergFout()
        Sessie.naarWebView(this)
        b.webView.loadUrl(doel)
    }

    private fun download(url: String, userAgent: String, beschrijving: String?, mime: String?) {
        try {
            val naam = URLUtil.guessFileName(url, beschrijving, mime)
            val verzoek = DownloadManager.Request(Uri.parse(url)).apply {
                CookieManager.getInstance().getCookie(url)?.let { addRequestHeader("Cookie", it) }
                addRequestHeader("User-Agent", userAgent)
                setMimeType(mime)
                setTitle(naam)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setDestinationInExternalFilesDir(this@WebActivity, Environment.DIRECTORY_DOWNLOADS, naam)
            }
            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(verzoek)
            melding(getString(R.string.download_gestart))
        } catch (e: Exception) {
            melding(getString(R.string.geen_app))
        }
    }

    /** De pagina's van de site hebben een webweergave van versie 72 of nieuwer nodig. Eén keer per keer opstarten
     * melden als hij ouder is (de eigen schermen van de app hebben er geen last van). */
    private fun waarschuwOudeWebView() {
        if (gewaarschuwd) return
        gewaarschuwd = true
        val versie = try {
            Regex("Chrome/(\\d+)").find(WebSettings.getDefaultUserAgent(this))?.groupValues?.get(1)?.toIntOrNull()
        } catch (e: Exception) {
            null
        }
        if (versie != null && versie < 72) melding(getString(R.string.webview_oud, versie), lang = true)
    }

    companion object {
        private var gewaarschuwd = false
        private const val EXTRA_PAD = "pad"
        private const val EXTRA_TITEL = "titel"

        fun open(activity: Activity, pad: String, titel: String? = null) {
            activity.startActivity(Intent(activity, WebActivity::class.java).putExtra(EXTRA_PAD, pad).putExtra(EXTRA_TITEL, titel))
        }
    }
}
