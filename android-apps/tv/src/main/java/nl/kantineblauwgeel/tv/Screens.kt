package nl.kantineblauwgeel.tv

/** Waar de tv-app naartoe gaat. De app toont alleen nog een gekoppeld scherm (zie kiosk_tvs.py op de site): de tv laat
 * een koppelcode en een QR-code zien, je koppelt hem op de site of met de handterminal, en daar kies je ook wat hij
 * toont en hoe groot. PlayerActivity onthoudt het eigen adres van de tv (/kiosk/t/...). */
object Screens {
    // https://www.kantineblauwgeel.nl; in de testversie eventueel een testserver (zie build.gradle.kts).
    val BASE_URL: String = BuildConfig.BASIS_URL

    /** Een nieuwe tv begint hier: de site geeft hem een eigen token en adres. */
    val KOPPELEN_URL = "$BASE_URL/kiosk/koppelen"

    /** De sleutel waaronder de zoom van het gekoppelde scherm bewaard wordt (zie Prefs). */
    const val GEKOPPELD = "gekoppeld"

    /** Het spel van de club (Shout-out!), achter de geheime toetsen (zie PlayerActivity en SpelActivity). */
    const val SPEL_URL = "https://coach.epremium.nl/blauwgeel/"

    /** De clubcode die het spel de eerste keer vraagt; de app vult hem zelf in. */
    const val SPEL_CLUBCODE = "BG"
}
