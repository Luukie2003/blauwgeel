package nl.kantineblauwgeel.tablet

import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/** Gedeeld gedrag van alle schermen na het inloggen (2.0):
 * - Automatisch uitloggen na [UITLOG_MINUTEN] minuten zonder aanraken, zodat niemand op jouw naam verder werkt.
 * - De noodstop (zie noodstop.py op de site): elke 15 seconden kijkt het scherm of de site is afgesloten; zo ja, dan
 *   logt de app uit en gaat hij naar het codescherm met de melding.
 * - Een verlopen sessie (Api.NietIngelogd) gaat ook terug naar het codescherm.
 * [opAchtergrond] draait een aanroep op een eigen thread en vangt die fouten op. */
abstract class BasisActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())
    private val controleer = object : Runnable {
        override fun run() {
            if (System.currentTimeMillis() - Sessie.laatsteAanraking > UITLOG_MINUTEN * 60_000L) {
                naarCodescherm(getString(R.string.automatisch_uitgelogd))
                return
            }
            Thread {
                val actief = try {
                    Api.get(this@BasisActivity, "/noodstop/status").optBoolean("actief")
                } catch (e: Api.Noodstop) {
                    true
                } catch (e: Exception) {
                    false // geen verbinding: dan weten we het niet, gewoon doorgaan
                }
                runOnUiThread { if (actief) naarCodescherm(getString(R.string.noodstop_actief)) }
            }.start()
            handler.postDelayed(this, 15_000)
        }
    }

    override fun onResume() {
        super.onResume()
        if (!Sessie.ingelogd()) return naarCodescherm(null)
        handler.post(controleer)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(controleer)
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        Sessie.laatsteAanraking = System.currentTimeMillis()
        return super.dispatchTouchEvent(ev)
    }

    /** Uitloggen en terug naar het codescherm, met een melding (of zonder). */
    fun naarCodescherm(melding: String?) {
        Sessie.uitloggen()
        startActivity(Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
            .putExtra(MainActivity.EXTRA_MELDING, melding))
        finish()
    }

    /** [werk] op een eigen thread; het resultaat met [klaar] op het scherm. Een fout gaat naar [fout] (standaard: een
     * melding), behalve uitgelogd en de noodstop: dan terug naar het codescherm. */
    fun <T> opAchtergrond(werk: () -> T, fout: ((Exception) -> Unit)? = null, klaar: (T) -> Unit) {
        Thread {
            try {
                val uitkomst = werk()
                runOnUiThread { if (!isFinishing) klaar(uitkomst) }
            } catch (e: Api.NietIngelogd) {
                runOnUiThread { naarCodescherm(e.message) }
            } catch (e: Api.Noodstop) {
                runOnUiThread { naarCodescherm(getString(R.string.noodstop_actief)) }
            } catch (e: Exception) {
                runOnUiThread {
                    if (fout != null) fout(e) else melding(e.message ?: getString(R.string.geen_verbinding))
                }
            }
        }.start()
    }

    fun melding(tekst: String) = Toast.makeText(this, tekst, Toast.LENGTH_LONG).show()

    companion object {
        const val UITLOG_MINUTEN = 10
    }
}
