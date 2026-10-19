package nl.kantineblauwgeel.handterminal

import android.content.Intent
import android.os.Bundle
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.ActivityVergrendeldBinding
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Het vergrendel-scherm: de site is afgesloten met de noodstop (Beheer > Noodstop op de site, zie noodstop.py). Net als
 * het vergrendel-scherm op de tv. Iedereen is uitgelogd en de app doet niets meer, ook niet op het toestel zelf (zoeken,
 * scannen, tellen). Elke paar seconden kijkt hij of de site weer open is, en dan kun je opnieuw inloggen.
 * Bewust geen BasisActivity: geen kopbalk, menu of scanner. */
class VergrendeldActivity : AppCompatActivity() {

    private lateinit var b: ActivityVergrendeldBinding
    private var kijken: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityVergrendeldBinding.inflate(layoutInflater)
        setContentView(b.root)
        Sessie.wis(this)
        b.titel.text = getText(R.string.vergrendeld_titel)
        b.sinds.text = getString(R.string.vergrendeld_sinds, SimpleDateFormat("HH:mm", Locale("nl", "NL")).format(Date()))
        // Terug brengt je niet naar een scherm van de app; de app gaat alleen naar de achtergrond.
        onBackPressedDispatcher.addCallback(this) { moveTaskToBack(true) }
    }

    override fun onResume() {
        super.onResume()
        kijken = lifecycleScope.launch {
            while (isActive) {
                delay(BasisActivity.NOODSTOP_ELKE_MS)
                if (Api.noodstopActief(applicationContext) == false) return@launch weerOpen()
            }
        }
    }

    override fun onPause() {
        super.onPause()
        kijken?.cancel()
    }

    private fun weerOpen() {
        startActivity(
            Intent(this, InlogActivity::class.java)
                .putExtra(InlogActivity.EXTRA_MELDING, getString(R.string.weer_open))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        finish()
    }
}
