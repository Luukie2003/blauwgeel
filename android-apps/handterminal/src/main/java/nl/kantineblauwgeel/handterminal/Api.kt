package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.UUID
import javax.net.ssl.SSLException

/** Praat met de site: de JSON-API voor de app (routes/app_api.py op de site), het factuur-inboeken (routes/facturen.py)
 * en het inloggen met de code. Alles via Beveiliging.open (ook op Android 6 een veilige verbinding).
 *
 * Opnieuw proberen bij een haperende verbinding gaat vanzelf, maar alleen waar dat veilig is: bij ophalen altijd, en bij
 * een schrijfactie alleen met een verzoek_id (dan herkent de site een herhaling en doet hij het niet dubbel). */
object Api {

    enum class Soort { GEEN_VERBINDING, TRAAG, BEVEILIGING, NIET_INGELOGD, GEEN_TOEGANG, NOODSTOP, NIET_GEVONDEN, ONGELDIG, SERVER }

    class Fout(val soort: Soort, melding: String) : Exception(melding) {
        /** Netwerk of server: het kan zo weer werken (in tegenstelling tot bijvoorbeeld een foute invoer). */
        val tijdelijk get() = soort in setOf(Soort.GEEN_VERBINDING, Soort.TRAAG, Soort.SERVER)
    }

    /** status 304 = niets veranderd (bij een ETag). */
    class Antwoord(val status: Int, val json: JSONObject?, val etag: String?)

    val userAgent: String
        get() = "KantineHandterminal/${BuildConfig.VERSION_NAME} (Linux; Android ${Build.VERSION.RELEASE}; ${Build.MODEL}) Mobile"

    fun nieuwVerzoekId(): String = UUID.randomUUID().toString()

    suspend fun get(context: Context, pad: String, etag: String? = null): Antwoord = withContext(Dispatchers.IO) {
        herhaal(pogingen = 3) { verzoek(context, "GET", pad, null, etag) }
    }

    suspend fun getJson(context: Context, pad: String): JSONObject =
        get(context, pad).json ?: throw Fout(Soort.SERVER, "Leeg antwoord van de website.")

    /** Een schrijfactie. Met [verzoekId] mag hij bij een haperende verbinding vanzelf opnieuw (de site doet hem dan
     * maar één keer); zonder alleen als [herhaalbaar] (bijvoorbeeld de stand van het tellen bewaren). */
    suspend fun post(
        context: Context,
        pad: String,
        body: JSONObject = JSONObject(),
        verzoekId: String? = null,
        herhaalbaar: Boolean = false,
    ): JSONObject = withContext(Dispatchers.IO) {
        if (verzoekId != null) body.put("verzoek_id", verzoekId)
        val pogingen = if (verzoekId != null || herhaalbaar) 4 else 1
        herhaal(pogingen) { verzoek(context, "POST", pad, body, null) }.json ?: JSONObject()
    }

    private suspend fun herhaal(pogingen: Int, actie: () -> Antwoord): Antwoord {
        var laatste: Fout? = null
        repeat(pogingen) { i ->
            if (i > 0) delay(700L * i)
            try {
                return actie()
            } catch (f: Fout) {
                if (!f.tijdelijk || f.soort == Soort.SERVER && i >= 1) throw f
                laatste = f
            }
        }
        throw laatste ?: Fout(Soort.GEEN_VERBINDING, "Geen verbinding met de website.")
    }

    private fun verzoek(context: Context, methode: String, pad: String, body: JSONObject?, etag: String?): Antwoord {
        Sessie.laad(context)
        val inst = Instellingen(context)
        val verbinding = try {
            Beveiliging.open(context, inst.basisUrl + pad)
        } catch (e: IOException) {
            throw netwerkFout(e)
        }
        try {
            verbinding.requestMethod = methode
            verbinding.connectTimeout = 10_000
            verbinding.readTimeout = 20_000
            verbinding.instanceFollowRedirects = false
            verbinding.setRequestProperty("Accept", "application/json")
            verbinding.setRequestProperty("User-Agent", userAgent)
            Sessie.cookieKop().takeIf { it.isNotEmpty() }?.let { verbinding.setRequestProperty("Cookie", it) }
            if (etag != null) verbinding.setRequestProperty("If-None-Match", etag)
            if (body != null) {
                verbinding.doOutput = true
                verbinding.setRequestProperty("Content-Type", "application/json")
                Sessie.csrfToken?.let { verbinding.setRequestProperty("X-CSRF-Token", it) }
                verbinding.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = verbinding.responseCode
            Sessie.neemCookiesOver(context, setCookies(verbinding))
            if (status == 304) return Antwoord(304, null, etag)
            val tekst = ((if (status in 200..299) verbinding.inputStream else verbinding.errorStream)
                ?.bufferedReader()?.use { it.readText() }) ?: ""
            val json = try {
                if (tekst.isBlank()) null else JSONObject(tekst)
            } catch (e: Exception) {
                null
            }
            if (status in 200..299) return Antwoord(status, json, verbinding.getHeaderField("ETag"))
            val melding = json?.optString("melding")?.takeIf { it.isNotEmpty() }
            throw when {
                status == 401 || status in 300..399 -> Fout(Soort.NIET_INGELOGD, melding ?: "Log opnieuw in.")
                status == 403 -> Fout(Soort.GEEN_TOEGANG, melding ?: "Dit mag jouw account niet.")
                status == 503 && json?.optString("fout") == "noodstop" -> Fout(Soort.NOODSTOP, context.getString(R.string.code_noodstop))
                status == 404 -> Fout(Soort.NIET_GEVONDEN, melding ?: "Niet gevonden.")
                status in 400..499 -> Fout(Soort.ONGELDIG, melding ?: "Dat ging niet goed (fout $status).")
                else -> Fout(Soort.SERVER, context.getString(R.string.fout_server_kort))
            }
        } catch (e: IOException) {
            throw netwerkFout(e)
        } finally {
            verbinding.disconnect()
        }
    }

    private fun setCookies(verbinding: HttpURLConnection): List<String> =
        verbinding.headerFields.entries.filter { it.key.equals("Set-Cookie", ignoreCase = true) }.flatMap { it.value }

    private fun netwerkFout(e: IOException) = when (e) {
        is SSLException -> Fout(Soort.BEVEILIGING, "Beveiligde verbinding mislukt. Kloppen de datum en tijd van de handterminal?")
        is SocketTimeoutException -> Fout(Soort.TRAAG, "De website reageert te traag. Probeer het nog eens.")
        is UnknownHostException -> Fout(Soort.GEEN_VERBINDING, "Geen verbinding met de website. Controleer de wifi.")
        else -> Fout(Soort.GEEN_VERBINDING, "Geen verbinding met de website. Controleer de wifi.")
    }

    // ---------------------------------------------------------------- inloggen met de code

    sealed class Inlog {
        class Gelukt(val naam: String, val csrfToken: String, val cookies: List<String>) : Inlog()
        class FouteCode(val pogingenOver: Int?) : Inlog()
        class TeVeelPogingen(val minuten: Int?) : Inlog()
        object Noodstop : Inlog()
        class Mislukt(val fout: Fout) : Inlog()
    }

    /** POST /api/tablet-code/inloggen (zie tablet_code_inloggen op de site). Een haperende verbinding proberen we
     * nog een keer; een foute code natuurlijk niet. */
    suspend fun inloggen(context: Context, code: String): Inlog = withContext(Dispatchers.IO) {
        var laatste = Fout(Soort.GEEN_VERBINDING, "Geen verbinding met de website.")
        repeat(2) { poging ->
            if (poging > 0) delay(1200)
            try {
                return@withContext inloggenEenKeer(context, code)
            } catch (e: IOException) {
                laatste = netwerkFout(e)
                if (laatste.soort == Soort.BEVEILIGING) return@withContext Inlog.Mislukt(laatste)
            }
        }
        Inlog.Mislukt(laatste)
    }

    private fun inloggenEenKeer(context: Context, code: String): Inlog {
        val verbinding = Beveiliging.open(context, Instellingen(context).basisUrl + "/api/tablet-code/inloggen")
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
            val tekst = ((if (status in 200..299) verbinding.inputStream else verbinding.errorStream)
                ?.bufferedReader()?.use { it.readText() }) ?: ""
            val antwoord = try {
                JSONObject(tekst)
            } catch (e: Exception) {
                null
            }
            return when {
                status == 429 -> Inlog.TeVeelPogingen(antwoord?.optInt("wacht_minuten", 0)?.takeIf { it > 0 })
                status == 503 && antwoord?.optString("fout") == "noodstop" -> Inlog.Noodstop
                antwoord == null || status !in 200..299 -> Inlog.Mislukt(Fout(Soort.SERVER, context.getString(R.string.code_server)))
                antwoord.optBoolean("geldig", false) -> {
                    val cookies = setCookies(verbinding)
                    val csrf = antwoord.optString("csrf_token")
                    if (cookies.isEmpty() || csrf.isEmpty()) Inlog.Mislukt(Fout(Soort.SERVER, context.getString(R.string.code_server)))
                    else Inlog.Gelukt(antwoord.optString("naam").ifEmpty { "?" }, csrf, cookies)
                }
                else -> Inlog.FouteCode(if (antwoord.has("pogingen_over")) antwoord.optInt("pogingen_over") else null)
            }
        } finally {
            verbinding.disconnect()
        }
    }

    /** GET /status (staat altijd open): hoe snel antwoordt de site, en welke versie draait er. */
    suspend fun meet(context: Context): Pair<Long, String?> = withContext(Dispatchers.IO) {
        val begin = System.nanoTime()
        val verbinding = Beveiliging.open(context, Instellingen(context).basisUrl + "/status")
        try {
            verbinding.connectTimeout = 8_000
            verbinding.readTimeout = 8_000
            verbinding.setRequestProperty("Cache-Control", "no-cache")
            if (verbinding.responseCode !in 200..299) throw IOException("status ${verbinding.responseCode}")
            val json = JSONObject(verbinding.inputStream.bufferedReader().use { it.readText() })
            (System.nanoTime() - begin) / 1_000_000 to json.optString("versie").ifEmpty { null }
        } finally {
            verbinding.disconnect()
        }
    }
}

/** Kleine hulpjes om door JSON te lopen. */
fun JSONArray.objecten(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

fun JSONObject.tekstOfNull(sleutel: String): String? = if (isNull(sleutel)) null else optString(sleutel).ifEmpty { null }
