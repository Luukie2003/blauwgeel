package nl.kantineblauwgeel.tv

data class Screen(val titel: String, val url: String)

object Screens {
    const val BASE_URL = "https://kantineblauwgeel.nl"

    val PRIJZEN = Screen("Prijzenscherm", "$BASE_URL/kiosk/prijzen")
    val DIAS = Screen("Dia's & sponsoren", "$BASE_URL/kiosk/scherm")
    val GEDEELD = Screen("Kantine-TV (gedeeld)", "$BASE_URL/kiosk/tv")

    val ALLE = listOf(PRIJZEN, DIAS, GEDEELD)
}
