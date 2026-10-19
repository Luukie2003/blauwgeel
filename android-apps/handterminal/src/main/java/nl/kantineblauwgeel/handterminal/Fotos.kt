package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import android.widget.ImageView
import androidx.core.view.isVisible
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Productfoto's: één keer downloaden, daarna van het toestel (en de laatst gebruikte uit het geheugen). Zo staan
 * ze er bij het tellen meteen, ook bij een slechte verbinding. De site geeft verkleinde foto's (zie _foto in
 * routes/app_api.py); een foto met een nieuwe naam is een nieuwe foto, dus verversen hoeft nooit. */
object Fotos {

    private val geheugen = object : LruCache<String, Bitmap>(8 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private fun bestand(context: Context, pad: String) =
        File(File(context.cacheDir, "fotos").apply { mkdirs() }, pad.substringAfterLast('/'))

    /** De foto in [beeld] zetten; zonder foto (of als hij niet te laden is) wordt [beeld] verborgen. */
    fun toon(beeld: ImageView, pad: String?, verbergZonder: Boolean = true) {
        beeld.tag = pad
        if (pad == null) {
            beeld.setImageDrawable(null)
            if (verbergZonder) beeld.isVisible = false
            return
        }
        geheugen.get(pad)?.let {
            beeld.setImageBitmap(it)
            beeld.isVisible = true
            return
        }
        beeld.setImageDrawable(null)
        val context = beeld.context.applicationContext
        scope.launch {
            val bitmap = laad(context, pad)
            if (beeld.tag != pad) return@launch // de regel is intussen hergebruikt voor een ander product
            if (bitmap != null) {
                beeld.setImageBitmap(bitmap)
                beeld.isVisible = true
            } else if (verbergZonder) {
                beeld.isVisible = false
            }
        }
    }

    /** Alvast ophalen (bijvoorbeeld de foto's van de volgende producten bij het tellen). */
    fun haalAlvast(context: Context, paden: List<String?>) {
        val app = context.applicationContext
        scope.launch { for (pad in paden.filterNotNull()) if (geheugen.get(pad) == null) laad(app, pad) }
    }

    private suspend fun laad(context: Context, pad: String): Bitmap? = withContext(Dispatchers.IO) {
        try {
            val f = bestand(context, pad)
            if (!f.exists() || f.length() == 0L) {
                val verbinding = Beveiliging.open(context, Instellingen(context).basisUrl + pad)
                try {
                    verbinding.connectTimeout = 8_000
                    verbinding.readTimeout = 15_000
                    if (verbinding.responseCode !in 200..299) return@withContext null
                    val tijdelijk = File(f.parentFile, f.name + ".tmp")
                    verbinding.inputStream.use { invoer -> tijdelijk.outputStream().use { invoer.copyTo(it) } }
                    tijdelijk.renameTo(f)
                } finally {
                    verbinding.disconnect()
                }
            }
            BitmapFactory.decodeFile(f.path)?.also { geheugen.put(pad, it) }
        } catch (e: Exception) {
            null
        }
    }
}
