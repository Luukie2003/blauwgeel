package nl.kantineblauwgeel.tv

import android.annotation.SuppressLint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.WindowManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/** Het spel van de club, Shout-out! (Screens.SPEL_URL), schermvullend op de tv: de geheime optie van de tv-app (links,
 * links, rechts, rechts, links, rechts op de afstandsbediening, zie PlayerActivity).
 *
 * De tv is daarbij het grote scherm: het spel laat een code zien waarmee de spelleider zijn telefoon koppelt, en speelt de
 * muziek af. Een tv zonder aanraakscherm kiest het spel zelf als scherm, en de clubcode vult de app in; daarna onthoudt
 * het spel allebei. Het geluid zet het spel pas aan na één klik op het scherm: dat doet de app zelf, en OK op de
 * afstandsbediening ook (tik()). Terug brengt je weer bij de kantine-tv. Bewust zonder de KantineTv-brug van
 * PlayerActivity: dit is een site van buiten. */
class SpelActivity : AppCompatActivity() {

    private lateinit var webview: WebView
    private val klok = Handler(Looper.getMainLooper())

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webview = WebView(this)
        setContentView(webview)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        verbergSysteembalken()

        webview.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true  // daarin bewaart het spel de clubcode en dat dit het scherm is
            mediaPlaybackRequiresUserGesture = false  // de muziek speelt, zonder dat iemand op het scherm hoeft te tikken
            // Een tv is voor een webpagina maar 960 bij 540 groot; het spel is gemaakt voor een beamer van 1920 bij 1080.
            // Met deze twee mag de pagina breder zijn (zie SPEL_BREEDTE) en verkleint de tv hem tot hij past.
            useWideViewPort = true
            loadWithOverviewMode = true
        }
        webview.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                view?.evaluateJavascript(ALS_SCHERM_EN_ONTGRENDELD, null)
                klok.removeCallbacksAndMessages(null)
                klok.postDelayed({ tik() }, GELUID_NA_MS)  // na het ontgrendelen: het geluid aan
            }

            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                finish()  // terug naar de kantine-tv in plaats van een vastgelopen scherm
                return true
            }
        }
        webview.loadUrl(Screens.SPEL_URL)
        Toast.makeText(this, R.string.spel_terug, Toast.LENGTH_LONG).show()
    }

    /** Een tik helemaal linksboven, waar in het spel geen knop staat: zo telt het als die ene klik op het scherm. */
    private fun tik() {
        val nu = SystemClock.uptimeMillis()
        for ((actie, wanneer) in listOf(MotionEvent.ACTION_DOWN to nu, MotionEvent.ACTION_UP to nu + 50)) {
            val gebeurtenis = MotionEvent.obtain(nu, wanneer, actie, 8f, 8f, 0)
            gebeurtenis.source = InputDevice.SOURCE_TOUCHSCREEN
            webview.dispatchTouchEvent(gebeurtenis)
            gebeurtenis.recycle()
        }
    }

    /** OK op de afstandsbediening: een klik op het scherm (zie tik()). */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || event.keyCode == KeyEvent.KEYCODE_ENTER) {
            if (event.action == KeyEvent.ACTION_UP) tik()
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            finish()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        klok.removeCallbacksAndMessages(null)
        webview.destroy()
        super.onDestroy()
    }

    companion object {
        /** Zo breed (in pixels van een webpagina) staat het spel op de tv, zoals op een beamer. */
        private const val SPEL_BREEDTE = 1920

        /** Zo lang na het laden tikt de app één keer op het scherm, als het spel ontgrendeld is. */
        private const val GELUID_NA_MS = 4000L

        /** Eerst de breedte van de pagina: SPEL_BREEDTE in plaats van die van de tv. Vraagt het spel welk apparaat dit is
         * (dat doet het alleen op een scherm met aanraken): het scherm, en één keer opnieuw laden. Vraagt het de
         * clubcode: invullen en op Ontgrendel drukken, net als met de hand. */
        private val ALS_SCHERM_EN_ONTGRENDELD = """
            (function () {
              var vp = document.querySelector('meta[name="viewport"]');
              if (vp && vp.getAttribute('content') !== 'width=$SPEL_BREEDTE') vp.setAttribute('content', 'width=$SPEL_BREEDTE');
              try {
                if (matchMedia('(pointer:coarse)').matches && !sessionStorage.getItem('kantinetv-scherm')) {
                  sessionStorage.setItem('kantinetv-scherm', '1');
                  sessionStorage.setItem('shoutout-skipask', '1');
                  localStorage.setItem('shoutout-device', 'screen');
                  location.reload();
                  return;
                }
              } catch (e) {}
              var keer = 0, klok = setInterval(function () {
                var veld = document.getElementById('lockpw'), knop = document.querySelector('[data-a="unlock-pw"]');
                if (veld && knop) { clearInterval(klok); veld.value = '${Screens.SPEL_CLUBCODE}'; knop.click(); }
                else if (++keer > 20) clearInterval(klok);
              }, 250);
            })();
        """.trimIndent()
    }
}
