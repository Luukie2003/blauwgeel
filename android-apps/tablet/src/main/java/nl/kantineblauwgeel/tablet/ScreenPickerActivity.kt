package nl.kantineblauwgeel.tablet

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivityScreenPickerBinding

/** Getoond na een geldige tablet-code: kies welk van de 3 kiosk-schermen van
 * de website hier moet komen. Terug-knop (hardware of op het scherm) gaat
 * terug naar de code-invoer -- er is bewust geen manier om vanaf hier bij de
 * rest van de website te komen. */
class ScreenPickerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityScreenPickerBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityScreenPickerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.knopPrijzen.text = Screens.PRIJZEN.titel
        binding.knopDias.text = Screens.DIAS.titel
        binding.knopGedeeld.text = Screens.GEDEELD.titel

        binding.knopPrijzen.setOnClickListener { openScherm(Screens.PRIJZEN) }
        binding.knopDias.setOnClickListener { openScherm(Screens.DIAS) }
        binding.knopGedeeld.setOnClickListener { openScherm(Screens.GEDEELD) }
        binding.terugKnop.setOnClickListener { finish() }
    }

    private fun openScherm(scherm: Scherm) {
        startActivity(KioskWebViewActivity.intentVoor(this, Screens.url(this, scherm)))
    }
}
