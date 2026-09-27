package nl.kantineblauwgeel.tv

data class Screen(val sleutel: String, val titel: String, val url: String)

object Screens {
    const val BASE_URL = "https://www.kantineblauwgeel.nl"

    val PRIJZEN = Screen("prijzen", "Prijzenscherm", "$BASE_URL/kiosk/prijzen")
    val DIAS = Screen("dias", "Dia's & sponsoren", "$BASE_URL/kiosk/scherm")
    val GEDEELD = Screen("gedeeld", "Kantine-TV (gedeeld)", "$BASE_URL/kiosk/tv")

    val ALLE = listOf(PRIJZEN, DIAS, GEDEELD)

    fun opSleutel(sleutel: String?): Screen =
        ALLE.firstOrNull { it.sleutel == sleutel } ?: GEDEELD
}
