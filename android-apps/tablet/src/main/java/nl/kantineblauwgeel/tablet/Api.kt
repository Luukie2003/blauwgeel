package nl.kantineblauwgeel.tablet

import android.content.Context
import nl.kantineblauwgeel.handterminal.Instellingen
import nl.kantineblauwgeel.handterminal.Sessie
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID
import nl.kantineblauwgeel.handterminal.Api as GedeeldeApi

/** Kleine HTTP-helper voor de eigen tv-schermen van de tablet (acties, bardiensten, uitgelicht, wedstrijddag, het
 * prijzenscherm). Sinds 3.0 met de inlog van de gedeelde handterminal-code: dezelfde sessie-cookie, hetzelfde csrf_token
 * en hetzelfde adres van de site (Sessie en Instellingen daar), zodat je maar één keer je code invoert.
 *
 * - get / postForm: de website-routes van Kantine-tv (de map routes/kiosk), die precies dezelfde form-encoded POSTs +
 *   csrf_token verwachten als een browser. "X-Requested-With: fetch" laat die routes JSON teruggeven i.p.v. een
 *   redirect (zie is_ajax_verzoek() in helpers.py).
 * - postJson: de JSON-API van de app (routes/app_api.py en verder), met het csrf_token in X-CSRF-Token en een
 *   verzoek_id, zodat een herhaald verzoek na een haperende verbinding niet dubbel wordt uitgevoerd.
 *
 * Synchroon: de schermen starten zelf een Thread{}. Een verlopen sessie (401, of een doorverwijzing naar het
 * inlogscherm) geeft NietIngelogd; een noodstop (503) Noodstop. */
object Api {

    open class ApiFout(bericht: String) : Exception(bericht)
    class NietIngelogd : ApiFout("Je bent uitgelogd. Voer je code opnieuw in.")
    class Noodstop : ApiFout("De site is tijdelijk afgesloten.")

    fun get(context: Context, pad: String): JSONObject = lezen(context, openen(context, pad, "GET"))

    fun postForm(context: Context, pad: String, velden: Map<String, String>): JSONObject {
        val verbinding = openen(context, pad, "POST")
        verbinding.doOutput = true
        val metCsrf = velden + ("csrf_token" to (Sessie.csrfToken ?: ""))
        val body = metCsrf.entries.joinToString("&") { (k, v) ->
            URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
        }
        verbinding.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        verbinding.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        return lezen(context, verbinding)
    }

    fun postJson(context: Context, pad: String, body: JSONObject = JSONObject()): JSONObject {
        val verbinding = openen(context, pad, "POST")
        verbinding.doOutput = true
        if (!body.has("verzoek_id")) body.put("verzoek_id", UUID.randomUUID().toString())
        verbinding.setRequestProperty("Content-Type", "application/json")
        verbinding.setRequestProperty("X-CSRF-Token", Sessie.csrfToken ?: "")
        verbinding.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        return lezen(context, verbinding)
    }

    private fun openen(context: Context, pad: String, methode: String): HttpURLConnection {
        Sessie.laad(context)
        val verbinding = URL(Instellingen(context).basisUrl.trimEnd('/') + pad).openConnection() as HttpURLConnection
        verbinding.requestMethod = methode
        verbinding.connectTimeout = 8000
        verbinding.readTimeout = 15000
        verbinding.instanceFollowRedirects = false
        verbinding.setRequestProperty("User-Agent", GedeeldeApi.userAgent)
        verbinding.setRequestProperty("X-Requested-With", "fetch")
        verbinding.setRequestProperty("Accept", "application/json")
        Sessie.cookieKop().takeIf { it.isNotEmpty() }?.let { verbinding.setRequestProperty("Cookie", it) }
        return verbinding
    }

    private fun lezen(context: Context, verbinding: HttpURLConnection): JSONObject {
        val status = try {
            verbinding.responseCode
        } catch (e: Exception) {
            throw ApiFout("Geen verbinding met de website")
        }
        // De site vernieuwt de sessie-cookie als er iets in de sessie verandert: die bewaart de gedeelde Sessie.
        val setCookies = verbinding.headerFields.entries.filter { it.key.equals("Set-Cookie", ignoreCase = true) }.flatMap { it.value }
        Sessie.neemCookiesOver(context, setCookies)
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
