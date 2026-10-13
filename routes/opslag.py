"""Beheer > Opslag: hoeveel schijfruimte de site gebruikt en wat het meeste inneemt."""

from flask import flash, redirect, render_template, request, url_for

from database import get_db
from opslag import (
    bewaar_quota_mb,
    groottetekst,
    lees_quota_mb,
    ongebruikte_videos,
    opslag_status,
    verwijder_ongebruikte_videos,
    video_gebruik,
)
from helpers import ffmpeg_beschikbaar


def register_routes(app):
    @app.route("/opslag", methods=["GET", "POST"])
    def opslag_pagina():
        db = get_db()
        if request.method == "POST":
            try:
                bewaar_quota_mb(db, int(request.form.get("quota_mb") or 0))
                flash("Opgeslagen.", "success")
            except ValueError:
                flash("Vul het aantal MB als getal in.", "error")
            return redirect(url_for("opslag_pagina"))
        return render_template("opslag.html")

    @app.route("/opslag/meting")
    def opslag_meting():
        """Het gemeten deel van de opslagpagina: alle bestanden langslopen duurt op de server enkele seconden, dus
        de pagina zelf haalt dit na het laden apart op (zie data-lazy-bron in gedeeld.js)."""
        db = get_db()
        status = opslag_status(db)
        gebruik = video_gebruik(db)
        grootste = []
        for f in status["grootste"]:
            video = gebruik.get(f["pad"].rsplit("/", 1)[-1]) if f["pad"].startswith("static/kiosk_videos/") else None
            grootste.append(dict(f, tekst=groottetekst(f["bytes"]), video=video))
        onbruikbaar = ongebruikte_videos(db)
        return render_template(
            "_opslag_meting.html",
            status=status,
            totaal_tekst=groottetekst(status["totaal"]),
            quota_mb=lees_quota_mb(db),
            onderdelen=[dict(o, tekst=groottetekst(o["bytes"])) for o in status["onderdelen"]],
            grootste=grootste,
            ongebruikte_videos=[(naam, groottetekst(g)) for naam, g in onbruikbaar],
            ongebruikt_tekst=groottetekst(sum(g for _, g in onbruikbaar)),
            ffmpeg_beschikbaar=ffmpeg_beschikbaar(),
        )

    @app.route("/opslag/video-opruimen", methods=["POST"])
    def opslag_video_opruimen():
        aantal, bytes_ = verwijder_ongebruikte_videos(get_db())
        if aantal:
            soort = "video" if aantal == 1 else "video's"
            flash(f"{aantal} ongebruikte {soort} verwijderd ({groottetekst(bytes_)} vrij).", "success")
        else:
            flash("Er waren geen ongebruikte video's.", "success")
        return redirect(url_for("opslag_pagina"))
