package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper

/** Houdt bij of de handterminal netwerk heeft, en hoe sterk de wifi is. Meldt veranderingen op de UI-thread. */
class Verbinding(context: Context, private val bijWijziging: (Toestand) -> Unit) {

    enum class Soort { WIFI, MOBIEL, GEEN }

    /** [signaal]: 0 (zwak) t/m 3 (uitstekend), alleen bij wifi. */
    class Toestand(val soort: Soort, val signaal: Int?, val dbm: Int?) {
        val verbonden get() = soort != Soort.GEEN
    }

    private val app = context.applicationContext
    private val cm = app.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val wifi = app.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val hoofdThread = Handler(Looper.getMainLooper())
    private var actief = false

    private val terugroep = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = melden()
        override fun onLost(network: Network) = melden()
        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = melden()
    }

    // Een paar keer per minuut de wifi-sterkte bijwerken; die geeft geen eigen melding.
    private val signaalTik = object : Runnable {
        override fun run() {
            bijWijziging(huidig())
            hoofdThread.postDelayed(this, 20_000)
        }
    }

    fun start() {
        if (actief) return
        actief = true
        try {
            cm.registerNetworkCallback(
                NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(),
                terugroep,
            )
        } catch (e: Exception) {
            // Zonder meldingen werkt de rest nog gewoon: de sterkte-tik en de foutafhandeling van de WebView.
        }
        hoofdThread.post(signaalTik)
    }

    fun stop() {
        if (!actief) return
        actief = false
        try {
            cm.unregisterNetworkCallback(terugroep)
        } catch (e: Exception) {
        }
        hoofdThread.removeCallbacks(signaalTik)
    }

    private fun melden() {
        // Even wachten: bij het wisselen van netwerk komt "kwijt" vaak vlak voor "beschikbaar".
        hoofdThread.removeCallbacks(meldNu)
        hoofdThread.postDelayed(meldNu, 400)
    }

    private val meldNu = Runnable { if (actief) bijWijziging(huidig()) }

    @Suppress("DEPRECATION") // activeNetworkInfo werkt op alle Android-versies van de TC51 (6 t/m 8.1) en nieuwer
    fun huidig(): Toestand {
        val info = cm.activeNetworkInfo
        if (info == null || !info.isConnected) return Toestand(Soort.GEEN, null, null)
        if (info.type != ConnectivityManager.TYPE_WIFI) return Toestand(Soort.MOBIEL, null, null)
        val rssi = try {
            wifi.connectionInfo?.rssi
        } catch (e: Exception) {
            null
        }
        val signaal = rssi?.takeIf { it > -127 }?.let { WifiManager.calculateSignalLevel(it, 4) }
        return Toestand(Soort.WIFI, signaal, rssi?.takeIf { it > -127 })
    }
}
