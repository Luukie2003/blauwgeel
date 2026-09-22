package nl.kantineblauwgeel.tv

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tv.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.knopPrijzen.text = Screens.PRIJZEN.titel
        binding.knopDias.text = Screens.DIAS.titel
        binding.knopGedeeld.text = Screens.GEDEELD.titel

        binding.knopPrijzen.setOnClickListener { openScherm(Screens.PRIJZEN) }
        binding.knopDias.setOnClickListener { openScherm(Screens.DIAS) }
        binding.knopGedeeld.setOnClickListener { openScherm(Screens.GEDEELD) }
        binding.knopInstellingen.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        binding.knopPrijzen.requestFocus()
    }

    private fun openScherm(scherm: Screen) {
        Prefs.setLastUrl(this, scherm.url)
        startActivity(PlayerActivity.intentVoor(this, scherm.url))
    }
}
