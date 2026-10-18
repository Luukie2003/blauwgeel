package nl.kantineblauwgeel.handterminal

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/** De twee dingen die de app zelf (buiten de WebView om) aan de site vraagt: inloggen met de persoonlijke code
 * en de verbinding testen. Synchroon: altijd vanuit een eigen thread aanroepen. */
object Server {

    sealed class Inlog {
        /** [cookies]: de Set-Cookie-regels van de site, voor de CookieManager van de WebView. */
        class Gelukt(val naam: String, val cookies: List<String>) : Inlog()
        class FouteCode(val pogingenOver: Int?) : Inlog()
        class TeVeelPogingen(val minuten: Int?) : Inlog()
        object Noodstop : Inlog()
        class Mislukt(val soort: Fout) : Inlog()
    }

    enum class Fout { GEEN_VERBINDING, TRAAG, BEVEILIGING, SERVER }

    class Meting(val milliseconden: Long, val versie: String?)

    /** POST /api/tablet-code/inloggen: dezelfde code-inlog als de tablet (zie tablet_code_inloggen op de site).
     * Een haperende verbinding proberen we één keer opnieuw; een foute code natuurlijk niet. */
    fun inloggen(context: Context, basisUrl: String, code: String, userAgent: String): Inlog {
        var laatste: Fout = Fout.GEEN_VERBINDING
        repeat(2) { poging ->
            if (poging > 0) Thread.sleep(1200)
            try {
                return inloggenEenKeer(context, basisUrl, code, userAgent)
            } catch (e: IOException) {
                laatste = soortFout(e)
                if (laatste == Fout.BEVEILIGING) return Inlog.Mislukt(laatste)
            }
        }
        return Inlog.Mislukt(laatste)
    }

    private fun inloggenEenKeer(context: Context, basisUrl: String, code: String, userAgent: String): Inlog {
        val verbinding = Beveiliging.open(context, "$basisUrl/api/tablet-code/inloggen")
        try {
            verbinding.requestMethod = "POST"
            verbinding.doOutput = true
            verbinding.connectTimeout = 10_000
            verbinding.readTimeout = 15_000
            verbinding.instanceFollowRedirects = false
            verbinding.setRequestProperty("Content-Type", "application/json")
            verbinding.setRequestProperty("Accept", "application/json")
            verbinding.setRequestProperty("User-Agent", userAgent)
            verbinding.outputStream.use { it.write(JSONObject().put("code", code).toString().toByteArray(Charsets.UTF_8)) }

            val status = verbinding.responseCode
            val antwoord = leesJson(verbinding, status)
            return when {
                status == 429 -> Inlog.TeVeelPogingen(antwoord?.optInt("wacht_minuten", 0)?.takeIf { it > 0 })
                status == 503 && antwoord?.optString("fout") == "noodstop" -> Inlog.Noodstop
                antwoord == null || status !in 200..299 -> Inlog.Mislukt(Fout.SERVER)
                antwoord.optBoolean("geldig", false) -> {
                    val cookies = verbinding.headerFields.entries
                        .filter { it.key.equals("Set-Cookie", ignoreCase = true) }
                        .flatMap { it.value }
                    if (cookies.isEmpty()) Inlog.Mislukt(Fout.SERVER)
                    else Inlog.Gelukt(antwoord.optString("naam").ifEmpty { "?" }, cookies)
                }
                else -> Inlog.FouteCode(if (antwoord.has("pogingen_over")) antwoord.optInt("pogingen_over") else null)
            }
        } finally {
            verbinding.disconnect()
        }
    }

    /** GET /status (staat altijd open, ook tijdens een noodstop): hoe snel antwoordt de site, en welke versie. */
    fun meet(context: Context, basisUrl: String): Meting {
        val begin = System.nanoTime()
        val verbinding = Beveiliging.open(context, "$basisUrl/status")
        try {
            verbinding.connectTimeout = 8_000
            verbinding.readTimeout = 8_000
            verbinding.setRequestProperty("Cache-Control", "no-cache")
            val status = verbinding.responseCode
            val antwoord = leesJson(verbinding, status)
            if (status !in 200..299) throw IOException("status $status")
            return Meting((System.nanoTime() - begin) / 1_000_000, antwoord?.optString("versie")?.ifEmpty { null })
        } finally {
            verbinding.disconnect()
        }
    }

    fun soortFout(e: Exception): Fout = when (e) {
        is SSLException -> Fout.BEVEILIGING
        is SocketTimeoutException -> Fout.TRAAG
        is UnknownHostException -> Fout.GEEN_VERBINDING
        else -> Fout.GEEN_VERBINDING
    }

    private fun leesJson(verbinding: HttpURLConnection, status: Int): JSONObject? {
        val stroom = (if (status in 200..299) verbinding.inputStream else verbinding.errorStream) ?: return null
        val tekst = stroom.bufferedReader().use { it.readText() }
        return try {
            JSONObject(tekst)
        } catch (e: Exception) {
            null
        }
    }
}
