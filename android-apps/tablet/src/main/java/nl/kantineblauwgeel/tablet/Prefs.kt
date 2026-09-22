package nl.kantineblauwgeel.tablet

import android.content.Context

object Prefs {
    private const val NAAM = "kantine_tablet_prefs"
    private const val KEY_BASE_URL = "base_url"

    const val DEFAULT_BASE_URL = "https://www.kantineblauwgeel.nl"

    private fun prefs(context: Context) =
        context.getSharedPreferences(NAAM, Context.MODE_PRIVATE)

    fun getBaseUrl(context: Context): String =
        prefs(context).getString(KEY_BASE_URL, DEFAULT_BASE_URL) ?: DEFAULT_BASE_URL

    fun setBaseUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_BASE_URL, url).apply()
    }
}
