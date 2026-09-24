#!/usr/bin/env python3
"""
Tägliche Wetter-Zusammenfassung für Neuzeug (Sierning, OÖ) mit Kleidungstipp
für Kinder. Datenquelle: Open-Meteo (kostenlos, kein API-Key nötig).

Versand (eine Variante wählen, per Umgebungsvariable):
  NTFY_TOPIC                       -> Push aufs Handy über die ntfy-App (am einfachsten)
  TELEGRAM_TOKEN + TELEGRAM_CHAT   -> Nachricht über einen Telegram-Bot

Testlauf ohne Versand:  python3 wetter_neuzeug.py --print
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

ORT = "Neuzeug"
LAT, LON = 47.95, 14.31          # ungefähre Koordinaten von Neuzeug
START_H, END_H = 7, 16           # Zeitraum, der für die Kinder relevant ist
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

SCHNEE_CODES = {71, 73, 75, 77, 85, 86}
REGEN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def hole_wetter():
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": ("temperature_2m,apparent_temperature,precipitation_probability,"
                   "precipitation,weather_code,wind_gusts_10m,uv_index"),
        "timezone": "Europe/Vienna",
        "forecast_days": 1,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    letzter_fehler = None
    for versuch in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # Netzwerk kann morgens kurz hängen
            letzter_fehler = e
            time.sleep(10)
    raise RuntimeError(f"Wetterdaten nicht abrufbar: {letzter_fehler}")


def kleidung(gefuehlt_morgens, gefuehlt_max, regen, schnee, boeen, uv):
    t = gefuehlt_morgens
    if t < -5:
        tipps = ["Winteroverall/Skianzug", "Thermounterwäsche", "Mütze, Schal, warme Handschuhe",
                 "Winterstiefel"]
    elif t < 2:
        tipps = ["Winterjacke", "Mütze, Schal, Handschuhe", "Warme Schuhe, dicke Socken"]
    elif t < 8:
        tipps = ["Warme Jacke", "Mütze und dünne Handschuhe", "Lange Hose, festes Schuhwerk"]
    elif t < 14:
        tipps = ["Leichte Jacke oder Fleece", "Lange Hose", "Geschlossene Schuhe"]
    elif t < 19:
        tipps = ["Langarmshirt oder Pulli", "Dünne Jacke einpacken", "Lange Hose"]
    elif t < 24:
        tipps = ["T-Shirt, kurze oder dünne Hose", "Dünne Jacke im Rucksack"]
    else:
        tipps = ["Luftige, leichte Kleidung", "Viel trinken"]

    if gefuehlt_max - gefuehlt_morgens >= 8:
        tipps.append("Zwiebellook: wird tagsüber deutlich wärmer, Schichten zum Ausziehen")
    if schnee:
        tipps.append("Wasserdichte Schuhe/Handschuhe (Schnee)")
    if regen:
        tipps.append("Regenjacke, ggf. Matschhose und Gummistiefel")
    if boeen >= 40:
        tipps.append("Windfeste Jacke (starke Böen)")
    if uv >= 5:
        tipps.append("Sonnencreme und Kappe/Sonnenhut")
    return tipps


def baue_nachricht(daten):
    h = daten["hourly"]
    zeitraum = range(START_H, END_H + 1)

    def werte(key):
        return [h[key][i] if h[key][i] is not None else 0 for i in zeitraum]

    temp = werte("temperature_2m")
    gef = werte("apparent_temperature")
    prob = werte("precipitation_probability")
    niederschlag = werte("precipitation")
    codes = werte("weather_code")
    boeen = werte("wind_gusts_10m")
    uv = werte("uv_index")

    mittag = min(len(temp) - 1, 13 - START_H)
    summe_regen = sum(niederschlag)
    schnee = any(int(c) in SCHNEE_CODES for c in codes)
    regen = schnee or any(int(c) in REGEN_CODES for c in codes) \
        or max(prob) >= 50 or summe_regen >= 1.0

    jetzt = datetime.now()
    zeilen = [
        f"Wetter {ORT} – {TAGE[jetzt.weekday()]} {jetzt:%d.%m.}",
        f"🌡 {START_H}:00 Uhr: {temp[0]:.0f}° (gefühlt {gef[0]:.0f}°)",
        f"🌡 Mittag: {temp[mittag]:.0f}° (gefühlt {gef[mittag]:.0f}°)",
        f"↕ Tief/Hoch: {min(temp):.0f}° / {max(temp):.0f}°",
    ]
    if regen:
        art = "Schnee" if schnee else "Regen"
        zeilen.append(f"🌧 {art}: bis {max(prob):.0f} % Wahrsch., {summe_regen:.1f} mm")
    else:
        zeilen.append("☀ Trocken")
    if max(boeen) >= 30:
        zeilen.append(f"💨 Böen bis {max(boeen):.0f} km/h")
    if max(uv) >= 3:
        zeilen.append(f"🕶 UV-Index bis {max(uv):.0f}")

    zeilen.append("")
    zeilen.append("👕 Anziehen:")
    for tipp in kleidung(gef[0], max(gef), regen, schnee, max(boeen), max(uv)):
        zeilen.append(f"• {tipp}")
    return "\n".join(zeilen)


def sende_ntfy(topic, text):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=text.encode("utf-8"),
        headers={"Title": f"Wetter {ORT}", "Tags": "sunrise"},
    )
    urllib.request.urlopen(req, timeout=20).read()


def sende_telegram(token, chat, text):
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20
    ).read()


def main():
    nachricht = baue_nachricht(hole_wetter())

    if "--print" in sys.argv:
        print(nachricht)
        return

    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT")
    topic = os.getenv("NTFY_TOPIC")
    if token and chat:
        sende_telegram(token, chat, nachricht)
    elif topic:
        sende_ntfy(topic, nachricht)
    else:
        sys.exit("Kein Versandweg konfiguriert (NTFY_TOPIC oder TELEGRAM_TOKEN/TELEGRAM_CHAT setzen).")


if __name__ == "__main__":
    main()
