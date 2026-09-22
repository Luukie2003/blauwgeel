package nl.kantineblauwgeel.tablet

import android.os.Bundle
import android.webkit.CookieManager
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.baseUrlVeld.setText(Prefs.getBaseUrl(this))

        binding.opslaanKnop.setOnClickListener {
            var url = binding.baseUrlVeld.text.toString().trim()
            if (url.isEmpty()) url = Prefs.DEFAULT_BASE_URL
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                url = "https://$url"
            }
            url = url.trimEnd('/')
            Prefs.setBaseUrl(this, url)
            Toast.makeText(this, R.string.instellingen_opgeslagen, Toast.LENGTH_SHORT).show()
            finish()
        }

        binding.uitloggenKnop.setOnClickListener {
            CookieManager.getInstance().removeAllCookies(null)
            CookieManager.getInstance().flush()
            Toast.makeText(this, R.string.uitgelogd, Toast.LENGTH_SHORT).show()
        }
    }
}
