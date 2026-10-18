/* Wat de app doet met een scan van de Zebra-scanner (zie Scanner.kt en HoofdActivity.verwerkScan). Bewust ES5:
   op een TC51 met Android 6 kan de WebView oud zijn. Geeft terug wat er met de scan is gebeurd.

   Volgorde:
   1. De pagina mag het zelf afhandelen: een 'kantine-scan'-event op document met detail.code. Roept een
      luisteraar preventDefault() aan, dan doen wij niets meer.
   2. Een tekstveld met de focus krijgt de code. Is het een scanveld (zoals bij Factuur inboeken) in een
      formulier met verder niets in te vullen, dan wordt het meteen verstuurd, net als een scanner met Enter.
      Staat de focus op een getalveld waar al iets in staat (zoals het aantal bij het tellen), dan doen we niets:
      anders zou de barcode als aantal worden ingevuld, of zou je wegspringen en is wat je intikte weg. Een leeg
      getalveld (bijvoorbeeld het aantal dat op de productpagina vanzelf geselecteerd is) houdt niets tegen.
   3. Anders: een scanveld op de pagina zelf.
   4. Anders: naar de barcodepagina van de site (/barcodes/zoek?direct=1). Een bekende barcode gaat daar meteen
      door naar het product, een onbekende kun je er toevoegen. Dat gebeurt op de server, dus het werkt ook als de
      WebView te oud is voor de JavaScript van de site. (Een gescande link naar de site, zoals een QR-code, opent
      HoofdActivity.verwerkScan al zelf.) */
(function (code) {
    function tekstVeld(el) {
        if (!el || el.tagName !== 'INPUT' || el.disabled || el.readOnly) return false;
        var soort = (el.getAttribute('type') || 'text').toLowerCase();
        return soort === 'text' || soort === 'search' || soort === 'tel';
    }
    function zichtbaar(el) {
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }
    function isScanVeld(el) {
        if (el.hasAttribute('data-scan')) return true;
        if (el.id === 'pda-zoek-invoer') return false; // de zoekbalk: zie stap 4
        var tekst = (el.getAttribute('placeholder') || '') + ' ' + (el.name || '') + ' ' + (el.id || '');
        return /scan|barcode|ean/i.test(tekst);
    }
    function alleenDitVeld(veld) {
        if (!veld.form) return false;
        var velden = veld.form.querySelectorAll('input, select, textarea');
        for (var i = 0; i < velden.length; i++) {
            var v = velden[i];
            var soort = (v.getAttribute('type') || '').toLowerCase();
            if (v === veld || soort === 'hidden' || soort === 'submit' || soort === 'button' || !zichtbaar(v)) continue;
            return false;
        }
        return true;
    }
    function zet(veld, waarde) {
        // Via de setter van het prototype, zodat ook scripts die de waarde bijhouden het merken.
        var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (setter && setter.set) setter.set.call(veld, waarde); else veld.value = waarde;
        veld.dispatchEvent(new Event('input', { bubbles: true }));
        veld.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function drukEnter(veld) {
        var toets;
        try {
            toets = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true });
            Object.defineProperty(toets, 'keyCode', { get: function () { return 13; } });
            Object.defineProperty(toets, 'which', { get: function () { return 13; } });
            // Een oude WebView kent 'key' nog niet; de zoekbalk van de site kijkt daar wel naar.
            if (toets.key !== 'Enter') Object.defineProperty(toets, 'key', { get: function () { return 'Enter'; } });
        } catch (e) {
            return true;
        }
        return veld.dispatchEvent(toets);
    }
    function verstuur(form) {
        if (form.requestSubmit) { form.requestSubmit(); return; }
        var knop = form.querySelector('button[type=submit], input[type=submit], button:not([type])');
        if (knop) knop.click(); else form.submit();
    }
    function naarBarcodePagina() {
        window.location.href = '/barcodes/zoek?direct=1&code=' + encodeURIComponent(code);
        return 'barcode';
    }

    try {
        var ev;
        try {
            ev = new CustomEvent('kantine-scan', { detail: { code: code }, cancelable: true });
        } catch (e) {
            ev = document.createEvent('CustomEvent');
            ev.initCustomEvent('kantine-scan', true, true, { code: code });
        }
        if (!document.dispatchEvent(ev)) return 'pagina';

        var actief = document.activeElement;
        if (actief && actief.tagName === 'INPUT' && (actief.getAttribute('type') || '').toLowerCase() === 'number' &&
            actief.value !== '') {
            return 'genegeerd';
        }
        var veld = null;
        if (tekstVeld(actief) && zichtbaar(actief) && actief.id !== 'pda-zoek-invoer') {
            if (!isScanVeld(actief)) {
                zet(actief, code); // een gewoon tekstveld: alleen invullen, niet versturen
                return 'ingevuld';
            }
            veld = actief;
        }
        if (!veld) {
            var kandidaten = document.querySelectorAll('main input');
            for (var i = 0; i < kandidaten.length; i++) {
                if (tekstVeld(kandidaten[i]) && zichtbaar(kandidaten[i]) && isScanVeld(kandidaten[i])) { veld = kandidaten[i]; break; }
            }
        }
        if (!veld) return naarBarcodePagina();

        zet(veld, code);
        var doorgaan = drukEnter(veld);
        if (doorgaan && alleenDitVeld(veld)) { verstuur(veld.form); return 'verstuurd'; }
        return 'ingevuld';
    } catch (e) {
        return naarBarcodePagina();
    }
})
