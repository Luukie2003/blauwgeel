package nl.kantineblauwgeel.tv

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tv.databinding.ActivityPlayerBinding

class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding

    companion object {
        private const val EXTRA_URL = "extra_url"

        fun intentVoor(context: Context, url: String): Intent =
            Intent(context, PlayerActivity::class.java).putExtra(EXTRA_URL, url)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPlayerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        verbergSysteembalken()

        val url = intent.getStringExtra(EXTRA_URL) ?: Screens.GEDEELD.url

        binding.webview.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            textZoom = Prefs.getZoom(this@PlayerActivity)
            cacheMode = WebSettings.LOAD_DEFAULT
        }

        binding.webview.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                super.onReceivedError(view, errorCode, description, failingUrl)
                binding.foutmelding.visibility = View.VISIBLE
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

    override fun onResume() {
        super.onResume()
        // De zoom kan gewijzigd zijn via het instellingenscherm; opnieuw toepassen.
        binding.webview.settings.textZoom = Prefs.getZoom(this)
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
        binding.webview.destroy()
        super.onDestroy()
    }
}
