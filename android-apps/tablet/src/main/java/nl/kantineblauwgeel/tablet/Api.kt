package nl.kantineblauwgeel.tablet

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID

/** Kleine HTTP-helper voor de native beheerschermen -- draagt de sessie-cookie + csrf_token uit Sessie mee.
 *
 * - get / postForm: de website-routes van Kantine-tv (de map routes/kiosk), die precies dezelfde form-encoded POSTs +
 *   csrf_token verwachten als een browser. "X-Requested-With: fetch" laat die routes JSON teruggeven i.p.v. een
 *   redirect (zie is_ajax_verzoek() in helpers.py).
 * - postJson: de JSON-API van de handterminal-app (routes/app_api.py en verder), met het csrf_token in X-CSRF-Token en een
 *   verzoek_id, zodat een herhaald verzoek na een haperende verbinding niet dubbel wordt uitgevoerd.
 *
 * Synchroon -- aanroepers starten zelf een Thread{} (zie BasisActivity.opAchtergrond). Een verlopen sessie (401, of
 * een doorverwijzing naar het inlogscherm) geeft NietIngelogd; een noodstop (503) Noodstop. */
object Api {

    open class ApiFout(bericht: String) : Exception(bericht)
    class NietIngelogd : ApiFout("Je bent uitgelogd. Voer je code opnieuw in.")
    class Noodstop : ApiFout("De site is tijdelijk afgesloten.")

    fun get(context: Context, pad: String): JSONObject = lezen(openen(context, pad, "GET"))

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

    fun postJson(context: Context, pad: String, body: JSONObject = JSONObject()): JSONObject {
        val verbinding = openen(context, pad, "POST")
        verbinding.doOutput = true
        if (!body.has("verzoek_id")) body.put("verzoek_id", UUID.randomUUID().toString())
        verbinding.setRequestProperty("Content-Type", "application/json")
        verbinding.setRequestProperty("X-CSRF-Token", Sessie.csrfToken ?: "")
        verbinding.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        return lezen(verbinding)
    }

    private fun openen(context: Context, pad: String, methode: String): HttpURLConnection {
        val verbinding = URL(Prefs.getBaseUrl(context) + pad).openConnection() as HttpURLConnection
        verbinding.requestMethod = methode
        verbinding.connectTimeout = 8000
        verbinding.readTimeout = 15000
        verbinding.instanceFollowRedirects = false
        verbinding.setRequestProperty("X-Requested-With", "fetch")
        verbinding.setRequestProperty("Accept", "application/json")
        Sessie.cookie?.let { verbinding.setRequestProperty("Cookie", it) }
        return verbinding
    }

    private fun lezen(verbinding: HttpURLConnection): JSONObject {
        val status = try {
            verbinding.responseCode
        } catch (e: Exception) {
            throw ApiFout("Geen verbinding met de website")
        }
        if (status in 300..399 || status == 401) throw NietIngelogd()
        if (status == 503) throw Noodstop()
        val tekst = try {
            (if (status in 200..299) verbinding.inputStream else verbinding.errorStream).bufferedReader().use { it.readText() }
        } catch (e: Exception) {
            throw ApiFout("Geen verbinding met de website")
        }
        val json = try {
            JSONObject(tekst)
        } catch (e: Exception) {
            throw ApiFout("Geen verbinding met de website")
        }
        if (status !in 200..299) {
            throw ApiFout(json.optString("melding").ifEmpty { json.optString("fout") }.ifEmpty { "Dat lukte niet (fout $status)." })
        }
        return json
    }
}
