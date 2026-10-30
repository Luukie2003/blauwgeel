/* Bewegende effecten over een dia op de kantine-tv (1.76.0, zie kiosk_momenten.EFFECTEN en kiosk_effecten.css).

   Elke dia met data-effect (en data-opties) krijgt bij het laden een laag met deeltjes die met CSS bewegen. De
   schijnwerper (templates/_kiosk_moment.html) gebruikt hetzelfde: KioskEffecten.maak(doel, effect, opties). Alles met
   transform en opacity, en een beperkt aantal deeltjes: licht genoeg voor de tv-kastjes.

   opties.prijs: [links, boven] in % van de dia, waar de gloed op de prijs klopt. Bij het programma: opties.rijen (de
   tijd van elke regel, van boven naar beneden), opties.boven/onder (het midden van de bovenste en onderste regel),
   hoogte, links en rechts (in %), en opties.momenten (de tijdsloten van de map, in ms): het tijdslot van nu licht op.
   Is het programma een griezeldia (1.77.0), dan staan de regels in de dia zelf (.gz-rij) en kleurt dit script ze. */
(function () {
    'use strict';

    var VLEERMUIS = '<svg viewBox="0 0 120 60"><path class="vl" d="M56 24L30 8Q18 6 4 16q8 6 8 14 6-5 10-4 4 4 8 10 4-7 10-6 4 4 8 8 3-6 8-6z"/>' +
        '<path class="vr" d="M64 24l26-16q12-2 26 8-8 6-8 14-6-5-10-4-4 4-8 10-4-7-10-6-4 4-8 8-3-6-8-6z"/>' +
        '<path d="M60 40c-5-2-6-10-5-16l-2-9 4 3 3-2 3 2 4-3-2 9c1 6 0 14-5 16z"/></svg>';
    var HEKS = '<svg viewBox="0 0 200 100"><path d="M30 60L4 47l7 13-11 6 13 4-7 12 26-13z"/><path d="M30 62l148-10 1 4-148 10z"/>' +
        '<path d="M92 58h26l-6-32q-8-6-14 0z"/><path d="M96 30q-24 4-36 18 20-2 34 2z"/><circle cx="108" cy="20" r="7"/>' +
        '<path d="M100 16l32-12-18 14z"/><path d="M96 18l28-4v3l-27 4z"/><path d="M112 56l28 4-2 4-28-3z"/></svg>';
    var SCHICHT = '<svg viewBox="0 0 64 200"><path d="M38 0L6 110h24L16 200l42-118H34L52 0z"/></svg>';
    var CONFETTI = ['#ffd23f', '#ff4fd8', '#9dff2e', '#4fc3ff', '#ff8a1f', '#ffffff'];

    function r(a, b) { return a + Math.random() * (b - a); }

    function deeltje(laag, klasse, stijl, html) {
        var el = document.createElement('i');
        el.className = klasse;
        el.setAttribute('style', stijl);
        if (html) el.innerHTML = html;
        laag.appendChild(el);
        return el;
    }

    // n deeltjes verspreid over gebied [links, rechts, boven, onder] (in %), elk met een eigen duur (s) en grootte;
    // met een negatieve vertraging staat alles meteen al in beweging.
    function veel(laag, n, klasse, gebied, duur, grootte, extra) {
        for (var i = 0; i < n; i++) {
            var d = r(duur[0], duur[1]);
            deeltje(laag, klasse,
                'left:' + r(gebied[0], gebied[1]).toFixed(1) + '%;top:' + r(gebied[2], gebied[3]).toFixed(1) + '%;' +
                '--s:' + r(grootte[0], grootte[1]).toFixed(2) + ';animation-duration:' + d.toFixed(2) + 's;' +
                'animation-delay:-' + r(0, d).toFixed(2) + 's;' + (extra ? extra() : ''));
        }
    }

    function zijwaarts() { return '--dx:' + r(-6, 6).toFixed(1) + ';'; }

    function vleermuizen(laag, n) {
        for (var i = 0; i < n; i++) {
            deeltje(laag, 'fx-vleermuis' + (i % 2 ? ' fx-vleermuis--terug' : ''),
                '--top:' + r(4, 34).toFixed(1) + 'vh;--maat:' + r(4, 7).toFixed(1) + 'vw;--d:' + r(22, 38).toFixed(1) + 's;' +
                '--w:' + (i * 7 + r(0, 4)).toFixed(1) + 's', VLEERMUIS);
        }
    }

    function prijs(laag, opties) {
        if (!opties || !opties.prijs) return;
        deeltje(laag, 'fx-prijs', 'left:' + opties.prijs[0] + '%;top:' + opties.prijs[1] + '%');
    }

    function bliksem(laag) {
        for (var i = 0; i < 2; i++) {
            var d = (r(8, 12)).toFixed(1) + 's', x = r(15, 85).toFixed(0);
            deeltje(laag, 'fx-flits', '--x:' + x + '%;--d:' + d + ';animation-delay:-' + r(0, 6).toFixed(1) + 's');
            deeltje(laag, 'fx-schicht', 'left:' + (x - 3) + '%;--d:' + d + ';animation-delay:-' + r(0, 6).toFixed(1) + 's', SCHICHT);
        }
    }

    function slijm(laag) {
        for (var i = 0; i < 9; i++) {
            var d = r(4.5, 7.5);
            deeltje(laag, 'fx-slijm', 'left:' + (i * 11.5 + r(0, 6)).toFixed(1) + '%;--s:' + r(0.6, 1.4).toFixed(2) + ';' +
                'animation-duration:' + d.toFixed(2) + 's;animation-delay:-' + r(0, d).toFixed(2) + 's');
        }
        veel(laag, 6, 'fx-drup', [3, 97, 6, 12], [3, 4.5], [0.8, 1.3]);
    }

    function confetti(laag) {
        // Om de 12 seconden een regen, alle snippers tegelijk (zie fx-confetti).
        var begin = r(0, 6);
        for (var i = 0; i < 34; i++) {
            deeltje(laag, 'fx-confetti',
                'left:' + r(0, 100).toFixed(1) + '%;--s:' + r(0.7, 1.4).toFixed(2) + ';--c:' + CONFETTI[i % CONFETTI.length] + ';' +
                '--dx:' + r(-8, 8).toFixed(1) + ';animation-delay:-' + (begin + r(0, 1.2)).toFixed(2) + 's');
        }
    }

    function kaarsen(laag) {
        [[3, 80], [7, 90], [93, 84], [96, 74], [30, 94], [70, 95]].forEach(function (plek) {
            deeltje(laag, 'fx-kaars', 'left:' + plek[0] + '%;top:' + plek[1] + '%;--s:' + r(0.8, 1.3).toFixed(2) + ';' +
                'animation-duration:' + r(1.8, 2.8).toFixed(2) + 's;animation-delay:-' + r(0, 2).toFixed(2) + 's');
        });
    }

    // Het programma: per regel een lijst eromheen die oplicht als het tijdslot van die regel nu is.
    function programma(laag, o) {
        var rijen = o.rijen || [];
        if (!rijen.length) return;
        var stap = rijen.length > 1 ? (o.onder - o.boven) / (rijen.length - 1) : 0;
        var lijsten = rijen.map(function (tijd, i) {
            return deeltje(laag, 'fx-rij',
                'left:' + o.links + '%;width:' + (o.rechts - o.links) + '%;top:' + (o.boven + i * stap).toFixed(2) + '%;' +
                '--h:' + o.hoogte + '%;height:' + o.hoogte + '%');
        });
        var tag = null;
        var uniek = [];
        rijen.forEach(function (tijd) { if (uniek.indexOf(tijd) < 0) uniek.push(tijd); });
        function bijwerken() {
            var nu = window.kioskNu ? window.kioskNu() : Date.now();
            var momenten = o.momenten || [];
            var huidige = null;
            for (var i = 0; i < momenten.length; i++) {
                if (momenten[i].van <= nu && nu < momenten[i].einde) huidige = i;
            }
            // Regels horen op volgorde bij de tijdsloten (zo klopt het ook als een moment is opgeschoven); zijn het er niet
            // evenveel, dan op de tijd zelf.
            var tijd = huidige === null ? null : (uniek.length === momenten.length ? uniek[huidige] : momenten[huidige].tijd);
            var eerste = null;
            lijsten.forEach(function (lijst, i) {
                var aan = tijd !== null && rijen[i] === tijd;
                lijst.className = 'fx-rij' + (aan ? ' fx-rij--nu' : '');
                if (aan && eerste === null) eerste = lijst;
            });
            if (tag && tag.parentNode) tag.parentNode.removeChild(tag);
            tag = null;
            if (eerste) {
                tag = document.createElement('i');
                tag.className = 'fx-nu';
                tag.textContent = 'NU';
                eerste.appendChild(tag);
            }
        }
        bijwerken();
        setInterval(bijwerken, 5000);
    }

    // Het programma als griezeldia: de regels (.gz-rij, met data-tijd) staan in de dia. Het tijdslot van nu licht op en
    // voorbije tijdsloten worden zachter; welke regel bij welk tijdslot hoort, gaat net als in programma() hierboven.
    function programmaLijst(lijst, o) {
        var rijen = Array.prototype.slice.call(lijst.querySelectorAll('.gz-rij'));
        var tijden = rijen.map(function (rij) { return rij.getAttribute('data-tijd'); });
        var uniek = [];
        tijden.forEach(function (tijd) { if (uniek.indexOf(tijd) < 0) uniek.push(tijd); });
        var klok = null;
        function bijwerken() {
            if (!document.body.contains(lijst)) { clearInterval(klok); return; }  // het voorbeeld is vervangen
            var nu = window.kioskNu ? window.kioskNu() : Date.now();
            var momenten = o.momenten || [];
            var stand = {};
            momenten.forEach(function (m, i) {
                var tijd = uniek.length === momenten.length ? uniek[i] : m.tijd;
                if (m.van <= nu && nu < m.einde) stand[tijd] = 'nu';
                else if (m.einde <= nu && stand[tijd] !== 'nu') stand[tijd] = 'geweest';
            });
            rijen.forEach(function (rij, i) {
                rij.classList.toggle('gz-rij--nu', stand[tijden[i]] === 'nu');
                rij.classList.toggle('gz-rij--geweest', stand[tijden[i]] === 'geweest');
            });
        }
        bijwerken();
        klok = setInterval(bijwerken, 5000);
    }

    var EFFECTEN = {
        heksenketel: function (laag, o) {
            veel(laag, 14, 'fx-bel', [4, 30, 66, 82], [3, 5.5], [0.6, 1.4]);
            veel(laag, 5, 'fx-damp', [0, 36, 58, 84], [8, 12], [0.8, 1.4]);
            veel(laag, 9, 'fx-drup', [24, 80, 26, 38], [2.6, 4.2], [0.7, 1.3]);
            prijs(laag, o);
            vleermuizen(laag, 2);
        },
        vuur: function (laag, o) {
            veel(laag, 4, 'fx-vlam', [34, 64, 78, 90], [0.7, 1.2], [0.8, 1.3]);
            veel(laag, 22, 'fx-vonk', [30, 68, 62, 86], [2.5, 4.5], [0.6, 1.4], zijwaarts);
            prijs(laag, o);
            vleermuizen(laag, 2);
        },
        toverglans: function (laag, o) {
            veel(laag, 22, 'fx-glitter', [10, 90, 36, 94], [1.8, 3.2], [0.5, 1.3]);
            veel(laag, 4, 'fx-damp', [8, 92, 70, 96], [9, 13], [0.9, 1.5]);
            deeltje(laag, 'fx-heks', 'animation-delay:-' + r(0, 8).toFixed(1) + 's', HEKS);
            prijs(laag, o);
            vleermuizen(laag, 1);
        },
        duivel: function (laag, o) {
            bliksem(laag);
            veel(laag, 18, 'fx-vonk', [0, 100, 78, 100], [3, 5], [0.6, 1.4], zijwaarts);
            veel(laag, 9, 'fx-drup', [22, 80, 28, 44], [2.4, 3.8], [0.8, 1.4]);
            prijs(laag, o);
            vleermuizen(laag, 2);
        },
        zombie: function (laag, o) {
            slijm(laag);
            veel(laag, 5, 'fx-damp', [0, 100, 72, 96], [9, 14], [0.9, 1.5]);
            confetti(laag);
            prijs(laag, o);
        },
        programma: function (laag, o) {
            vleermuizen(laag, 4);
            var lijst = laag.parentNode && laag.parentNode.querySelector('.gz-programma');
            if (lijst) {
                programmaLijst(lijst, o);
                return;
            }
            kaarsen(laag);
            programma(laag, o);
        }
    };

    window.KioskEffecten = {
        /* Een effectlaag in doel (een dia); geeft de laag, of null bij een onbekend effect. */
        maak: function (doel, effect, opties) {
            if (!doel || !EFFECTEN[effect]) return null;
            var laag = document.createElement('div');
            laag.className = 'fx fx--' + effect;
            laag.setAttribute('aria-hidden', 'true');
            doel.appendChild(laag);
            try { EFFECTEN[effect](laag, opties || {}); } catch (e) { /* een effect mag een dia nooit breken */ }
            return laag;
        }
    };

    function opties(el) {
        try { return JSON.parse(el.getAttribute('data-opties') || '{}'); } catch (e) { return {}; }
    }

    var dias = document.querySelectorAll('.scherm .slide[data-effect]');
    for (var i = 0; i < dias.length; i++) window.KioskEffecten.maak(dias[i], dias[i].getAttribute('data-effect'), opties(dias[i]));
})();
