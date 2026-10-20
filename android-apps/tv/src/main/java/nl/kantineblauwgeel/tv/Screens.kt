package nl.kantineblauwgeel.tv

data class Screen(val sleutel: String, val titel: String, val url: String)

object Screens {
    // https://www.kantineblauwgeel.nl; in de testversie eventueel een testserver (zie build.gradle.kts).
    val BASE_URL: String = BuildConfig.BASIS_URL

    // Een gekoppelde tv (zie kiosk_tvs.py op de site): de tv laat een code zien, die je op de site koppelt; daarna
    // kies je op de site wat hij toont en hoe groot. PlayerActivity onthoudt het eigen adres van de tv (/kiosk/t/...).
    val GEKOPPELD = Screen("gekoppeld", "Gekoppeld scherm\n(beheer op de site)", "$BASE_URL/kiosk/koppelen")
    val PRIJZEN = Screen("prijzen", "Prijzenscherm", "$BASE_URL/kiosk/prijzen")
    val DIAS = Screen("dias", "Dia's & sponsoren", "$BASE_URL/kiosk/scherm")
    val GEDEELD = Screen("gedeeld", "Kantine-TV (gedeeld)", "$BASE_URL/kiosk/tv")

    val ALLE = listOf(GEKOPPELD, PRIJZEN, DIAS, GEDEELD)

    fun opSleutel(sleutel: String?): Screen =
        ALLE.firstOrNull { it.sleutel == sleutel } ?: GEKOPPELD
}
