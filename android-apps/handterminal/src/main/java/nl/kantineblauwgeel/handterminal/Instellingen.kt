package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.net.Uri

/** Wat de app onthoudt op het toestel: de instellingen, en wie er is ingelogd (de sessie-cookie van de site en het
 * csrf_token, zie Sessie.kt), met wanneer die voor het laatst iets deed, voor het automatisch uitloggen. */
class Instellingen(context: Context) {

    private val prefs = context.applicationContext.getSharedPreferences("handterminal", Context.MODE_PRIVATE)

    var basisUrl: String
        get() = prefs.getString("basis_url", null) ?: STANDAARD_URL
        set(waarde) = prefs.edit().putString("basis_url", waarde.trimEnd('/')).apply()

    val siteHost: String
        get() = Uri.parse(basisUrl).host ?: ""

    /** Na hoeveel minuten zonder aanraken of scannen de app uitlogt; 0 = nooit. */
    var uitlogMinuten: Int
        get() = prefs.getInt("uitlog_minuten", 15)
        set(waarde) = prefs.edit().putInt("uitlog_minuten", waarde).apply()

    /** Tekstgrootte van de pagina's die nog als website openen. */
    var tekstGrootte: Int
        get() = prefs.getInt("tekst_grootte", 100)
        set(waarde) = prefs.edit().putInt("tekst_grootte", waarde).apply()

    var trillen: Boolean
        get() = prefs.getBoolean("trillen", true)
        set(waarde) = prefs.edit().putBoolean("trillen", waarde).apply()

    // ---- De sessie (zie Sessie.kt) ----

    var naam: String?
        get() = prefs.getString("naam", null)
        set(waarde) = prefs.edit().putString("naam", waarde).apply()

    var cookies: String?
        get() = prefs.getString("cookies", null)
        set(waarde) = prefs.edit().putString("cookies", waarde).apply()

    var csrfToken: String?
        get() = prefs.getString("csrf_token", null)
        set(waarde) = prefs.edit().putString("csrf_token", waarde).apply()

    /** Het website-adres waarmee is ingelogd; verandert dat (alleen in een testversie), dan opnieuw inloggen. */
    var ingelogdOp: String?
        get() = prefs.getString("ingelogd_op", null)
        set(waarde) = prefs.edit().putString("ingelogd_op", waarde).apply()

    var laatsteActiviteit: Long
        get() = prefs.getLong("laatste_activiteit", 0L)
        set(waarde) = prefs.edit().putLong("laatste_activiteit", waarde).apply()

    /** Het laatste antwoord van het startscherm, om meteen iets te kunnen tonen terwijl het nieuwe onderweg is. */
    var startCache: String?
        get() = prefs.getString("start_cache", null)
        set(waarde) = prefs.edit().putString("start_cache", waarde).apply()

    /** Mag je bij deze sectie (voorraad, kassa, keuken, club_van_20, kantine_tv), volgens het laatste startscherm?
     * Alleen om te bepalen wat de app laat zien: de site controleert het zelf ook. Zonder startscherm: ja. */
    fun toegang(sectie: String): Boolean = try {
        startCache?.let { org.json.JSONObject(it).optJSONObject("toegang")?.optBoolean(sectie, true) } ?: true
    } catch (e: org.json.JSONException) {
        true
    }

    val beheerder: Boolean
        get() = try {
            startCache?.let { org.json.JSONObject(it).optBoolean("beheerder") } ?: false
        } catch (e: org.json.JSONException) {
            false
        }

    fun isVerlopen(nu: Long = System.currentTimeMillis()): Boolean {
        val minuten = uitlogMinuten
        return minuten > 0 && nu - laatsteActiviteit > minuten * 60_000L
    }

    companion object {
        const val STANDAARD_URL = "https://www.kantineblauwgeel.nl"
        val UITLOG_KEUZES = intArrayOf(5, 10, 15, 30, 60, 0)
        val TEKST_KEUZES = intArrayOf(90, 100, 115, 130)
    }
}
