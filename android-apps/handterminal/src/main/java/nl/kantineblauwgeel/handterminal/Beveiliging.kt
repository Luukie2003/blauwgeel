package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.net.http.SslCertificate
import android.os.Build
import java.io.ByteArrayInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Collections
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

/** Veilige verbindingen, ook op oude Android-versies.
 *
 * De site gebruikt een Let's Encrypt-certificaat dat terugleidt naar ISRG Root X1. Android 6 en 7.0 kennen dat
 * rootcertificaat niet, en de Zebra TC51 draait vaak nog Android 6. Daarom zit het rootcertificaat in de app
 * (res/raw) en vertrouwen we het naast de certificaten van het toestel zelf. Vanaf Android 7.0 doet
 * res/xml/netwerkbeveiliging.xml dit voor alles; op Android 6 regelen we het hier:
 *
 * - eigen verzoeken (inloggen, verbinding testen) gaan via [open] met een TrustManager die het toestel én de
 *   meegeleverde rootcertificaten vertrouwt;
 * - de WebView kent alleen de certificaten van het toestel en meldt dan een SSL-fout. [isZelfdeAlsGecontroleerd]
 *   kijkt dan of de WebView precies hetzelfde certificaat kreeg als een verbinding die wij wél volledig hebben
 *   gecontroleerd (keten én hostnaam). Alleen dan gaat de WebView verder. */
object Beveiliging {

    @Volatile private var socketFactory: SSLSocketFactory? = null
    private val goedgekeurd = Collections.synchronizedSet(HashSet<String>())

    fun open(context: Context, url: String): HttpURLConnection {
        val verbinding = URL(url).openConnection() as HttpURLConnection
        if (verbinding is HttpsURLConnection) verbinding.sslSocketFactory = sslSocketFactory(context)
        return verbinding
    }

    private fun sslSocketFactory(context: Context): SSLSocketFactory {
        socketFactory?.let { return it }
        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, arrayOf(vertrouwen(context)), null)
        return sslContext.socketFactory.also { socketFactory = it }
    }

    private fun trustManager(keyStore: KeyStore?): X509TrustManager {
        val fabriek = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
        fabriek.init(keyStore)
        return fabriek.trustManagers.filterIsInstance<X509TrustManager>().first()
    }

    private fun vertrouwen(context: Context): X509TrustManager {
        val toestel = trustManager(null)
        val eigen = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null, null) }
        val fabriek = CertificateFactory.getInstance("X.509")
        listOf(R.raw.isrg_root_x1, R.raw.isrg_root_x2).forEachIndexed { i, bron ->
            context.resources.openRawResource(bron).use { eigen.setCertificateEntry("isrg$i", fabriek.generateCertificate(it)) }
        }
        val meegeleverd = trustManager(eigen)
        return object : X509TrustManager {
            override fun checkClientTrusted(keten: Array<X509Certificate>, soort: String) =
                toestel.checkClientTrusted(keten, soort)

            override fun checkServerTrusted(keten: Array<X509Certificate>, soort: String) {
                try {
                    toestel.checkServerTrusted(keten, soort)
                } catch (e: CertificateException) {
                    meegeleverd.checkServerTrusted(keten, soort)
                }
            }

            override fun getAcceptedIssuers(): Array<X509Certificate> = toestel.acceptedIssuers + meegeleverd.acceptedIssuers
        }
    }

    /** Draait niet op de UI-thread (maakt zelf verbinding). */
    fun isZelfdeAlsGecontroleerd(context: Context, certificaat: SslCertificate?, basisUrl: String): Boolean {
        val x509 = alsX509(certificaat) ?: return false
        val vingerafdruk = vingerafdruk(x509)
        if (vingerafdruk in goedgekeurd) return true
        return try {
            val verbinding = open(context, "$basisUrl/status") as? HttpsURLConnection ?: return false
            verbinding.connectTimeout = 10_000
            verbinding.readTimeout = 10_000
            try {
                verbinding.connect()
                val gezien = verbinding.serverCertificates.firstOrNull() as? X509Certificate ?: return false
                val gelijk = gezien.encoded.contentEquals(x509.encoded)
                if (gelijk) goedgekeurd.add(vingerafdruk)
                gelijk
            } finally {
                verbinding.disconnect()
            }
        } catch (e: Exception) {
            false
        }
    }

    private fun alsX509(certificaat: SslCertificate?): X509Certificate? {
        if (certificaat == null) return null
        if (Build.VERSION.SDK_INT >= 29) return certificaat.x509Certificate
        val bytes = SslCertificate.saveState(certificaat)?.getByteArray("x509-certificate") ?: return null
        return try {
            CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(bytes)) as X509Certificate
        } catch (e: Exception) {
            null
        }
    }

    private fun vingerafdruk(certificaat: X509Certificate): String =
        MessageDigest.getInstance("SHA-256").digest(certificaat.encoded).joinToString("") { "%02x".format(it) }
}
