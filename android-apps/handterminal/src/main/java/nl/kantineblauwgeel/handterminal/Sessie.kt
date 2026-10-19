package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.webkit.CookieManager

/** Wie er is ingelogd. De site werkt met een sessie-cookie; de app bewaart die (en het csrf_token, voor elke POST)
 * zelf en stuurt hem mee met elk verzoek (zie Api.kt). Voor de pagina's die nog als website openen, zet WebActivity
 * dezelfde cookie in de WebView. */
object Sessie {

    private val cookies = LinkedHashMap<String, String>()
    @Volatile var csrfToken: String? = null
        private set
    @Volatile var naam: String? = null
        private set

    private var geladen = false

    @Synchronized
    fun laad(context: Context) {
        if (geladen) return
        geladen = true
        val inst = Instellingen(context)
        naam = inst.naam
        csrfToken = inst.csrfToken
        inst.cookies?.split("; ")?.forEach { deel ->
            val i = deel.indexOf('=')
            if (i > 0) cookies[deel.substring(0, i)] = deel.substring(i + 1)
        }
    }

    fun isIngelogd(context: Context): Boolean {
        laad(context)
        val inst = Instellingen(context)
        return naam != null && cookies.containsKey("session") && inst.ingelogdOp == inst.basisUrl && !inst.isVerlopen()
    }

    @Synchronized
    fun zet(context: Context, naam: String, csrfToken: String, setCookies: List<String>) {
        laad(context)
        cookies.clear()
        neemCookiesOver(context, setCookies)
        this.naam = naam
        this.csrfToken = csrfToken
        val inst = Instellingen(context)
        inst.naam = naam
        inst.csrfToken = csrfToken
        inst.ingelogdOp = inst.basisUrl
        inst.laatsteActiviteit = System.currentTimeMillis()
    }

    /** Set-Cookie-regels uit een antwoord: de site vernieuwt de sessie-cookie als er iets in de sessie verandert. */
    @Synchronized
    fun neemCookiesOver(context: Context, setCookies: List<String>) {
        if (setCookies.isEmpty()) return
        for (regel in setCookies) {
            val paar = regel.substringBefore(';')
            val i = paar.indexOf('=')
            if (i <= 0) continue
            val sleutel = paar.substring(0, i).trim()
            val waarde = paar.substring(i + 1).trim()
            val verlopen = regel.contains("Max-Age=0", ignoreCase = true) || regel.contains("expires=Thu, 01 Jan 1970", ignoreCase = true)
            if (waarde.isEmpty() || verlopen) cookies.remove(sleutel) else cookies[sleutel] = waarde
        }
        Instellingen(context).cookies = cookieKop()
    }

    @Synchronized
    fun cookieKop(): String = cookies.entries.joinToString("; ") { "${it.key}=${it.value}" }

    /** De cookies in de WebView zetten, voor een pagina die als website opent. */
    fun naarWebView(context: Context) {
        val inst = Instellingen(context)
        val manager = CookieManager.getInstance()
        val veilig = if (inst.basisUrl.startsWith("https://")) "; Secure" else ""
        synchronized(this) {
            for ((sleutel, waarde) in cookies) manager.setCookie(inst.basisUrl, "$sleutel=$waarde; Path=/$veilig")
        }
        manager.setCookie(inst.basisUrl, "weergave=pda; Max-Age=31536000; Path=/; SameSite=Lax$veilig")
        manager.flush()
    }

    @Synchronized
    fun wis(context: Context) {
        laad(context)
        cookies.clear()
        naam = null
        csrfToken = null
        val inst = Instellingen(context)
        inst.naam = null
        inst.cookies = null
        inst.csrfToken = null
        inst.ingelogdOp = null
        inst.startCache = null
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
    }
}
