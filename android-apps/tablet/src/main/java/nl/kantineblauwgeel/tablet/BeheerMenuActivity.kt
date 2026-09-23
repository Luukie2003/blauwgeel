package nl.kantineblauwgeel.tablet

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivityBeheerMenuBinding

/** Getoond na een geldige tablet-code: menu met de basics die vanaf dit
 * toestel aan te passen zijn. Elke kaart opent een volledig native scherm
 * (geen WebView) dat rechtstreeks met de bestaande website-routes praat via
 * Api.kt, met de rechten van het account van de code. Terug-knop (hardware
 * of op het scherm) gaat terug naar de code-invoer. */
class BeheerMenuActivity : AppCompatActivity() {

    private lateinit var binding: ActivityBeheerMenuBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityBeheerMenuBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.knopProducten.setOnClickListener {
            startActivity(Intent(this, ProductenActivity::class.java))
        }
        binding.knopActies.setOnClickListener {
            startActivity(Intent(this, ActiesActivity::class.java))
        }
        binding.knopBardienst.setOnClickListener {
            startActivity(Intent(this, BardienstenActivity::class.java))
        }
        binding.terugKnop.setOnClickListener { finish() }
    }
}
