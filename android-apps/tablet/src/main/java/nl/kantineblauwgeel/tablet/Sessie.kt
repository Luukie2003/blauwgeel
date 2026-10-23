package nl.kantineblauwgeel.tablet

/** Sessiestatus voor de duur van het app-proces -- er is bewust geen WebView (alle schermen zijn native, zie
 * BeheerMenuActivity), dus geen CookieManager om de sessie in te bewaren. In plaats daarvan onthoudt de app zelf de
 * sessie-cookie en het csrf_token uit het inloggen (MainActivity.neemSessieOver), en stuurt die mee met elke aanroep
 * (zie Api.kt). Bewust niet persistent: bij elke herstart moet opnieuw de 6-cijferige code worden ingevoerd. Na
 * BasisActivity.UITLOG_MINUTEN zonder aanraken logt de app vanzelf uit. */
object Sessie {
    var cookie: String? = null
    var csrfToken: String? = null
    /** Naam van het ingelogde account, puur om te tonen in BeheerMenuActivity. */
    var naam: String? = null
    var laatsteAanraking: Long = System.currentTimeMillis()

    fun ingelogd(): Boolean = cookie != null

    fun uitloggen() {
        cookie = null
        csrfToken = null
        naam = null
    }
}
