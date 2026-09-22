package nl.kantineblauwgeel.tv

import android.os.Bundle
import android.widget.SeekBar
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

        val huidigeZoom = Prefs.getZoom(this)
        binding.zoomSeekbar.max = (maxZoom - minZoom) / stap
        binding.zoomSeekbar.progress = (huidigeZoom - minZoom) / stap
        binding.zoomWaarde.text = getString(R.string.zoom_percentage, huidigeZoom)

        binding.zoomSeekbar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val percentage = minZoom + progress * stap
                binding.zoomWaarde.text = getString(R.string.zoom_percentage, percentage)
                if (fromUser) {
                    Prefs.setZoom(this@SettingsActivity, percentage)
                }
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        binding.zoomResetKnop.setOnClickListener {
            binding.zoomSeekbar.progress = (Prefs.DEFAULT_ZOOM - minZoom) / stap
        }

        binding.autoStartCheckbox.isChecked = Prefs.isAutoStartEnabled(this)
        binding.autoStartCheckbox.setOnCheckedChangeListener { _, isChecked ->
            Prefs.setAutoStartEnabled(this, isChecked)
        }
    }
}
