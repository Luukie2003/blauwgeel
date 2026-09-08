// Service worker: cachet alleen de "schil" (stijl, logo, offline-pagina) zodat
// een navigatie die mislukt door geen verbinding een nette melding toont
// i.p.v. de kale foutmelding van de browser. Bemoeit zich bewust NIET met
// POSTs (boekingen, tellingen e.d.) -- die moeten altijd echt de server
// bereiken of expliciet falen; het opnieuw-versturen bij geen verbinding
// gebeurt in JS met een lokale wachtrij (zie _gedeelde_script.html), niet
// hier. Cachet ook geen ingelogde pagina's: die zijn per gebruiker/sessie
// verschillend en zouden verouderd of verkeerd (andere gebruiker) kunnen
// worden getoond.
const CACHE_NAAM = "kantine-schil-v1";
const SCHIL_BESTANDEN = [
    "/static/style.css",
    "/static/logo.png",
    "/offline",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAAM).then((cache) => cache.addAll(SCHIL_BESTANDEN))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((namen) =>
            Promise.all(namen.filter((n) => n !== CACHE_NAAM).map((n) => caches.delete(n)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const { request } = event;
    if (request.method !== "GET") return;

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() => caches.match("/offline"))
        );
        return;
    }

    if (SCHIL_BESTANDEN.some((pad) => request.url.endsWith(pad))) {
        event.respondWith(
            caches.match(request).then((cached) => cached || fetch(request))
        );
    }
});
