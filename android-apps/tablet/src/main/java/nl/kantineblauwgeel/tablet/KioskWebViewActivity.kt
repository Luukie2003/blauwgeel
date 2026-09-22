package nl.kantineblauwgeel.tablet

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivityKioskWebviewBinding

/** Toont 1 van de 3 bestaande, inlogvrije kiosk-URL's van de website
 * (/kiosk/prijzen, /kiosk/scherm of /kiosk/tv) voledig schermvullend, zonder
 * systeembalken -- elk scherm ververst zichzelf al via JavaScript-polling op
 * de website, deze activity hoeft daar niets extra's voor te doen. Terug
 * (hardware-knop) gaat terug naar het schermkiezer. */
class KioskWebViewActivity : AppCompatActivity() {

    private lateinit var binding: ActivityKioskWebviewBinding

    companion object {
        private const val EXTRA_URL = "extra_url"

        fun intentVoor(context: Context, url: String): Intent =
            Intent(context, KioskWebViewActivity::class.java).putExtra(EXTRA_URL, url)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityKioskWebviewBinding.inflate(layoutInflater)
        setContentView(binding.root)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        verbergSysteembalken()

        val url = intent.getStringExtra(EXTRA_URL) ?: Screens.url(this, Screens.GEDEELD)

        binding.webview.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            cacheMode = WebSettings.LOAD_DEFAULT
        }

        binding.webview.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                super.onReceivedError(view, request, error)
                if (request.isForMainFrame) binding.foutmelding.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, finishedUrl: String?) {
                super.onPageFinished(view, finishedUrl)
                binding.foutmelding.visibility = View.GONE
            }
        }

        binding.opnieuwProberen.setOnClickListener {
            binding.foutmelding.visibility = View.GONE
            binding.webview.loadUrl(url)
        }

        binding.webview.loadUrl(url)
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
            finish()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        binding.webview.destroy()
        super.onDestroy()
    }
}
