package nl.kantineblauwgeel.tablet

import android.content.Intent
import android.os.Bundle
import android.view.View
import nl.kantineblauwgeel.tablet.databinding.ActivityBeheerMenuBinding

/** Getoond na een geldige tablet-code: het menu. Bovenaan het prijzenscherm (producten, acties, bardienst,
 * uitgelicht, wedstrijddag), onderaan de kantine-tv zelf (2.0: tv's, dia's, uitverkocht, timer). Elke kaart opent een
 * volledig native scherm dat met de site praat via Api.kt, met de rechten van het account van de code. "Andere code
 * invoeren" logt uit en gaat terug naar de code-invoer. */
class BeheerMenuActivity : BasisActivity() {

    private lateinit var binding: ActivityBeheerMenuBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityBeheerMenuBinding.inflate(layoutInflater)
        setContentView(binding.root)

        Sessie.naam?.let {
            binding.ingelogdAlsTekst.text = getString(R.string.ingelogd_als, it)
            binding.ingelogdAlsTekst.visibility = View.VISIBLE
        }

        binding.knopProducten.setOnClickListener {
            startActivity(Intent(this, ProductenActivity::class.java))
        }
        binding.knopActies.setOnClickListener {
            startActivity(Intent(this, ActiesActivity::class.java))
        }
        binding.knopBardienst.setOnClickListener {
            startActivity(Intent(this, BardienstenActivity::class.java))
        }
        binding.knopUitgelicht.setOnClickListener {
            startActivity(Intent(this, UitgelichtActivity::class.java))
        }
        binding.knopWedstrijddag.setOnClickListener {
            startActivity(Intent(this, WedstrijddagActivity::class.java))
        }
        binding.knopTvs.setOnClickListener { startActivity(Intent(this, TvsActivity::class.java)) }
        binding.knopDias.setOnClickListener { startActivity(Intent(this, DiasActivity::class.java)) }
        binding.knopUitverkocht.setOnClickListener { startActivity(Intent(this, UitverkochtActivity::class.java)) }
        binding.knopTimer.setOnClickListener { startActivity(Intent(this, TimerActivity::class.java)) }
        binding.terugKnop.setOnClickListener {
            Sessie.uitloggen()
            finish()
        }
    }
}
