package nl.kantineblauwgeel.tablet

import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebChromeClient.FileChooserParams
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.ActionBarDrawerToggle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.GravityCompat
import nl.kantineblauwgeel.tablet.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var bestandCallback: ValueCallback<Array<Uri>>? = null
    private var geladenBaseUrl: String? = null

    private val bestandsKiezerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val data = result.data
        val uris: Array<Uri>? = if (result.resultCode == Activity.RESULT_OK && data != null) {
            val clip = data.clipData
            when {
                clip != null -> Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
                data.data != null -> arrayOf(data.data!!)
                else -> null
            }
        } else null
        bestandCallback?.onReceiveValue(uris)
        bestandCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        val toggle = ActionBarDrawerToggle(
            this, binding.drawerLayout, binding.toolbar,
            R.string.drawer_open, R.string.drawer_close
        )
        binding.drawerLayout.addDrawerListener(toggle)
        toggle.syncState()

        binding.navView.setNavigationItemSelectedListener { item ->
            if (item.itemId == R.id.nav_instellingen) {
                startActivity(Intent(this, SettingsActivity::class.java))
            } else {
                val pad = padVoorMenuItem(item.itemId)
                if (pad != null) {
                    binding.webview.loadUrl(Prefs.getBaseUrl(this) + pad)
                }
            }
            binding.drawerLayout.closeDrawers()
            true
        }

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(binding.webview, false)

        binding.webview.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            cacheMode = WebSettings.LOAD_DEFAULT
        }

        binding.webview.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                return when {
                    url.startsWith(Prefs.getBaseUrl(this@MainActivity)) -> false
                    url.startsWith("tel:") || url.startsWith("mailto:") -> {
                        startActivity(Intent(Intent.ACTION_VIEW, request.url))
                        true
                    }
                    else -> false
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                binding.verversen.isRefreshing = false
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                binding.verversen.isRefreshing = false
            }
        }

        binding.webview.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                bestandCallback?.onReceiveValue(null)
                bestandCallback = filePathCallback

                val intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                }
                return try {
                    bestandsKiezerLauncher.launch(intent)
                    true
                } catch (e: Exception) {
                    bestandCallback = null
                    false
                }
            }
        }

        binding.webview.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            downloadStarten(url, contentDisposition, mimeType)
        }

        binding.verversen.setOnRefreshListener { binding.webview.reload() }

        if (savedInstanceState == null) {
            geladenBaseUrl = Prefs.getBaseUrl(this)
            binding.webview.loadUrl(geladenBaseUrl!!)
        }
    }

    private fun padVoorMenuItem(itemId: Int): String? = when (itemId) {
        R.id.nav_dashboard -> "/"
        R.id.nav_voorraad -> "/voorraadoverzicht"
        R.id.nav_producten -> "/producten"
        R.id.nav_acties -> "/kiosk/prijzen/acties"
        R.id.nav_bardiensten -> "/kiosk/prijzen/bardienst"
        R.id.nav_prijzenscherm_instellingen -> "/kiosk/prijzen/instellingen"
        R.id.nav_dias_sponsoren -> "/kiosk/sponsoren-leden"
        R.id.nav_kiosk_overzicht -> "/kiosk"
        else -> null
    }

    private fun downloadStarten(url: String, contentDisposition: String?, mimeType: String?) {
        val bestandsnaam = URLUtil.guessFileName(url, contentDisposition, mimeType)
        val request = DownloadManager.Request(Uri.parse(url)).apply {
            setMimeType(mimeType)
            addRequestHeader("cookie", CookieManager.getInstance().getCookie(url))
            setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, bestandsnaam)
        }
        val manager = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        manager.enqueue(request)
    }

    override fun onResume() {
        super.onResume()
        val huidigeBaseUrl = Prefs.getBaseUrl(this)
        if (geladenBaseUrl != null && geladenBaseUrl != huidigeBaseUrl) {
            geladenBaseUrl = huidigeBaseUrl
            binding.webview.loadUrl(huidigeBaseUrl)
        }
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        when {
            binding.drawerLayout.isDrawerOpen(GravityCompat.START) -> binding.drawerLayout.closeDrawers()
            binding.webview.canGoBack() -> binding.webview.goBack()
            else -> super.onBackPressed()
        }
    }

    override fun onDestroy() {
        binding.webview.destroy()
        super.onDestroy()
    }
}
