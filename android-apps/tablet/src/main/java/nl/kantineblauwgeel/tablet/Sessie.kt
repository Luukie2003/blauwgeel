package nl.kantineblauwgeel.tablet

/** Sessiestatus voor de duur van het app-proces -- er is bewust geen
 * WebView meer (alle schermen zijn native, zie BeheerMenuActivity en de
 * Producten/Acties/Bardiensten-schermen), dus geen CookieManager om de
 * sessie in te bewaren. In plaats daarvan onthoudt de app zelf de
 * sessie-cookie (uit MainActivity.neemSessieOver) en het csrf_token (uit
 * Api.haalCsrfTokenOp), en stuurt die handmatig mee met elke aanroep (zie
 * Api.kt). Bewust niet persistent: bij elke herstart moet opnieuw de
 * 6-cijferige code worden ingevoerd, net als voorheen. */
object Sessie {
    var cookie: String? = null
    var csrfToken: String? = null
    /** Naam van het ingelogde account, puur om te tonen in BeheerMenuActivity
     * -- geen functionele rol, zie tablet_code_inloggen in routes/auth.py. */
    var naam: String? = null

    fun ingelogd(): Boolean = cookie != null
}
