# 💰 Cloud-Abo-Kosten vs. Lokale Aufzeichnung

> **RTSP Recorder = 0€/Jahr** - Keine Abos, keine Cloud, vollständige Privatsphäre!

## Warum lokale Aufzeichnung?

Viele beliebte Smart-Home-Kameras erfordern **kostenpflichtige Cloud-Abonnements** um wichtige Funktionen freizuschalten:
- Videoaufzeichnung und Wiedergabe
- 24/7 Daueraufzeichnung
- Erweiterte Video-Historie (30-180 Tage)
- Personen-/Paketerkennung
- Unterstützung mehrerer Standorte

**Mit RTSP Recorder erhalten Sie all das KOSTENLOS:**
- ✅ Lokale Videoaufzeichnung (keine Cloud erforderlich)
- ✅ KI-gestützte Personenerkennung (via Coral TPU)
- ✅ Gesichtserkennung mit lokaler Datenbank
- ✅ Unbegrenzte Video-Historie (nur durch Speicherplatz begrenzt)
- ✅ Vollständige Privatsphäre - Daten verlassen nie Ihr Netzwerk

---

## Vergleich der Cloud-Abo-Kosten (2026)

### Ring (Amazon)

| Tarif | Monatlich | Jährlich | Abdeckung | Funktionen |
|-------|-----------|----------|-----------|------------|
| **Basic** | 3,99€ | 39,99€ | 1 Gerät | 180 Tage Historie, Personen-Benachrichtigungen |
| **Standard** | 9,99€ | 99,99€ | Alle Geräte, 1 Standort | + Türklingel-Anrufe, erweitertes Live-Video |
| **Premium** | 19,99€ | **199,99€** | Alle Geräte, 1 Standort | + 24/7 Aufzeichnung, kontinuierliches Live-Video |

> ⚠️ **Preise pro Standort!** Mehrere Häuser = mehrere Abonnements

### Google Nest (Home Premium)

| Tarif | Monatlich | Jährlich | Funktionen |
|-------|-----------|----------|------------|
| **Standard** | ~6€ | ~60€ | 30 Tage Ereignis-Historie |
| **Premium** | ~12€ | ~120€ | 60 Tage Ereignisse + 10 Tage 24/7 |

### Arlo

| Tarif | Monatlich | Jährlich | Funktionen |
|-------|-----------|----------|------------|
| **Secure** | 2,99€ | 29,99€ | 1 Kamera, 30 Tage |
| **Secure Plus** | 9,99€ | 99,99€ | Unbegrenzte Kameras, 30 Tage |
| **Safe & Secure Pro** | 14,99€ | 149,99€ | + 24/7 Notfallreaktion |

### Blink (Amazon)

| Tarif | Monatlich | Jährlich | Abdeckung |
|-------|-----------|----------|-----------|
| **Basic** | 3€ | 30€ | Pro Gerät |
| **Plus** | 10€ | 100€ | Unbegrenzte Geräte |

### Wyze

| Tarif | Monatlich | Jährlich | Funktionen |
|-------|-----------|----------|------------|
| **Cam Plus** | $1,99 | $19,99 | Pro Kamera, Personenerkennung |
| **Cam Plus Pro** | $3,99 | $39,99 | + 24/7 Aufzeichnung |

### eufy (Anker)

| Tarif | Monatlich | Jährlich | Funktionen |
|-------|-----------|----------|------------|
| **Keiner erforderlich!** | 0€ | 0€ | Lokale Speicherung auf HomeBase |

> ✅ eufy ist eine der wenigen Marken mit **lokaler Speicherung standardmäßig**

---

## Ihre Ersparnis mit RTSP Recorder

### Einzelkamera-Haushalt

| Szenario | Cloud-Kosten/Jahr | Mit RTSP Recorder | **Jährliche Ersparnis** |
|----------|-------------------|-------------------|-------------------------|
| Ring Basic | 40€ | 0€ | **40€** |
| Ring Standard | 100€ | 0€ | **100€** |
| Ring Premium | 200€ | 0€ | **200€** |

### Multi-Kamera-Haushalt (3 Kameras)

| Szenario | Cloud-Kosten/Jahr | Mit RTSP Recorder | **Jährliche Ersparnis** |
|----------|-------------------|-------------------|-------------------------|
| 3x Ring Basic | 120€ | 0€ | **120€** |
| Ring Standard | 100€ | 0€ | **100€** |
| Arlo Secure Plus | 100€ | 0€ | **100€** |

### Langfristige Ersparnis

| Zeitraum | Ring Premium | Mit RTSP Recorder | **Gesamtersparnis** |
|----------|--------------|-------------------|---------------------|
| 1 Jahr | 200€ | 0€ | **200€** |
| 3 Jahre | 600€ | 0€ | **600€** |
| 5 Jahre | 1.000€ | 0€ | **1.000€** |
| 10 Jahre | 2.000€ | 0€ | **2.000€** |

---

## Empfohlene Home Assistant Integrationen

Um RTSP Recorder zu nutzen, müssen Ihre Kameras einen RTSP-Stream bereitstellen. So erhalten Sie RTSP von beliebten Kamerasystemen:

### Native RTSP-Unterstützung (Empfohlen)

Diese Kameras unterstützen RTSP direkt:

| Kamerasystem | Home Assistant Integration | Hinweise |
|--------------|---------------------------|----------|
| **Reolink** | [reolink](https://www.home-assistant.io/integrations/reolink/) | Ausgezeichnete RTSP-Unterstützung |
| **Tapo (TP-Link)** | [tapo](https://www.home-assistant.io/integrations/tapo/) | Natives RTSP |
| **UniFi Protect** | [unifiprotect](https://www.home-assistant.io/integrations/unifiprotect/) | Professionelle Qualität |
| **eufy** | [eufy_security](https://github.com/fuatakgun/eufy_security) | HACS Integration |
| **Amcrest** | [amcrest](https://www.home-assistant.io/integrations/amcrest/) | Natives RTSP |
| **Dahua** | Manuelle RTSP-URL | Natives RTSP |
| **Hikvision** | Manuelle RTSP-URL | Natives RTSP |

### RTSP via Bridge/Gateway

Diese Kameras benötigen zusätzliche Software für RTSP:

| Kamerasystem | Lösung | Hinweise |
|--------------|--------|----------|
| **Ring** | [ring-mqtt](https://github.com/tsightler/ring-mqtt) | HA Add-on, stellt RTSP-Gateway bereit |
| **Wyze** | [docker-wyze-bridge](https://github.com/mrlt8/docker-wyze-bridge) | Docker Container |
| **Nest** | Nicht unterstützt | Kein RTSP verfügbar |
| **Blink** | Eingeschränkt | Nur experimentelle Lösungen |

---

## Ring Kamera Einrichtungsanleitung

### Schritt 1: ring-mqtt Add-on installieren

1. Gehe zu **Einstellungen → Add-ons → Add-on Store**
2. Suche nach **ring-mqtt**
3. Klicke **Installieren**
4. Konfiguriere mit deinen Ring-Zugangsdaten
5. Starte das Add-on

### Schritt 2: RTSP-Stream-URL abrufen

Nachdem ring-mqtt läuft, sind deine Kameras verfügbar unter:
```
rtsp://homeassistant.local:8554/ring_kamera_name
```

### Schritt 3: Zu RTSP Recorder hinzufügen

1. Öffne die RTSP Recorder Konfiguration
2. Füge eine neue Kamera mit der RTSP-URL von ring-mqtt hinzu
3. Konfiguriere die Aufnahmeeinstellungen
4. Starte die Aufzeichnung!

> ⚠️ **Wichtig:** Der RTSP-Stream von ring-mqtt läuft weiterhin über Rings Cloud-Server. Jedoch werden deine **Aufnahmen lokal gespeichert** auf deinem Home Assistant Server, nicht in Amazons Cloud. Das bedeutet:
> - ✅ Kein Abo für Video-Speicherung erforderlich
> - ✅ Unbegrenzte Video-Historie
> - ✅ Deine Aufnahmen bleiben privat
> - ⚠️ Live-Stream benötigt weiterhin Internet (Ring Cloud)

---

## Datenschutz-Vergleich

| Funktion | Cloud-Abonnement | RTSP Recorder |
|----------|------------------|---------------|
| **Video-Speicherung** | Cloud (Server des Anbieters) | Lokal (dein Server) |
| **Datenzugriff** | Anbieter + ggf. Behörden | Nur du |
| **Internet erforderlich** | Ja, für alle Funktionen | Nur für Live-Stream |
| **Abo-Kosten** | 40-200€/Jahr | 0€ |
| **Video-Historie** | Begrenzt (30-180 Tage) | Unbegrenzt |
| **Datenschutz** | Unterliegt den AGB des Anbieters | Volle Kontrolle |
| **Gesichtserkennung** | Cloud-basiert (falls verfügbar) | Lokal, privat |

---

## Fazit

RTSP Recorder ermöglicht dir:

1. **100-200€+ pro Jahr sparen** an Cloud-Abonnements
2. **Deine Videodaten privat halten** - keine Cloud-Speicherung
3. **Unbegrenzte Video-Historie genießen** - nur durch Speicherplatz begrenzt
4. **KI-Funktionen lokal nutzen** - Personenerkennung, Gesichtserkennung
5. **Vollständige Kontrolle behalten** über deine Überwachungsdaten

**Starte noch heute mit dem Sparen - wechsle zur lokalen Aufzeichnung mit RTSP Recorder!**

---

*Zuletzt aktualisiert: Februar 2026*
*Preise können je nach Region variieren. Aktuelle Preise auf den Anbieter-Websites prüfen.*
