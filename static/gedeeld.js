document.addEventListener("click", function (e) {
    var trigger = e.target.closest(".menu-trigger");
    document.querySelectorAll(".menu-item.open").forEach(function (item) {
        if (!trigger || item !== trigger.closest(".menu-item")) {
            item.classList.remove("open");
        }
    });
    if (trigger) {
        trigger.closest(".menu-item").classList.toggle("open");
    }
});

document.addEventListener("click", function (e) {
    if (e.target.closest("#zijbalk-toggle")) {
        document.getElementById("app-zijbalk").classList.toggle("open");
    }
    // Eenvoudige weergave: "Alle onderdelen" klapt het hele menu onder de favorieten uit en weer in.
    var alles = e.target.closest("#zijbalk-alles-knop");
    if (alles) {
        var open = document.getElementById("app-zijbalk").classList.toggle("alles");
        alles.setAttribute("aria-expanded", open ? "true" : "false");
        alles.textContent = open ? "Minder onderdelen" : "Alle onderdelen";
    }
});

// ---------- Zijbalk: één groep tegelijk open ----------
// Alleen de groep met de pagina waar je nu bent staat open; de rest is dicht. Klik je op een
// andere groep, dan klapt die open en de vorige dicht (een accordeon), zodat het menu nooit
// uitgroeit tot een lange lijst. Een groep die je zelf dichtklikt blijft dicht tot je naar een
// andere pagina gaat. Er wordt bewust niets onthouden: elke pagina begint weer overzichtelijk.
//
// Dit script staat vóór de zijbalk in de HTML (zie base.html), dus de groepen bestaan nog niet
// op het moment dat dit script geparsed wordt -- vandaar dat alles tot na DOMContentLoaded wacht.
document.addEventListener("DOMContentLoaded", function () {
    var groepen = document.querySelectorAll(".zijbalk-groep");
    if (!groepen.length) return;

    // De sleutel van de vorige versie (meerdere groepen onthouden) is niet meer nodig.
    try { localStorage.removeItem("zijbalk-open-groepen"); } catch (e) { /* niet erg */ }

    function zet(groep, open) {
        groep.classList.toggle("dicht", !open);
        var knop = groep.querySelector(".zijbalk-groepkop");
        if (knop) knop.setAttribute("aria-expanded", open ? "true" : "false");
    }

    groepen.forEach(function (groep) {
        var heeftActieveLink = !!groep.querySelector("a.actief");
        groep.classList.toggle("heeft-actief", heeftActieveLink);
        zet(groep, heeftActieveLink);
    });

    document.addEventListener("click", function (e) {
        var knop = e.target.closest(".zijbalk-groepkop");
        if (!knop) return;
        var groep = knop.closest(".zijbalk-groep");
        var openen = groep.classList.contains("dicht");
        groepen.forEach(function (andere) { zet(andere, andere === groep && openen); });
    });
});

function modalOpenen(id) {
    document.getElementById(id).classList.add("open");
}
function modalSluiten(id) {
    document.getElementById(id).classList.remove("open");
}
document.addEventListener("click", function (e) {
    if (e.target.classList.contains("modal-overlay")) {
        e.target.classList.remove("open");
    }
});

// ---------- Bevestigen via pop-up i.p.v. de kale browser-confirm() ----------
// opties (mag weg): {ja: "Ja, afbreken", nee: "Nee, verder tellen"} -- duidelijker dan
// "Bevestigen" en "Annuleren" als de vraag zelf over annuleren gaat.
function toonBevestiging(bericht, callback, opties) {
    var overlay = document.getElementById("bevestig-modal");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "bevestig-modal";
        overlay.className = "modal-overlay";
        overlay.innerHTML =
            '<div class="modal-venster modal-venster-bevestig">' +
            '<p id="bevestig-modal-tekst"></p>' +
            '<div class="modal-knoppen">' +
            '<button type="button" class="btn btn-rand" data-actie="annuleren">Annuleren</button>' +
            '<button type="button" class="btn btn-gevaar" data-actie="bevestigen">Bevestigen</button>' +
            "</div></div>";
        document.body.appendChild(overlay);
    }
    overlay.querySelector("#bevestig-modal-tekst").textContent = bericht;
    overlay.querySelector('[data-actie="annuleren"]').textContent = (opties && opties.nee) || "Annuleren";
    overlay.querySelector('[data-actie="bevestigen"]').textContent = (opties && opties.ja) || "Bevestigen";
    var sluiten = function () {
        overlay.classList.remove("open");
    };
    overlay.querySelector('[data-actie="annuleren"]').onclick = sluiten;
    overlay.querySelector('[data-actie="bevestigen"]').onclick = function () {
        sluiten();
        callback();
    };
    overlay.classList.add("open");
}

// Vervangt onsubmit="return confirm(...)": zelfde bevestig-stap, maar
// met de pop-up van de site i.p.v. de lelijke kale browserdialoog.
// De submit zelf blijft daarna een gewone paginaherlaad.
function bevestigEnVerstuur(form, bericht, opties) {
    toonBevestiging(bericht, function () {
        form.submit();
    }, opties);
    return false;
}

// ---------- Kleine meldingen (toast) rechtsonder ----------
function toonToast(tekst) {
    var stapel = document.getElementById("toast-stapel");
    if (!stapel) {
        stapel = document.createElement("div");
        stapel.id = "toast-stapel";
        stapel.className = "toast-stapel";
        document.body.appendChild(stapel);
    }
    var toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = tekst;
    stapel.appendChild(toast);
    requestAnimationFrame(function () {
        toast.classList.add("zichtbaar");
    });
    setTimeout(function () {
        toast.classList.remove("zichtbaar");
        setTimeout(function () {
            toast.remove();
        }, 200);
    }, 3200);
}

// ---------- Offline-wachtrij voor formulieren die dat aanvragen ----------
// Formulieren met data-offline-wachtrij="1" (zie boeken.html en
// product_detail.html) belanden bij een echte netwerkfout niet in een
// kale mislukte paginaherlaad, maar in een wachtrij op dit toestel
// (localStorage) die vanzelf leegloopt zodra er weer verbinding is --
// fijn voor het boeken van voorraad met wisselend bereik in het
// voorraadhok. Alleen bedoeld voor dit soort "vuur en vergeet"-acties,
// niet voor elk js-ajax-form: een mislukte beheeractie (bijv. een
// product verwijderen) moet je gewoon meteen zien mislukken, niet
// straks stilzwijgend alsnog uitgevoerd worden.
var OFFLINE_WACHTRIJ_SLEUTEL = "kantine-offline-wachtrij";
var offlineWachtrijBezig = false;

function offlineWachtrijLezen() {
    try {
        return JSON.parse(localStorage.getItem(OFFLINE_WACHTRIJ_SLEUTEL) || "[]");
    } catch (e) {
        return [];
    }
}

function offlineWachtrijSchrijven(lijst) {
    try {
        localStorage.setItem(OFFLINE_WACHTRIJ_SLEUTEL, JSON.stringify(lijst));
    } catch (e) {
        // localStorage kan geblokkeerd zijn (bijv. privénavigatie) --
        // de actie is dan alsnog uitgevoerd zodra er weer bereik is
        // vanuit dit tabblad, maar overleeft het sluiten ervan niet.
    }
}

function offlineWachtrijToevoegen(form) {
    var data = Array.from(new FormData(form).entries());
    var lijst = offlineWachtrijLezen();
    lijst.push({ url: form.action, data: data, ts: Date.now() });
    offlineWachtrijSchrijven(lijst);
    toonToast(
        (form.dataset.offlineWachtrij || "Actie") +
            " opgeslagen zonder verbinding — wordt verstuurd zodra je weer bereik hebt."
    );
    form.reset();
}

function offlineWachtrijVerwerken() {
    if (offlineWachtrijBezig) return;
    var lijst = offlineWachtrijLezen();
    if (!lijst.length) return;
    offlineWachtrijBezig = true;
    var item = lijst[0];
    // Alleen op resp.ok controleren, bewust geen JSON proberen te lezen:
    // deze wachtrij bedient zowel gewone formulieren (die uiteindelijk
    // een HTML-pagina teruggeven na een redirect) als js-ajax-forms (die
    // JSON teruggeven) -- resp.ok is het enige dat beide gemeen hebben.
    fetch(item.url, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new URLSearchParams(item.data),
    })
        .then(function (resp) {
            if (!resp.ok) throw new Error("serverfout");
            var rest = offlineWachtrijLezen();
            rest.shift();
            offlineWachtrijSchrijven(rest);
            toonToast("Eerder opgeslagen actie alsnog verstuurd.");
        })
        .catch(function () {
            // Nog steeds geen verbinding (of alsnog een serverfout) --
            // laten staan, een volgende 'online'-gebeurtenis of
            // paginabezoek probeert het opnieuw.
        })
        .finally(function () {
            offlineWachtrijBezig = false;
            if (offlineWachtrijLezen().length) offlineWachtrijVerwerken();
        });
}

window.addEventListener("online", offlineWachtrijVerwerken);
document.addEventListener("DOMContentLoaded", offlineWachtrijVerwerken);

// ---------- Formulieren die geen volledige paginaherlaad meer nodig hebben ----------
// Een form met class "js-ajax-form" wordt via fetch() verstuurd i.p.v.
// een gewone submit; de route herkent dit (zie is_ajax_verzoek() in
// app.py) en geeft JSON terug in plaats van een redirect. Heeft de
// form ook data-bevestig, dan verschijnt eerst de bevestigings-pop-up.
// Lukt het fetch-verzoek niet, dan onderscheiden we twee gevallen: een
// echte netwerkfout (fetch zelf gooit een TypeError) op een form met
// data-offline-wachtrij gaat de wachtrij hierboven in; al het andere
// (serverfout, oude sessie, geen JS-ondersteunde route) valt terug op
// een gewone submit, zodat de actie hoe dan ook gewoon lukt.
document.addEventListener("submit", function (e) {
    var form = e.target.closest(".js-ajax-form");
    if (!form) return;
    e.preventDefault();
    var versturen = function () {
        fetch(form.action, {
            method: "POST",
            headers: { "X-Requested-With": "fetch" },
            body: new FormData(form),
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error("serverfout");
                return resp.json();
            })
            .then(function (data) {
                if (!data.ok) throw new Error(data.fout || "mislukt");
                form.dispatchEvent(
                    new CustomEvent("ajax-form:success", { detail: data, bubbles: true })
                );
            })
            .catch(function (fout) {
                if (form.dataset.offlineWachtrij && fout instanceof TypeError) {
                    offlineWachtrijToevoegen(form);
                    return;
                }
                form.submit();
            });
    };
    if (form.dataset.bevestig) {
        toonBevestiging(form.dataset.bevestig, versturen);
    } else {
        versturen();
    }
});

// Standaardgedrag bij succes: gewoon een toast tonen. Pagina's met
// eigen opmaak (bijv. de stemmenlijst) luisteren zelf ook naar
// "ajax-form:success" om daarnaast nog iets in de DOM bij te werken.
document.addEventListener("ajax-form:success", function (e) {
    if (e.detail && e.detail.melding) {
        toonToast(e.detail.melding);
    }
});

// ---------- Noodstop: ook een pagina die al openstaat gaat dicht ----------
// Drukt de eigenaar op de noodstop (Beheer > Noodstop, zie noodstop.py), dan
// krijgt elk volgend verzoek het afgesloten-scherm. Een pagina die al openstond
// (op een andere computer, de tablet) bleef tot dan gewoon staan; daarom kijkt
// elke pagina elke 30 seconden, en meteen als je hem weer voor je haalt, of de
// site is afgesloten, en herlaadt dan. Ook bij beheerders: iedereen wordt
// uitgelogd. Wie tijdens de noodstop met de noodcode inlogde (data-noodstop-binnen
// op <body>), werkt gewoon door; die pagina's hoeven niet te kijken.
(function () {
    if (document.body.dataset.noodstopBinnen === "1") return;
    function kijk() {
        if (document.visibilityState !== "visible") return;
        fetch("/noodstop/status", { cache: "no-store", credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.actief === true) window.location.reload();
            })
            .catch(function () {});
    }
    setInterval(kijk, 30000);
    document.addEventListener("visibilitychange", kijk);
})();

// Cachet alleen de schil (stijl, logo) en toont een nette offline-pagina
// i.p.v. de kale foutmelding van de browser bij geen verbinding -- zie
// static/sw.js. Bemoeit zich niet met formulieren/boekingen, dat doet
// de wachtrij hierboven.
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {
        // Kan mislukken zonder verbinding (of op een browser die het
        // niet ondersteunt) -- de rest van de site werkt dan gewoon
        // door, alleen zonder de offline-schil.
    });
}

(function () {
    var banner = document.getElementById("site-banner");
    if (!banner) return;
    var tekst = banner.dataset.bannerTekst;
    if (localStorage.getItem("banner-weggeklikt") === tekst) {
        banner.style.display = "none";
        return;
    }
    var sluiten = document.getElementById("site-banner-sluiten");
    sluiten.addEventListener("click", function () {
        localStorage.setItem("banner-weggeklikt", tekst);
        banner.style.display = "none";
    });
})();

// ---------- Tabbladen binnen 1 pagina ----------
// Zie .tab-balk/.tab-knop/.tab-paneel in style.css. Markup: een
// <div class="tab-balk" data-tab-js> met daarin knoppen
// data-tab-doel="naam", en ergens op de pagina bijpassende panelen
// data-tab-paneel="naam". Alleen voor tabbladen die panelen op DEZELFDE
// pagina tonen/verbergen (bijv. kiosk_sponsoren_leden.html) -- een
// subnav van gewone links naar andere pagina's (bijv. de sub-navigatie
// boven Prijzenscherm & acties) heeft deze JS niet nodig, "actief"
// wordt daar gewoon server-side bepaald. Het huidige tabblad staat in het
// URL-fragment (#naam), zodat een link van elders (bijv. vanaf de
// kantine-tv-hub) direct op het juiste tabblad kan uitkomen en
// verversen niet terugvalt op het eerste tabblad.
//
// Dit script staat vóór de pagina-inhoud in de HTML (zie base.html,
// zelfde reden als de inklapbare zijbalk-groepen hierboven), dus de
// tabbladen/panelen bestaan nog niet op het moment dat dit script
// geparsed wordt -- vandaar ook hier tot na DOMContentLoaded wachten.
document.addEventListener("DOMContentLoaded", function () {
    var balken = document.querySelectorAll(".tab-balk[data-tab-js]");
    if (!balken.length) return;

    function activeer(doel) {
        document.querySelectorAll("[data-tab-doel]").forEach(function (knop) {
            knop.classList.toggle("actief", knop.dataset.tabDoel === doel);
        });
        document.querySelectorAll("[data-tab-paneel]").forEach(function (paneel) {
            paneel.hidden = paneel.dataset.tabPaneel !== doel;
        });
    }

    balken.forEach(function (balk) {
        balk.addEventListener("click", function (e) {
            var knop = e.target.closest("[data-tab-doel]");
            if (!knop) return;
            e.preventDefault();
            activeer(knop.dataset.tabDoel);
            history.replaceState(null, "", "#" + knop.dataset.tabDoel);
        });
    });

    var starttab = (location.hash || "").slice(1);
    var startKnop = starttab && document.querySelector('[data-tab-doel="' + starttab + '"]');
    var eersteKnop = document.querySelector("[data-tab-doel]");
    if (startKnop) {
        activeer(starttab);
    } else if (eersteKnop) {
        activeer(eersteKnop.dataset.tabDoel);
    }
});


// ---------- Zoekbalk in de titelbalk ----------
// Typt iemand in de zoekbalk, dan haalt dit na een korte pauze de beste
// resultaten op (zie /zoeken/live in routes/zoeken.py) en toont ze direct in
// een lijstje; Enter opent de volledige resultatenpagina. De sneltoets "/"
// zet de cursor in de zoekbalk, tenzij je al in een invoerveld typt.
document.addEventListener("DOMContentLoaded", function () {
    var formulier = document.getElementById("zoekbalk");
    var invoer = document.getElementById("zoekbalk-invoer");
    var lijst = document.getElementById("zoekbalk-resultaten");
    if (!formulier || !invoer || !lijst) return;

    var timer = null;
    var lopend = null;
    var actief = -1;

    function verberg() {
        lijst.hidden = true;
        lijst.textContent = "";
        actief = -1;
    }

    // Laatste zoekopdrachten, alleen in deze browser onthouden (localStorage kan
    // geblokkeerd zijn, bijvoorbeeld in een privévenster: dan werkt zoeken gewoon zonder).
    var RECENT_SLEUTEL = "zoek-recent";
    function leesRecent() {
        try {
            var lijstje = JSON.parse(localStorage.getItem(RECENT_SLEUTEL) || "[]");
            return Array.isArray(lijstje) ? lijstje.filter(function (t) { return typeof t === "string"; }) : [];
        } catch (e) { return []; }
    }
    function bewaarRecent(term) {
        term = (term || "").trim();
        if (term.length < 2) return;
        var nieuw = [term].concat(leesRecent().filter(function (t) { return t.toLowerCase() !== term.toLowerCase(); }));
        try { localStorage.setItem(RECENT_SLEUTEL, JSON.stringify(nieuw.slice(0, 5))); } catch (e) { /* niet erg */ }
    }
    function wisRecent() {
        try { localStorage.removeItem(RECENT_SLEUTEL); } catch (e) { /* niet erg */ }
    }
    function toonRecent() {
        var termen = leesRecent();
        if (!termen.length) { verberg(); return; }
        lijst.textContent = "";
        var kop = document.createElement("div");
        kop.className = "zoek-groep-titel";
        kop.textContent = "Recent gezocht";
        lijst.appendChild(kop);
        termen.forEach(function (term) {
            var a = document.createElement("a");
            a.className = "zoek-resultaat";
            a.href = "/zoeken?q=" + encodeURIComponent(term);
            a.textContent = term;
            lijst.appendChild(a);
        });
        var wis = document.createElement("a");
        wis.className = "zoek-alle";
        wis.href = "#";
        wis.textContent = "Wissen";
        wis.addEventListener("click", function (e) { e.preventDefault(); wisRecent(); verberg(); });
        lijst.appendChild(wis);
        lijst.hidden = false;
        actief = -1;
    }

    function links() {
        return lijst.querySelectorAll(".zoek-resultaat");
    }

    function markeer(nieuw) {
        var alle = links();
        if (!alle.length) return;
        actief = (nieuw + alle.length) % alle.length;
        alle.forEach(function (a, i) {
            a.classList.toggle("actief", i === actief);
        });
        alle[actief].scrollIntoView({ block: "nearest" });
    }

    function toon(antwoord) {
        lijst.textContent = "";
        if (!antwoord.groepen.length) {
            var leeg = document.createElement("div");
            leeg.className = "zoek-leeg";
            leeg.textContent = "Niets gevonden.";
            lijst.appendChild(leeg);
        }
        antwoord.groepen.forEach(function (groep) {
            var kop = document.createElement("div");
            kop.className = "zoek-groep-titel";
            kop.textContent = groep.titel;
            lijst.appendChild(kop);
            groep.resultaten.forEach(function (r) {
                var a = document.createElement("a");
                a.className = "zoek-resultaat";
                a.href = r.url;
                a.textContent = r.titel;
                if (r.detail) {
                    var klein = document.createElement("small");
                    klein.textContent = r.detail;
                    a.appendChild(klein);
                }
                lijst.appendChild(a);
            });
        });
        if (antwoord.groepen.length) {
            var alle = document.createElement("a");
            alle.className = "zoek-alle";
            alle.href = antwoord.alle_url;
            alle.textContent = "Alle resultaten bekijken";
            lijst.appendChild(alle);
        }
        lijst.hidden = false;
        actief = -1;
    }

    function zoek() {
        var term = invoer.value.trim();
        if (term.length < 2) { if (term.length === 0) toonRecent(); else verberg(); return; }
        if (lopend) lopend.abort();
        lopend = new AbortController();
        fetch("/zoeken/live?q=" + encodeURIComponent(term), { signal: lopend.signal, credentials: "same-origin" })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (antwoord) { if (antwoord && invoer.value.trim() === term) toon(antwoord); })
            .catch(function () { /* afgebroken of offline: dan blijft het lijstje zoals het was */ });
    }

    invoer.addEventListener("focus", function () {
        if (!invoer.value.trim()) toonRecent();
    });
    formulier.addEventListener("submit", function () { bewaarRecent(invoer.value); });
    lijst.addEventListener("click", function (e) {
        // Een resultaat aanklikken telt ook als een zoekopdracht om te onthouden.
        if (e.target.closest(".zoek-resultaat") && invoer.value.trim()) bewaarRecent(invoer.value);
    });
    invoer.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(zoek, 200);
    });
    invoer.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { verberg(); invoer.blur(); }
        else if (e.key === "ArrowDown") { e.preventDefault(); markeer(actief + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); markeer(actief - 1); }
        else if (e.key === "Enter" && actief >= 0) { e.preventDefault(); links()[actief].click(); }
    });
    document.addEventListener("click", function (e) {
        if (!e.target.closest("#zoekbalk")) verberg();
    });
    document.addEventListener("keydown", function (e) {
        var doel = e.target;
        var typt = doel && (doel.tagName === "INPUT" || doel.tagName === "TEXTAREA" || doel.tagName === "SELECT" || doel.isContentEditable);
        if (e.key === "/" && !typt && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            invoer.focus();
            invoer.select();
        }
    });
});

// @naam taggen: een veld met data-tag-autocomplete toont, zodra je een @ typt, de accounts die erbij passen. De namen
// staan op de pagina in <script type="application/json" id="gebruikersnamen-data"> (prikbord en taken).
document.addEventListener("DOMContentLoaded", function () {
    var gebruikersnamenEl = document.getElementById("gebruikersnamen-data");
    if (!gebruikersnamenEl) return;
    var gebruikersnamen = JSON.parse(gebruikersnamenEl.textContent);
    if (!gebruikersnamen.length) return;

    document.querySelectorAll("[data-tag-autocomplete]").forEach(function (veld) {
        var lijst = document.createElement("div");
        lijst.className = "tag-suggesties";
        lijst.style.display = "none";
        veld.insertAdjacentElement("afterend", lijst);

        function huidigeAtWoord() {
            var voor = veld.value.slice(0, veld.selectionStart);
            var match = voor.match(/@([A-Za-z0-9_.\-]*)$/);
            return match ? match[1] : null;
        }

        function verbergen() {
            lijst.style.display = "none";
            lijst.innerHTML = "";
        }

        function bijwerken() {
            var deel = huidigeAtWoord();
            if (deel === null) { verbergen(); return; }
            var suggesties = gebruikersnamen.filter(function (naam) {
                return naam.toLowerCase().indexOf(deel.toLowerCase()) === 0;
            });
            if (!suggesties.length) { verbergen(); return; }
            lijst.innerHTML = "";
            suggesties.forEach(function (naam) {
                var item = document.createElement("button");
                item.type = "button";
                item.className = "tag-suggestie";
                item.textContent = "@" + naam;
                item.addEventListener("click", function () {
                    var pos = veld.selectionStart;
                    var voor = veld.value.slice(0, pos).replace(/@([A-Za-z0-9_.\-]*)$/, "@" + naam + " ");
                    veld.value = voor + veld.value.slice(pos);
                    verbergen();
                    veld.focus();
                });
                lijst.appendChild(item);
            });
            lijst.style.display = "block";
        }

        veld.addEventListener("input", bijwerken);
        veld.addEventListener("blur", function () {
            setTimeout(verbergen, 150); // laat een klik op een suggestie nog wel doorkomen
        });
    });
});

// Zware onderdelen van een pagina laden na de rest: <div data-lazy-bron="/url">…</div> haalt die url op en zet het antwoord
// (HTML) in het blok zodra het er is. Het blok toont tot dan wat erin staat; mislukt het laden, dan wordt de tekst in het
// element met data-lazy-status vervangen door data-lazy-fout. De berekeningen van het voorspelmodel duren op de server soms
// enkele seconden; zo staat de pagina zelf meteen klaar.
//
// Is alles geladen (gelukt of niet), dan gaat er een "lazy-klaar"-seintje op document af; het overzicht gebruikt dat om
// daarna het voorspelmodel alvast te laten rekenen zonder de eerste berekening in de weg te zitten.
document.addEventListener("DOMContentLoaded", function () {
    var laden = [];
    document.querySelectorAll("[data-lazy-bron]").forEach(function (blok) {
        laden.push(
            fetch(blok.dataset.lazyBron, { credentials: "same-origin" })
                .then(function (antwoord) {
                    // redirected: de sessie is verlopen en we kregen de inlogpagina terug
                    if (!antwoord.ok || antwoord.redirected) throw new Error("niet gelukt");
                    return antwoord.text();
                })
                .then(function (html) { blok.innerHTML = html; })
                .catch(function () {
                    var status = blok.querySelector("[data-lazy-status]");
                    if (status) status.textContent = blok.dataset.lazyFout || "Laden is niet gelukt. Ververs de pagina om het opnieuw te proberen.";
                })
        );
    });
    Promise.all(laden).then(function () { document.dispatchEvent(new Event("lazy-klaar")); });
});

// Turven: een invoerveld met data-turf="1,5,24:krat" krijgt knoppen om er snel iets bij op te tellen, zoals je dat met
// streepjes op papier doet (+1, +5, een hele krat) en een knop om er een af te halen. Een stap met een naam erachter
// (24:krat) toont die naam op de knop. Het veld zelf blijft gewoon een getal dat je ook kunt typen.
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input[data-turf]").forEach(function (veld) {
        var groep = document.createElement("span");
        groep.className = "turf-knoppen";

        function knop(tekst, delta) {
            var b = document.createElement("button");
            b.type = "button";
            b.className = "btn btn-rand btn-klein turf-knop";
            b.textContent = tekst;
            b.setAttribute("aria-label", (delta > 0 ? "Tel er " + delta + " bij" : "Haal er 1 af") + (veld.getAttribute("aria-label") ? " bij " + veld.getAttribute("aria-label") : ""));
            b.addEventListener("click", function () {
                var huidig = parseInt(veld.value, 10);
                if (isNaN(huidig)) huidig = 0;
                veld.value = String(Math.max(0, huidig + delta));
                veld.dispatchEvent(new Event("input", { bubbles: true }));
                veld.dispatchEvent(new Event("change", { bubbles: true }));
            });
            return b;
        }

        veld.dataset.turf.split(",").forEach(function (stap) {
            var delen = stap.split(":");
            var aantal = parseInt(delen[0], 10);
            if (aantal > 0) groep.appendChild(knop("+" + aantal + (delen[1] ? " " + delen[1] : ""), aantal));
        });
        groep.appendChild(knop("\u22121", -1));
        veld.insertAdjacentElement("afterend", groep);
    });
});


// ---------- Barcodes scannen (keuken tellen en inboeken) ----------
// Dezelfde vaste vorm als barcodes.normaliseer op de server: alleen cijfers, een UPC-A van 12 cijfers met een 0 ervoor,
// een doos-code van 14 cijfers die met 0 begint zonder die 0. null als het geen getal is.
function barcodeNormaliseren(tekst) {
    var code = String(tekst || "").replace(/\s+/g, "");
    if (!/^\d+$/.test(code)) return null;
    if (code.length === 12) code = "0" + code;
    if (code.length === 14 && code.charAt(0) === "0") code = code.slice(1);
    return code;
}

// De camera als barcodescanner, waar de browser dat kan (BarcodeDetector: Chrome op Android). De knop blijft verborgen
// als het niet kan; wissel() zet de camera aan of uit, en opGevonden(code) krijgt de eerste barcode die hij ziet.
function cameraScanner(video, knop, opGevonden, opFout) {
    var detector = null, stream = null;
    if ("BarcodeDetector" in window) {
        BarcodeDetector.getSupportedFormats().then(function (formaten) {
            var nodig = ["ean_13", "ean_8", "upc_a", "itf"].filter(function (f) { return formaten.indexOf(f) >= 0; });
            if (!nodig.length) return;
            detector = new BarcodeDetector({ formats: nodig });
            knop.hidden = false;
        }).catch(function () {});
    }
    function stoppen() {
        if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
        stream = null;
        video.hidden = true;
    }
    function zoek() {
        if (!stream) return;
        detector.detect(video).then(function (codes) {
            if (codes.length) { stoppen(); opGevonden(codes[0].rawValue); }
            else setTimeout(zoek, 250);
        }).catch(function () { setTimeout(zoek, 500); });
    }
    return {
        wissel: function () {
            if (stream) { stoppen(); return; }
            navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (s) {
                stream = s;
                video.srcObject = s;
                video.hidden = false;
                video.play();
                zoek();
            }).catch(function () { if (opFout) opFout(); });
        }
    };
}
