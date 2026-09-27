package nl.kantineblauwgeel.tv

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tv.databinding.ActivitySplashBinding

/** Puur cosmetisch openingsscherm bij het handmatig starten van de app vanuit
 * de tv-launcher -- laadt zelf niets echts in (de kioskschermen doen dat pas
 * in PlayerActivity), maar geeft de app een merkmoment i.p.v. meteen kaal het
 * menu te tonen. Duurt daarom een vaste, fictieve tijd i.p.v. te wachten op
 * iets dat hier nog niet speelt. BootReceiver slaat dit scherm bewust over
 * (start rechtstreeks PlayerActivity) -- na een stroomstoring moet het
 * kioskscherm zo snel mogelijk terug in beeld zijn, niet later. */
class SplashActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(ActivitySplashBinding.inflate(layoutInflater).root)

        Handler(Looper.getMainLooper()).postDelayed({
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }, SPLASH_DUUR_MS)
    }

    companion object {
        private const val SPLASH_DUUR_MS = 4000L
    }
}
