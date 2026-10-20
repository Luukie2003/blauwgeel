package nl.kantineblauwgeel.tv

import android.os.Bundle
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tv.databinding.ActivitySettingsBinding

/** Instellingen (de OK-knop op de afstandsbediening): hoe groot de prijzenlijst en de dia's op deze tv staan. Niet elke
 * pagina past op dezelfde grootte; elk scherm heeft daarom zijn eigen zoom, bewaard op de tv (ook na herstarten en een
 * update). "Zoals op de site" laat het scherm de grootte volgen die op de site voor deze tv is gekozen. */
class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    private val minZoom = 50
    private val maxZoom = 200
    private val stap = 5

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        regelaar(Prefs.PRIJZEN, binding.prijzenWaarde, binding.prijzenSeekbar, binding.prijzenSiteKnop)
        regelaar(Prefs.DIAS, binding.diasWaarde, binding.diasSeekbar, binding.diasSiteKnop)
        binding.versie.text = getString(R.string.app_versie, BuildConfig.VERSION_NAME)
        binding.prijzenSeekbar.requestFocus()
    }

    private fun regelaar(scherm: String, waarde: TextView, balk: SeekBar, siteKnop: Button) {
        balk.max = (maxZoom - minZoom) / stap
        fun toon() {
            val eigen = Prefs.getEigenZoom(this, scherm)
            val zoom = eigen ?: Prefs.getSiteZoom(this)
            balk.progress = (zoom - minZoom) / stap
            waarde.text = if (eigen == null) getString(R.string.zoom_zoals_site, zoom) else getString(R.string.zoom_percentage, zoom)
        }
        toon()
        balk.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, vanGebruiker: Boolean) {
                if (!vanGebruiker) return
                val zoom = minZoom + progress * stap
                Prefs.setEigenZoom(this@SettingsActivity, scherm, zoom)
                waarde.text = getString(R.string.zoom_percentage, zoom)
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })
        siteKnop.setOnClickListener {
            Prefs.setEigenZoom(this, scherm, null)
            toon()
        }
    }
}
