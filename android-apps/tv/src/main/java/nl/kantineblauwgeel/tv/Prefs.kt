package nl.kantineblauwgeel.tv

import android.content.Context

object Prefs {
    private const val NAAM = "kantine_tv_prefs"
    private const val KEY_ZOOM_PREFIX = "zoom_percent_"
    // Oude, gedeelde zoom-instelling van voor het scherm-per-scherm maken
    // ervan -- alleen nog gelezen als terugvaloptie (zie getZoom hieronder)
    // zodat een al ingestelde zoom niet stilzwijgend terugspringt naar
    // DEFAULT_ZOOM voor iedereen die al een aangepaste waarde had. Wordt
    // zelf niet meer geschreven.
    private const val KEY_ZOOM_OUD_GEDEELD = "zoom_percent"
    private const val KEY_LAST_SCHERM = "last_scherm_sleutel"
    private const val KEY_AUTO_START = "auto_start_last"

    const val DEFAULT_ZOOM = 100

    private fun prefs(context: Context) =
        context.getSharedPreferences(NAAM, Context.MODE_PRIVATE)

    fun getZoom(context: Context, schermSleutel: String): Int {
        val instellingen = prefs(context)
        val eigenSleutel = KEY_ZOOM_PREFIX + schermSleutel
        if (instellingen.contains(eigenSleutel)) {
            return instellingen.getInt(eigenSleutel, DEFAULT_ZOOM)
        }
        return instellingen.getInt(KEY_ZOOM_OUD_GEDEELD, DEFAULT_ZOOM)
    }

    fun setZoom(context: Context, schermSleutel: String, waarde: Int) {
        prefs(context).edit().putInt(KEY_ZOOM_PREFIX + schermSleutel, waarde).apply()
    }

    fun getLastSchermSleutel(context: Context): String? =
        prefs(context).getString(KEY_LAST_SCHERM, null)

    fun setLastSchermSleutel(context: Context, schermSleutel: String) {
        prefs(context).edit().putString(KEY_LAST_SCHERM, schermSleutel).apply()
    }

    fun isAutoStartEnabled(context: Context): Boolean =
        prefs(context).getBoolean(KEY_AUTO_START, true)

    fun setAutoStartEnabled(context: Context, waarde: Boolean) {
        prefs(context).edit().putBoolean(KEY_AUTO_START, waarde).apply()
    }
}
