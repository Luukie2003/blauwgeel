package nl.kantineblauwgeel.handterminal

import android.animation.ObjectAnimator
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.http.SslError
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.InputMethodManager
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
import android.widget.PopupMenu
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.ColorRes
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityHoofdBinding
import org.json.JSONObject

/** De handterminal: inloggen met de persoonlijke code, daarna de handterminal-weergave van de site.
 *
 * Wat de app toevoegt aan de site in een browser:
 * - inloggen met de 6-cijferige code (dezelfde als op de tablet), en automatisch uitloggen na een tijd niets doen,
 *   want iedereen gebruikt dezelfde handterminal;
 * - de Zebra-scanner werkt altijd, ook als er geen veld is geselecteerd (zie Scanner.kt en assets/scan.js);
 * - verbindingsbewaking: een balk die laat zien of er verbinding is, een duidelijk foutscherm dat vanzelf opnieuw
 *   probeert zodra de wifi terug is, en nooit stilletjes een formulier opnieuw versturen (geen dubbele boekingen);
 * - de wifi blijft op volle kracht zolang de app voorin staat, en het juiste rootcertificaat voor oude
 *   Android-versies (zie Beveiliging.kt). */
class HoofdActivity : AppCompatActivity() {

    private enum class Fout { GEEN_NETWERK, SERVER, BEVEILIGING, VERSTUREN }

    private lateinit var b: ActivityHoofdBinding
    private lateinit var inst: Instellingen
    private lateinit var verbinding: Verbinding
    private lateinit var scanJs: String
    private val hoofdThread = Handler(Looper.getMainLooper())

    private var scanOntvanger: BroadcastReceiver? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var toestand: Verbinding.Toestand? = null

    // Inloggen
    private val code = StringBuilder()
    private var ingelogd = false
    private var bezigMetInloggen = false
    private var ingelogdOp: String? = null // het website-adres bij het inloggen; verandert dat, dan opnieuw inloggen
    private var laatsteOpslag = 0L

    // Laden van pagina's
    private var paginaLaadt = false
    private var traag = false
    private var foutTijdensLaden: Fout? = null
    private var huidigeFout: Fout? = null
    private var foutUrl: String? = null
    private var laatsteGoedeUrl: String? = null
    @Volatile private var laatsteMethode = "GET" // van het laatste verzoek voor de hele pagina (zie shouldInterceptRequest)
    private var laadUrl: String? = null
    private var pogingen = 0
    private var resterend = 0
    private var wisGeschiedenis = false

    private var bestandTerug: ValueCallback<Array<Uri>>? = null
    private val kiesBestand = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        bestandTerug?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(r.resultCode, r.data))
        bestandTerug = null
    }

    private val startUrl get() = inst.basisUrl + "/"
    private val inlogZichtbaar get() = b.inlog.root.isVisible

    // ---------------------------------------------------------------- levenscyclus

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityHoofdBinding.inflate(layoutInflater)
        setContentView(b.root)
        inst = Instellingen(this)
        verbinding = Verbinding(this) { werkVerbindingBij(it) }
        scanJs = assets.open("scan.js").bufferedReader().use { it.readText() }

        richtWebViewIn()
        richtInlogIn()
        richtBalkEnFoutschermIn()
        Scanner.stelIn(this)

        val wifi = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        wifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "kantine:handterminal").apply {
            setReferenceCounted(false)
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = terug()
        })

        if (inst.naam != null && !inst.isVerlopen() && heeftSessie()) {
            ingelogd = true
            ingelogdOp = inst.basisUrl
            toonSite(animatie = false)
            if (savedInstanceState == null || b.webView.restoreState(savedInstanceState) == null) {
                laad(inst.vorigePagina?.takeIf { isSite(Uri.parse(it)) } ?: startUrl)
            }
        } else {
            val verlopen = inst.naam != null && inst.isVerlopen()
            uitloggen(if (verlopen) getString(R.string.uitgelogd_automatisch, inst.uitlogMinuten) else null)
        }
        openTestUrl(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        openTestUrl(intent)
    }

    /** Alleen in een testversie: `adb shell am start -n <app>/.HoofdActivity --es test_url <adres>` opent een pagina
     * zonder in te loggen, om bijvoorbeeld de beveiligde verbinding op Android 6 te controleren. */
    private fun openTestUrl(intent: Intent?) {
        if (!BuildConfig.DEBUG) return
        val url = intent?.getStringExtra("test_url") ?: return
        toonSite(animatie = false)
        b.webView.loadUrl(url)
    }

    override fun onResume() {
        super.onResume()
        b.webView.onResume()
        verbinding.start()
        werkVerbindingBij(verbinding.huidig())
        scanOntvanger = Scanner.luister(this) { code, _ -> hoofdThread.post { verwerkScan(code) } }
        wifiLock?.acquire()
        b.webView.settings.textZoom = inst.tekstGrootte
        if (ingelogd && ingelogdOp != inst.basisUrl) {
            uitloggen(getString(R.string.uitgelogd), vergeetPagina = true) // ander website-adres (alleen in een testversie)
        } else if (ingelogd && inst.isVerlopen()) {
            uitloggen(getString(R.string.uitgelogd_automatisch, inst.uitlogMinuten))
        } else if (huidigeFout == Fout.GEEN_NETWERK || huidigeFout == Fout.SERVER) {
            probeerOpnieuw()
        }
        hoofdThread.post(inactiviteitTik)
    }

    override fun onPause() {
        super.onPause()
        scanOntvanger?.let { unregisterReceiver(it) }
        scanOntvanger = null
        verbinding.stop()
        if (wifiLock?.isHeld == true) wifiLock?.release()
        hoofdThread.removeCallbacks(inactiviteitTik)
        b.webView.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (ingelogd) b.webView.saveState(outState)
    }

    override fun onDestroy() {
        hoofdThread.removeCallbacksAndMessages(null)
        (b.webView.parent as? android.view.ViewGroup)?.removeView(b.webView)
        b.webView.destroy()
        super.onDestroy()
    }

    // ---------------------------------------------------------------- automatisch uitloggen

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        if (ev.actionMasked == MotionEvent.ACTION_DOWN) activiteit()
        return super.dispatchTouchEvent(ev)
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        activiteit()
        // Een toestel met echte cijfertoetsen kan ook zo de code intikken.
        if (inlogZichtbaar && event.action == KeyEvent.ACTION_DOWN) {
            when (event.keyCode) {
                in KeyEvent.KEYCODE_0..KeyEvent.KEYCODE_9 -> {
                    cijfer('0' + (event.keyCode - KeyEvent.KEYCODE_0)); return true
                }
                KeyEvent.KEYCODE_DEL -> {
                    haalCijferWeg(); return true
                }
            }
        }
        return super.dispatchKeyEvent(event)
    }

    private fun activiteit(direct: Boolean = false) {
        val nu = System.currentTimeMillis()
        if (direct || nu - laatsteOpslag > 5_000) {
            inst.laatsteActiviteit = nu
            laatsteOpslag = nu
        }
    }

    private val inactiviteitTik = object : Runnable {
        override fun run() {
            if (ingelogd && inst.isVerlopen()) uitloggen(getString(R.string.uitgelogd_automatisch, inst.uitlogMinuten))
            hoofdThread.postDelayed(this, 30_000)
        }
    }

    // ---------------------------------------------------------------- inloggen

    private fun richtInlogIn() {
        val l = b.inlog
        listOf(
            l.toets0 to '0', l.toets1 to '1', l.toets2 to '2', l.toets3 to '3', l.toets4 to '4',
            l.toets5 to '5', l.toets6 to '6', l.toets7 to '7', l.toets8 to '8', l.toets9 to '9',
        ).forEach { (toets, c) ->
            toets.setOnClickListener {
                it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                cijfer(c)
            }
        }
        l.toetsWis.setOnClickListener { wisCode(); verbergMelding() }
        l.toetsTerug.setOnClickListener { haalCijferWeg() }
        l.toetsTerug.setOnLongClickListener { wisCode(); true }
        // Verborgen: lang op het logo drukken opent de instellingen (zoals bij de tablet-app).
        l.inlogLogo.setOnLongClickListener { openInstellingen(); true }
        l.inlogVersie.text = "v" + BuildConfig.VERSION_NAME

        val webview = webViewVersie()
        if (webview != null && webview < MIN_WEBVIEW) {
            l.webviewWaarschuwing.text = getString(R.string.webview_oud, webview)
            l.webviewWaarschuwing.isVisible = true
            l.webviewWaarschuwing.setOnClickListener { werkWebViewBij() }
        }
        werkStippenBij()
    }

    private fun cijfer(c: Char) {
        if (bezigMetInloggen || code.length >= 6) return
        code.append(c)
        verbergMelding()
        werkStippenBij()
        if (code.length == 6) controleerCode()
    }

    private fun haalCijferWeg() {
        if (bezigMetInloggen || code.isEmpty()) return
        code.deleteCharAt(code.length - 1)
        werkStippenBij()
    }

    private fun wisCode() {
        code.clear()
        werkStippenBij()
    }

    private fun werkStippenBij(fout: Boolean = false) {
        val stippen = b.inlog.stippen
        for (i in 0 until stippen.childCount) {
            stippen.getChildAt(i).setBackgroundResource(
                when {
                    fout -> R.drawable.stip_fout
                    i < code.length -> R.drawable.stip_vol
                    else -> R.drawable.stip_leeg
                },
            )
        }
    }

    private fun zetToetsen(aan: Boolean) {
        val toetsen = b.inlog.toetsen
        for (r in 0 until toetsen.childCount) {
            val rij = toetsen.getChildAt(r) as android.view.ViewGroup
            for (k in 0 until rij.childCount) rij.getChildAt(k).isEnabled = aan
        }
        toetsen.alpha = if (aan) 1f else 0.55f
    }

    private fun controleerCode() {
        val ingevoerd = code.toString()
        val userAgent = b.webView.settings.userAgentString
        val basisUrl = inst.basisUrl
        bezigMetInloggen = true
        zetToetsen(false)
        verbergMelding()
        b.inlog.inlogBezig.isVisible = true
        Thread {
            val uitkomst = Server.inloggen(applicationContext, basisUrl, ingevoerd, userAgent)
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                bezigMetInloggen = false
                zetToetsen(true)
                b.inlog.inlogBezig.isVisible = false
                verwerkInlog(uitkomst, basisUrl)
            }
        }.start()
    }

    private fun verwerkInlog(uitkomst: Server.Inlog, basisUrl: String) {
        when (uitkomst) {
            is Server.Inlog.Gelukt -> ingelogdAls(uitkomst, basisUrl)
            is Server.Inlog.FouteCode -> codeFout(
                uitkomst.pogingenOver?.takeIf { it in 1..2 }?.let { getString(R.string.code_fout_pogingen, it) }
                    ?: getString(R.string.code_fout),
            )
            is Server.Inlog.TeVeelPogingen -> codeFout(
                uitkomst.minuten?.let { getString(R.string.code_te_veel_minuten, it) } ?: getString(R.string.code_te_veel),
            )
            Server.Inlog.Noodstop -> codeFout(getString(R.string.code_noodstop))
            is Server.Inlog.Mislukt -> {
                controleerWebsite()
                codeFout(
                getString(
                    when (uitkomst.soort) {
                        Server.Fout.GEEN_VERBINDING -> R.string.code_geen_verbinding
                        Server.Fout.TRAAG -> R.string.code_traag
                        Server.Fout.BEVEILIGING -> R.string.code_beveiliging
                        Server.Fout.SERVER -> R.string.code_server
                    },
                ),
                schudden = false,
            )
            }
        }
    }

    private fun ingelogdAls(gelukt: Server.Inlog.Gelukt, basisUrl: String) {
        val cookies = CookieManager.getInstance()
        gelukt.cookies.forEach { cookies.setCookie(basisUrl, it) }
        // Altijd de handterminal-weergave van de site (die onthoudt dat per toestel in dit cookie).
        val veilig = if (basisUrl.startsWith("https://")) "; Secure" else ""
        cookies.setCookie(basisUrl, "weergave=pda; Max-Age=31536000; Path=/; SameSite=Lax$veilig")
        cookies.flush()

        // Dezelfde persoon na automatisch uitloggen: verder waar je was. Iemand anders: het startscherm.
        val zelfde = gelukt.naam == inst.vorigeNaam
        val doel = inst.vorigePagina?.takeIf { zelfde && isSite(Uri.parse(it)) } ?: startUrl
        inst.naam = gelukt.naam
        inst.vorigeNaam = gelukt.naam
        activiteit(direct = true)
        ingelogd = true
        ingelogdOp = basisUrl
        wisCode()
        werkBalkBij()

        wisGeschiedenis = true
        laad(doel)
        toonSite(animatie = true)
        Toast.makeText(this, getString(R.string.welkom, gelukt.naam), Toast.LENGTH_SHORT).show()
    }

    private fun codeFout(melding: String, schudden: Boolean = true) {
        toonMelding(melding, fout = true)
        if (schudden) {
            werkStippenBij(fout = true)
            ObjectAnimator.ofFloat(b.inlog.stippen, "translationX", 0f, 22f, -22f, 16f, -16f, 8f, -8f, 0f)
                .setDuration(450).start()
            tril(120)
            hoofdThread.postDelayed({ wisCode() }, 500)
        } else {
            wisCode()
        }
    }

    private fun toonMelding(tekst: String, fout: Boolean) {
        val m = b.inlog.inlogMelding
        m.text = tekst
        m.setBackgroundResource(if (fout) R.drawable.melding_fout else R.drawable.melding_info)
        m.visibility = View.VISIBLE
    }

    private fun verbergMelding() {
        b.inlog.inlogMelding.visibility = View.INVISIBLE
    }

    /** Terug naar het inlogscherm, met de sessie weg. [vergeetPagina]: bij zelf uitloggen niet verder waar je was. */
    private fun uitloggen(melding: String?, vergeetPagina: Boolean = false) {
        ingelogd = false
        ingelogdOp = null
        inst.naam = null
        if (vergeetPagina) {
            inst.vorigeNaam = null
            inst.vorigePagina = null
        }
        val cookies = CookieManager.getInstance()
        cookies.removeAllCookies { cookies.flush() }
        b.webView.stopLoading()
        verbergFout()
        laadUrl = null
        wisGeschiedenis = true
        b.webView.loadUrl("about:blank")
        wisCode()
        if (melding != null) toonMelding(melding, fout = false) else verbergMelding()
        toonInlog()
    }

    /** De site stuurde naar de inlogpagina: de sessie is verlopen (of overal uitgelogd). Na inloggen verder. */
    private fun sessieVerlopen(uri: Uri) {
        val volgende = uri.getQueryParameter("next")
        if (volgende != null && volgende.startsWith("/") && !volgende.startsWith("//")) {
            inst.vorigePagina = inst.basisUrl + volgende
        }
        uitloggen(if (ingelogd) getString(R.string.uitgelogd_sessie) else null)
    }

    private fun heeftSessie(): Boolean =
        CookieManager.getInstance().getCookie(inst.basisUrl)?.contains("session=") == true

    private fun toonInlog() {
        val laag = b.inlog.root
        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(b.root.windowToken, 0)
        laag.animate().cancel()
        laag.alpha = 1f
        laag.isVisible = true
        laag.scrollTo(0, 0)
        controleerWebsite()
    }

    private fun toonSite(animatie: Boolean) {
        val laag = b.inlog.root
        if (!animatie) {
            laag.isVisible = false
            return
        }
        laag.animate().alpha(0f).setDuration(220).withEndAction {
            laag.isVisible = false
            laag.alpha = 1f
        }.start()
    }

    // ---------------------------------------------------------------- de site in de WebView

    @SuppressLint("SetJavaScriptEnabled")
    private fun richtWebViewIn() {
        val w = b.webView
        w.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            @Suppress("DEPRECATION")
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            allowFileAccess = false
            allowContentAccess = false
            setSupportMultipleWindows(false)
            javaScriptCanOpenWindowsAutomatically = false
            builtInZoomControls = false
            setSupportZoom(false)
            textZoom = inst.tekstGrootte
            // De site kan zo zien dat hij in de app draait (bijvoorbeeld om de weergavekeuze over te slaan).
            userAgentString = "$userAgentString KantineHandterminal/${BuildConfig.VERSION_NAME}"
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        CookieManager.getInstance().setAcceptCookie(true)
        w.webViewClient = SiteClient()
        w.webChromeClient = SiteChrome()
        w.setDownloadListener { url, userAgent, beschrijving, mime, _ -> download(url, userAgent, beschrijving, mime) }

        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setProgressBackgroundColorSchemeResource(R.color.geel)
        b.verversen.setOnRefreshListener { vernieuwen() }
    }

    private fun laad(url: String) {
        laadUrl = url
        b.webView.loadUrl(url)
    }

    /** Vernieuwen verstuurt nooit een formulier opnieuw: de WebView vraagt dat via onFormResubmission, en dat
     * weigeren we (standaardgedrag). */
    private fun vernieuwen() {
        if (huidigeFout != null) probeerOpnieuw() else b.webView.reload()
    }

    private fun isSite(uri: Uri): Boolean {
        val host = uri.host?.lowercase() ?: return false
        val site = inst.siteHost.lowercase()
        return host == site || host == site.removePrefix("www.") || "www.$host" == site
    }

    /** Waar gaat een link heen? Binnen de site in de app, de rest in een andere app. Een paar adressen van de
     * site handelt de app zelf af: uitloggen, inloggen en de camerascanner (de Zebra heeft een echte). */
    private fun onderschep(uri: Uri): Boolean {
        when (uri.scheme?.lowercase()) {
            "about", "javascript", "data", "blob" -> return false
            "http", "https" -> if (isSite(uri)) {
                val pad = uri.path ?: "/"
                return when {
                    pad == "/logout" -> {
                        uitloggen(getString(R.string.uitgelogd), vergeetPagina = true); true
                    }
                    pad == "/login" || pad.startsWith("/login/") -> {
                        sessieVerlopen(uri); true
                    }
                    pad == "/scannen" && Scanner.isAanwezig(this) -> {
                        Scanner.startScan(this)
                        Toast.makeText(this, R.string.scan_klaar, Toast.LENGTH_SHORT).show()
                        true
                    }
                    else -> false
                }
            }
        }
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, R.string.geen_app, Toast.LENGTH_SHORT).show()
        }
        return true
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
            // Vangnet: een doorverwijzing naar de inlogpagina die niet langs shouldOverrideUrlLoading kwam.
            if (isSite(uri) && (uri.path == "/login" || uri.path?.startsWith("/login/") == true)) {
                view.stopLoading()
                sessieVerlopen(uri)
                return
            }
            foutTijdensLaden = null
            paginaLaadt = url != "about:blank"
            if (paginaLaadt) startWaakhond()
        }

        // De pagina staat in beeld en is te gebruiken; plaatjes mogen nog binnendruppelen. Vanaf hier is het dus
        // geen trage of mislukte verbinding meer, ook als onPageFinished nog even op zich laat wachten.
        override fun onPageCommitVisible(view: WebView, url: String?) {
            if (url != "about:blank") {
                paginaLaadt = false
                stopWaakhond()
            }
            pasPaginaAan(view, url)
        }

        override fun onPageFinished(view: WebView, url: String?) {
            paginaLaadt = false
            stopWaakhond()
            b.verversen.isRefreshing = false
            b.voortgang.isVisible = false
            if (wisGeschiedenis && url != null && url != "about:blank") {
                view.clearHistory()
                wisGeschiedenis = false
            }
            if (foutTijdensLaden == null && url != null && url != "about:blank") {
                verbergFout()
                pogingen = 0
                if (isSite(Uri.parse(url))) {
                    laatsteGoedeUrl = url
                    if (ingelogd) inst.vorigePagina = url
                }
                pasPaginaAan(view, url)
            }
            werkBalkBij()
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (!request.isForMainFrame) return
            val soort = when {
                request.method.equals("POST", ignoreCase = true) -> Fout.VERSTUREN
                toestand?.verbonden == false || !verbinding.huidig().verbonden -> Fout.GEEN_NETWERK
                else -> Fout.SERVER
            }
            foutTijdensLaden = soort
            toonFout(soort, request.url.toString())
        }

        override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
            if (!request.isForMainFrame) return
            val post = request.method.equals("POST", ignoreCase = true)
            when (response.statusCode) {
                // PythonAnywhere (de server) start opnieuw op, of is overbelast.
                502, 504 -> {
                    foutTijdensLaden = if (post) Fout.VERSTUREN else Fout.SERVER
                    toonFout(foutTijdensLaden!!, request.url.toString())
                }
                // Een noodstop (alles dicht) of de server zelf: dat zoeken we even uit.
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
            // De webweergave is gecrasht (bijvoorbeeld door te weinig geheugen): het scherm opnieuw opbouwen.
            recreate()
            return true
        }
    }

    private fun sslMislukt(url: String?) {
        foutTijdensLaden = Fout.BEVEILIGING
        b.webView.stopLoading()
        toonFout(Fout.BEVEILIGING, url ?: laadUrl ?: startUrl)
    }

    private fun controleerNoodstop(url: String, post: Boolean) {
        val basisUrl = inst.basisUrl
        Thread {
            val noodstop = try {
                val v = Beveiliging.open(applicationContext, "$basisUrl/noodstop/status")
                v.connectTimeout = 8_000
                v.readTimeout = 8_000
                try {
                    JSONObject(v.inputStream.bufferedReader().use { it.readText() }).optBoolean("actief", false)
                } finally {
                    v.disconnect()
                }
            } catch (e: Exception) {
                false
            }
            runOnUiThread {
                if (noodstop) {
                    uitloggen(getString(R.string.code_noodstop))
                } else {
                    foutTijdensLaden = if (post) Fout.VERSTUREN else Fout.SERVER
                    toonFout(foutTijdensLaden!!, url)
                }
            }
        }.start()
    }

    /** Kleine aanpassingen aan elke pagina: de weergavekeuze na het inloggen hoort niet in de app. */
    private fun pasPaginaAan(view: WebView, url: String?) {
        if (url == null || !isSite(Uri.parse(url))) return
        view.evaluateJavascript(
            "(function(){var m=document.getElementById('welkom-modal');if(m&&m.parentNode)m.parentNode.removeChild(m);})();",
            null,
        )
    }

    private inner class SiteChrome : WebChromeClient() {
        override fun onProgressChanged(view: WebView, voortgang: Int) {
            b.voortgang.progress = voortgang
            b.voortgang.isVisible = voortgang < 100 && view.url != "about:blank"
        }

        override fun onShowFileChooser(
            view: WebView,
            terugroep: ValueCallback<Array<Uri>>,
            parameters: FileChooserParams,
        ): Boolean {
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

    private fun download(url: String, userAgent: String, beschrijving: String?, mime: String?) {
        try {
            val naam = URLUtil.guessFileName(url, beschrijving, mime)
            val verzoek = DownloadManager.Request(Uri.parse(url)).apply {
                CookieManager.getInstance().getCookie(url)?.let { addRequestHeader("Cookie", it) }
                addRequestHeader("User-Agent", userAgent)
                setMimeType(mime)
                setTitle(naam)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setDestinationInExternalFilesDir(this@HoofdActivity, Environment.DIRECTORY_DOWNLOADS, naam)
            }
            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(verzoek)
            Toast.makeText(this, R.string.download_gestart, Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, R.string.geen_app, Toast.LENGTH_SHORT).show()
        }
    }

    // ---------------------------------------------------------------- trage verbinding

    private val waakhondTraag = Runnable {
        if (paginaLaadt) {
            traag = true
            werkBalkBij()
        }
    }

    // Na 40 seconden geven we het op. Was het een formulier, dan niet opnieuw: misschien is het al opgeslagen.
    private val waakhondOp = Runnable {
        if (paginaLaadt) {
            val soort = if (laatsteMethode.equals("POST", ignoreCase = true)) Fout.VERSTUREN else Fout.SERVER
            foutTijdensLaden = soort
            b.webView.stopLoading()
            toonFout(soort, b.webView.url ?: laadUrl ?: startUrl)
        }
    }

    private fun startWaakhond() {
        stopWaakhond()
        hoofdThread.postDelayed(waakhondTraag, 8_000)
        hoofdThread.postDelayed(waakhondOp, 40_000)
    }

    private fun stopWaakhond() {
        hoofdThread.removeCallbacks(waakhondTraag)
        hoofdThread.removeCallbacks(waakhondOp)
        if (traag) {
            traag = false
            werkBalkBij()
        }
    }

    // ---------------------------------------------------------------- foutscherm

    private fun richtBalkEnFoutschermIn() {
        b.foutKnop.setOnClickListener { probeerOpnieuw() }
        b.foutTestKnop.setOnClickListener { testVerbinding() }
        b.menuKnop.setOnClickListener { toonMenu(it) }
        werkBalkBij()
    }

    private fun toonFout(soort: Fout, url: String) {
        huidigeFout = soort
        foutUrl = url
        paginaLaadt = false
        stopWaakhond()
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
        b.foutLaag.scrollTo(0, 0)
        if (soort == Fout.VERSTUREN || soort == Fout.BEVEILIGING) {
            hoofdThread.removeCallbacks(aftelTik)
            resterend = 0
            b.foutAftellen.isVisible = false
        } else {
            planOpnieuw()
        }
        werkBalkBij()
    }

    private fun verbergFout() {
        huidigeFout = null
        hoofdThread.removeCallbacks(aftelTik)
        resterend = 0
        b.foutLaag.isVisible = false
        werkBalkBij()
    }

    /** Steeds iets langer wachten (3, 6, 12, 24, 30 s), en zonder netwerk wachten tot het er weer is. */
    private fun planOpnieuw() {
        hoofdThread.removeCallbacks(aftelTik)
        b.foutAftellen.isVisible = true
        if (!verbinding.huidig().verbonden) {
            resterend = 0
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
            werkBalkBij()
            resterend--
            hoofdThread.postDelayed(this, 1_000)
        }
    }

    private fun probeerOpnieuw() {
        hoofdThread.removeCallbacks(aftelTik)
        resterend = 0
        val soort = huidigeFout
        pogingen++
        b.foutAftellen.text = getString(R.string.balk_laden)
        val doel = if (soort == Fout.VERSTUREN) laatsteGoedeUrl ?: startUrl else foutUrl ?: laatsteGoedeUrl ?: startUrl
        if (soort == Fout.VERSTUREN) verbergFout() // de pagina hierna is een gewone, nieuwe pagina
        laad(doel)
    }

    // ---------------------------------------------------------------- verbinding en de balk

    private fun werkVerbindingBij(nieuw: Verbinding.Toestand) {
        val wasVerbonden = toestand?.verbonden
        toestand = nieuw
        // Weer netwerk terwijl het foutscherm staat: meteen verder, niet op het aftellen wachten.
        if (nieuw.verbonden && wasVerbonden == false && (huidigeFout == Fout.GEEN_NETWERK || huidigeFout == Fout.SERVER)) {
            probeerOpnieuw()
        } else if (!nieuw.verbonden && (huidigeFout == Fout.GEEN_NETWERK || huidigeFout == Fout.SERVER)) {
            planOpnieuw()
        }
        werkBalkBij()

        werkInlogVerbindingBij()
        if (nieuw.verbonden && wasVerbonden == false && inlogZichtbaar) controleerWebsite()
    }

    /** Onderaan het inlogscherm: wifi-sterkte en of de website bereikbaar is, nog vóór je je code intikt. */
    private fun werkInlogVerbindingBij() {
        val t = toestand ?: return
        val l = b.inlog
        val netwerk = when (t.soort) {
            Verbinding.Soort.WIFI -> t.signaal?.let { getString(R.string.verbonden_wifi_signaal, signaalWoord(it)) }
                ?: getString(R.string.verbonden_wifi)
            Verbinding.Soort.MOBIEL -> getString(R.string.verbonden_mobiel)
            Verbinding.Soort.GEEN -> getString(R.string.geen_netwerk)
        }
        val site = websiteBereikbaar
        l.inlogVerbinding.text = when {
            !t.verbonden || site == null -> netwerk
            site -> getString(R.string.inlog_site_ok, netwerk)
            else -> getString(R.string.inlog_site_fout, netwerk)
        }
        kleurStip(l.inlogVerbindingStip, if (t.verbonden && site == false) R.color.oranje else stipKleur(t))
    }

    private var websiteBereikbaar: Boolean? = null
    private var websiteCheckLoopt = false

    private fun controleerWebsite() {
        if (websiteCheckLoopt) return
        websiteCheckLoopt = true
        val basisUrl = inst.basisUrl
        Thread {
            val bereikbaar = try {
                Server.meet(applicationContext, basisUrl)
                true
            } catch (e: Exception) {
                false
            }
            runOnUiThread {
                websiteCheckLoopt = false
                websiteBereikbaar = bereikbaar
                werkInlogVerbindingBij()
            }
        }.start()
    }

    private fun signaalWoord(signaal: Int) = getString(
        when (signaal) {
            3 -> R.string.signaal_uitstekend
            2 -> R.string.signaal_goed
            1 -> R.string.signaal_matig
            else -> R.string.signaal_zwak
        },
    )

    @ColorRes
    private fun stipKleur(t: Verbinding.Toestand?): Int = when {
        t == null -> R.color.groen
        !t.verbonden -> R.color.rood
        (t.signaal ?: 3) <= 0 -> R.color.oranje
        else -> R.color.groen
    }

    private fun kleurStip(stip: View, @ColorRes kleur: Int) {
        val vorm = (stip.background.mutate() as? GradientDrawable) ?: return
        vorm.setColor(ContextCompat.getColor(this, kleur))
    }

    private fun werkBalkBij() {
        if (!::b.isInitialized) return
        val t = toestand
        val fout = huidigeFout
        val (achtergrond, stip, tekst) = when {
            t != null && !t.verbonden -> Triple(R.color.rood_balk, R.color.rood, getString(R.string.balk_offline))
            fout == Fout.GEEN_NETWERK || fout == Fout.SERVER -> Triple(
                R.color.rood_balk,
                R.color.rood,
                when {
                    resterend <= 0 -> getString(R.string.balk_laden)
                    fout == Fout.SERVER -> getString(R.string.balk_server_opnieuw, resterend)
                    else -> getString(R.string.balk_opnieuw, resterend)
                },
            )
            traag -> Triple(R.color.oranje_balk, R.color.oranje, getString(R.string.balk_traag))
            else -> {
                val naam = inst.naam ?: ""
                val zwak = t?.signaal != null && t.signaal <= 0
                Triple(R.color.navy, stipKleur(t), if (zwak) "$naam · ${getString(R.string.verbonden_wifi_signaal, getString(R.string.signaal_zwak))}" else naam)
            }
        }
        b.statusBalk.setBackgroundColor(ContextCompat.getColor(this, achtergrond))
        kleurStip(b.statusStip, stip)
        b.statusTekst.text = tekst
    }

    // ---------------------------------------------------------------- menu

    private fun toonMenu(anker: View) {
        val menu = PopupMenu(this, anker)
        menu.menu.add(0, 1, 0, R.string.menu_start)
        menu.menu.add(0, 2, 1, R.string.menu_vernieuwen)
        if (Scanner.isAanwezig(this)) menu.menu.add(0, 3, 2, R.string.menu_scannen)
        menu.menu.add(0, 4, 3, R.string.menu_verbinding)
        menu.menu.add(0, 5, 4, R.string.menu_instellingen)
        menu.menu.add(0, 6, 5, getString(R.string.menu_uitloggen) + (inst.naam?.let { " ($it)" } ?: ""))
        menu.setOnMenuItemClickListener {
            when (it.itemId) {
                1 -> {
                    verbergFout(); laad(startUrl)
                }
                2 -> vernieuwen()
                3 -> Scanner.startScan(this)
                4 -> testVerbinding()
                5 -> openInstellingen()
                6 -> uitloggen(getString(R.string.uitgelogd), vergeetPagina = true)
            }
            true
        }
        menu.show()
    }

    private fun openInstellingen() {
        startActivity(Intent(this, InstellingenActivity::class.java))
    }

    /** Meet drie keer hoe snel de site antwoordt, en vertelt in gewone taal hoe het ervoor staat. */
    private fun testVerbinding() {
        val dialoog = AlertDialog.Builder(this)
            .setTitle(R.string.test_titel)
            .setMessage(R.string.test_bezig)
            .setPositiveButton(R.string.sluiten, null)
            .show()
        val t = verbinding.huidig()
        val basisUrl = inst.basisUrl
        Thread {
            val tijden = mutableListOf<Long>()
            var versie: String? = null
            repeat(3) {
                try {
                    val meting = Server.meet(applicationContext, basisUrl)
                    tijden += meting.milliseconden
                    versie = meting.versie ?: versie
                } catch (e: Exception) {
                }
            }
            runOnUiThread {
                if (!dialoog.isShowing) return@runOnUiThread
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
        }.start()
    }

    // ---------------------------------------------------------------- scannen

    private fun verwerkScan(gescand: String) {
        activiteit()
        if (!ingelogd || inlogZichtbaar) {
            toonMelding(getString(R.string.scan_eerst_inloggen), fout = false)
            return
        }
        if (huidigeFout != null) {
            Toast.makeText(this, R.string.balk_offline, Toast.LENGTH_SHORT).show()
            return
        }
        if (inst.trillen) tril(35)
        // Een QR-code met een link naar de site (zoals op de producten): die pagina openen.
        val alsLink = Uri.parse(gescand)
        if ((alsLink.scheme == "https" || alsLink.scheme == "http") && isSite(alsLink)) {
            laad(gescand)
            return
        }
        b.webView.evaluateJavascript("($scanJs)(${JSONObject.quote(gescand)})") { uitkomst ->
            if (uitkomst == "\"genegeerd\"") Toast.makeText(this, R.string.scan_genegeerd, Toast.LENGTH_SHORT).show()
        }
    }

    private fun tril(ms: Long) {
        val trilmotor = getSystemService(VIBRATOR_SERVICE) as? Vibrator ?: return
        if (Build.VERSION.SDK_INT >= 26) {
            trilmotor.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            trilmotor.vibrate(ms)
        }
    }

    // ---------------------------------------------------------------- terug-knop

    private fun terug() {
        when {
            inlogZichtbaar -> moveTaskToBack(true)
            huidigeFout != null -> {
                verbergFout()
                if (b.webView.canGoBack()) b.webView.goBack() else laad(startUrl)
            }
            else -> {
                // Eerst een open venster of de zoekresultaten van de site sluiten, dan pas een pagina terug.
                b.webView.evaluateJavascript(
                    "(function(){var m=document.querySelector('.modal-overlay.open');if(m){m.classList.remove('open');return 1;}" +
                        "var r=document.getElementById('pda-zoek-resultaten');if(r&&!r.hidden){r.hidden=true;return 1;}return 0;})()",
                ) { gesloten ->
                    if (gesloten == "1") return@evaluateJavascript
                    if (b.webView.canGoBack()) b.webView.goBack() else moveTaskToBack(true)
                }
            }
        }
    }

    /** Naar de Play Store voor een nieuwere webweergave (op Android 7 t/m 9 is dat Chrome). */
    private fun werkWebViewBij() {
        val pakket = if (Build.VERSION.SDK_INT in 24..28) "com.android.chrome" else "com.google.android.webview"
        for (adres in listOf("market://details?id=$pakket", "https://play.google.com/store/apps/details?id=$pakket")) {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(adres)))
                return
            } catch (e: ActivityNotFoundException) {
            }
        }
        Toast.makeText(this, R.string.geen_app, Toast.LENGTH_SHORT).show()
    }

    private companion object {
        /** Vanaf Chrome 72 stuurt fetch() standaard de inlogcookie mee; de site rekent daarop (net als op
         * CSS-variabelen en NodeList.forEach, die zijn ouder). */
        const val MIN_WEBVIEW = 72
    }

    private fun webViewVersie(): Int? = try {
        Regex("Chrome/(\\d+)").find(WebSettings.getDefaultUserAgent(this))?.groupValues?.get(1)?.toIntOrNull()
    } catch (e: Exception) {
        null
    }
}
