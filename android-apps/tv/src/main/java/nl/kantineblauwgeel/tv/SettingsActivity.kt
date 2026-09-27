package nl.kantineblauwgeel.tv

import android.os.Bundle
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tv.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    private val minZoom = 50
    private val maxZoom = 200
    private val stap = 5

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        koppelZoomRegelaar(
            Screens.PRIJZEN, binding.prijzenTitel, binding.prijzenZoomWaarde,
            binding.prijzenZoomSeekbar, binding.prijzenZoomResetKnop
        )
        koppelZoomRegelaar(
            Screens.DIAS, binding.diasTitel, binding.diasZoomWaarde,
            binding.diasZoomSeekbar, binding.diasZoomResetKnop
        )
        koppelZoomRegelaar(
            Screens.GEDEELD, binding.gedeeldTitel, binding.gedeeldZoomWaarde,
            binding.gedeeldZoomSeekbar, binding.gedeeldZoomResetKnop
        )

        binding.autoStartCheckbox.isChecked = Prefs.isAutoStartEnabled(this)
        binding.autoStartCheckbox.setOnCheckedChangeListener { _, isChecked ->
            Prefs.setAutoStartEnabled(this, isChecked)
        }
    }

    /** Zet 1 scherm z'n eigen zoom-regelaar op -- elk scherm heeft zijn eigen
     * opgeslagen niveau (zie Prefs.getZoom/setZoom), losstaand van de andere
     * 2, want niet elk scherm/tv-aansluiting toont de website even groot. */
    private fun koppelZoomRegelaar(
        scherm: Screen,
        titel: TextView,
        waarde: TextView,
        seekbar: SeekBar,
        resetKnop: Button
    ) {
        titel.text = scherm.titel

        fun toon(percentage: Int) {
            waarde.text = getString(R.string.zoom_percentage, percentage)
        }

        val huidigeZoom = Prefs.getZoom(this, scherm.sleutel)
        seekbar.max = (maxZoom - minZoom) / stap
        seekbar.progress = (huidigeZoom - minZoom) / stap
        toon(huidigeZoom)

        seekbar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val percentage = minZoom + progress * stap
                toon(percentage)
                Prefs.setZoom(this@SettingsActivity, scherm.sleutel, percentage)
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        resetKnop.setOnClickListener {
            seekbar.progress = (Prefs.DEFAULT_ZOOM - minZoom) / stap
            toon(Prefs.DEFAULT_ZOOM)
            Prefs.setZoom(this, scherm.sleutel, Prefs.DEFAULT_ZOOM)
        }
    }
}
