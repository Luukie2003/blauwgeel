package nl.kantineblauwgeel.tablet

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Kleine HTTP-helper voor de native beheerschermen (Producten/Acties/
 * Bardiensten) -- draagt de sessie-cookie + csrf_token uit Sessie mee, want
 * de bestaande website-routes (routes/producten.py, routes/kiosk.py)
 * verwachten precies dezelfde form-encoded POSTs + csrf_token als een
 * browser. "X-Requested-With: fetch" laat diezelfde routes JSON teruggeven
 * i.p.v. een redirect (zie is_ajax_verzoek() in helpers.py). Synchroon --
 * aanroepers starten zelf een Thread{}, zie MainActivity voor dat patroon. */
object Api {

    class ApiFout(bericht: String) : Exception(bericht)

    fun get(context: Context, pad: String): JSONObject {
        val verbinding = openen(context, pad, "GET")
        return lezen(verbinding)
    }

    fun postForm(context: Context, pad: String, velden: Map<String, String>): JSONObject {
        val verbinding = openen(context, pad, "POST")
        verbinding.doOutput = true
        val metCsrf = velden + ("csrf_token" to (Sessie.csrfToken ?: ""))
        val body = metCsrf.entries.joinToString("&") { (k, v) ->
            URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
        }
        verbinding.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        verbinding.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        return lezen(verbinding)
    }

    private fun openen(context: Context, pad: String, methode: String): HttpURLConnection {
        val verbinding = URL(Prefs.getBaseUrl(context) + pad).openConnection() as HttpURLConnection
        verbinding.requestMethod = methode
        verbinding.connectTimeout = 8000
        verbinding.readTimeout = 8000
        verbinding.setRequestProperty("X-Requested-With", "fetch")
        Sessie.cookie?.let { verbinding.setRequestProperty("Cookie", it) }
        return verbinding
    }

    private fun lezen(verbinding: HttpURLConnection): JSONObject {
        try {
            val status = verbinding.responseCode
            val stream = if (status in 200..299) verbinding.inputStream else verbinding.errorStream
            val tekst = stream.bufferedReader().use { it.readText() }
            return JSONObject(tekst)
        } catch (e: Exception) {
            throw ApiFout("Geen verbinding met de website")
        }
    }
}
