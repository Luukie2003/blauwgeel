package nl.kantineblauwgeel.handterminal

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.text.Normalizer

/** Alle producten met hun barcodes, op het toestel zelf. Zoeken en een scan opzoeken gebeurt hierin, zonder op de site
 * te wachten: dat maakt de app snel. De lijst staat in een bestand (meteen beschikbaar na het opstarten) en wordt op de
 * achtergrond ververst bij de site (GET /api/app/producten, met een ETag: niets veranderd is dan bijna gratis). */
object Catalogus {

    /** [doosAantal]/[doosCode]: bij een losse verpakking de doos waar hij in zit (als die bekend is). */
    class Barcode(
        val code: String,
        val niveau: String,
        val aantal: Int,
        val artikel: String,
        val doosAantal: Int? = null,
        val doosCode: String? = null,
    ) {
        val isDoos get() = niveau == "omverpakking"
    }

    class Product(
        val id: Int,
        val naam: String,
        val categorie: String,
        val subcategorie: String,
        val merk: String,
        val eenheid: String,
        val voorraad: Int,
        val minVoorraad: Int,
        val actief: Boolean,
        val besteleenheid: String?,
        val perBesteleenheid: Int,
        val barcodes: List<Barcode>,
        val foto: String? = null,
        val fotoGroot: String? = null,
        /** De leverancier: bij het klaarzetten wordt het een bestelling per leverancier. */
        val leverancier: String? = null,
    ) {
        val laag get() = actief && voorraad < minVoorraad
        internal val zoektekst = normaal("$naam $categorie $subcategorie $merk")

        /** "24 fles", of "48 fles (2 krat)" als het er precies in past. */
        fun voorraadTekst(aantal: Int = voorraad): String {
            val basis = "$aantal $eenheid"
            if (besteleenheid == null || perBesteleenheid <= 1 || aantal <= 0 || aantal % perBesteleenheid != 0) return basis
            return "$basis (${aantal / perBesteleenheid} $besteleenheid)"
        }

        fun metVoorraad(nieuw: Int) = Product(id, naam, categorie, subcategorie, merk, eenheid, nieuw, minVoorraad, actief,
            besteleenheid, perBesteleenheid, barcodes, foto, fotoGroot, leverancier)

        /** Hoeveel er in een volle doos of krat zit, bij een losse verpakking van [barcode]: de doos van dat artikel,
         * of anders de besteleenheid van het product. Null als er niets groters is. */
        fun volleEenheid(barcode: Barcode): Int? =
            barcode.doosAantal?.takeIf { it > barcode.aantal }
                ?: perBesteleenheid.takeIf { besteleenheid != null && it > barcode.aantal }
    }

    class Treffer(val product: Product, val barcode: Barcode)

    @Volatile var producten: List<Product> = emptyList()
        private set
    @Volatile var dervingRedenen: List<Pair<String, String>> = emptyList()
        private set
    @Volatile private var opCode: Map<String, Treffer> = emptyMap()
    private var geladen = false

    private fun bestand(context: Context) = File(context.filesDir, "catalogus.json")
    private fun etagBestand(context: Context) = File(context.filesDir, "catalogus.etag")

    @Synchronized
    fun laad(context: Context) {
        if (geladen) return
        geladen = true
        try {
            val f = bestand(context)
            if (f.exists()) zetUit(JSONObject(f.readText()))
        } catch (e: Exception) {
            bestand(context).delete()
            etagBestand(context).delete()
        }
    }

    val leeg get() = producten.isEmpty()

    /** Haalt de nieuwste lijst op. Geeft true als er iets veranderd is. Gooit Api.Fout bij een probleem. */
    suspend fun ververs(context: Context): Boolean {
        laad(context)
        val etag = etagBestand(context).takeIf { it.exists() && !leeg }?.readText()
        val antwoord = Api.get(context, "/api/app/producten", etag)
        if (antwoord.status == 304 || antwoord.json == null) return false
        withContext(Dispatchers.IO) {
            bestand(context).writeText(antwoord.json.toString())
            antwoord.etag?.let { etagBestand(context).writeText(it) } ?: etagBestand(context).delete()
        }
        zetUit(antwoord.json)
        return true
    }

    private fun zetUit(json: JSONObject) {
        val lijst = json.getJSONArray("producten").objecten().map(::product)
        val redenen = json.optJSONObject("derving_redenen")
        dervingRedenen = redenen?.keys()?.asSequence()?.map { it to redenen.getString(it) }?.toList() ?: emptyList()
        zetProducten(lijst)
    }

    private fun zetProducten(lijst: List<Product>) {
        val index = HashMap<String, Treffer>()
        for (p in lijst) for (b in p.barcodes) index[b.code] = Treffer(p, b)
        producten = lijst
        opCode = index
    }

    fun product(json: JSONObject) = Product(
        id = json.getInt("id"),
        naam = json.getString("naam"),
        categorie = json.optString("categorie"),
        subcategorie = json.optString("subcategorie"),
        merk = json.optString("merk"),
        eenheid = json.optString("eenheid").ifEmpty { "stuks" },
        voorraad = json.optInt("voorraad"),
        minVoorraad = json.optInt("min_voorraad"),
        actief = json.optBoolean("actief", true),
        besteleenheid = json.tekstOfNull("besteleenheid"),
        perBesteleenheid = json.optInt("per_besteleenheid", 1),
        barcodes = json.optJSONArray("barcodes")?.objecten()?.map {
            Barcode(
                it.getString("code"), it.optString("niveau"), it.optInt("aantal", 1), it.optString("artikel"),
                doosAantal = if (it.isNull("doos_aantal")) null else it.optInt("doos_aantal"),
                doosCode = it.tekstOfNull("doos_code"),
            )
        } ?: emptyList(),
        foto = json.tekstOfNull("foto"),
        fotoGroot = json.tekstOfNull("foto_groot"),
        leverancier = json.tekstOfNull("leverancier"),
    )

    /** Een product dat net is bijgewerkt (geboekt, barcode gekoppeld): meteen goed in de lijst, zonder op het
     * verversen te wachten. */
    @Synchronized
    fun werkBij(context: Context, nieuw: Product) {
        val lijst = producten.toMutableList()
        val i = lijst.indexOfFirst { it.id == nieuw.id }
        if (i >= 0) lijst[i] = nieuw else lijst.add(nieuw)
        zetProducten(lijst)
        // Het bestand klopt nu niet meer met de ETag: de volgende keer gewoon de hele lijst ophalen.
        etagBestand(context).delete()
    }

    fun opId(id: Int): Product? = producten.firstOrNull { it.id == id }

    /** Een gescande barcode, net zo genormaliseerd als op de site (barcodes.normaliseer). */
    fun opBarcode(tekst: String): Treffer? = normaliseerCode(tekst)?.let { opCode[it] }

    fun categorieen(): List<String> = producten.filter { it.actief }.map { it.categorie }.filter { it.isNotEmpty() }.distinct()

    /** Zoeken op (een deel van) de naam, categorie of het merk; elk woord moet ergens in voorkomen. Wat met de
     * zoekterm begint eerst. Een barcode vindt zijn product. */
    fun zoek(term: String, categorie: String? = null, alleenLaag: Boolean = false, ookInactief: Boolean = false): List<Product> {
        val schoon = term.trim()
        opBarcode(schoon)?.let { return listOf(it.product) }
        val woorden = normaal(schoon).split(' ').filter { it.isNotEmpty() }
        val kandidaten = producten.filter { p ->
            (ookInactief || p.actief || woorden.isNotEmpty()) &&
                (categorie == null || p.categorie == categorie) &&
                (!alleenLaag || p.laag) &&
                woorden.all { p.zoektekst.contains(it) }
        }
        if (woorden.isEmpty()) return kandidaten
        val eerste = woorden.first()
        return kandidaten.sortedWith(compareBy<Product>({ !it.actief }, { !normaal(it.naam).startsWith(eerste) }))
    }

    fun normaliseerCode(tekst: String): String? {
        var code = tekst.filterNot { it.isWhitespace() }
        if (code.isEmpty() || !code.all { it.isDigit() }) return null
        if (code.length == 12) code = "0$code"
        if (code.length == 14 && code.startsWith("0")) code = code.substring(1)
        return code
    }

    fun normaal(tekst: String): String =
        Normalizer.normalize(tekst.lowercase(), Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")
}
