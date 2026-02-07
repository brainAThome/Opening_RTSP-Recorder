# Ring Kamera - Amazon Datenfluss Analyse

**Datum:** 06. Februar 2026  
**Status:** Dokumentiert  
**Projekt:** RTSP Recorder - Lokale Aufnahme ohne Cloud-Abhängigkeit

---

## 📋 Übersicht

Diese Dokumentation beschreibt, wie Ring-Kameras Daten an Amazon senden, welche Daten fließen, und wie wir versucht haben, den Datenfluss zu kontrollieren.

---

## ⚠️ WICHTIG: Ring Premium Abo

| Abo-Status | Video-Speicherung in Cloud | Handlungsbedarf |
|------------|---------------------------|-----------------|
| **Kein Premium** | ❌ Keine Videos gespeichert | Nur Snapshots werden übertragen |
| **Mit Premium** | ✅ Alle Videos gespeichert | **Video-Speicherung muss manuell deaktiviert werden!** |

### Videospeicherung deaktivieren (bei Premium-Abo)

1. Ring App öffnen → Gerät auswählen
2. Geräteeinstellungen → Videoeinstellungen
3. **"Videoaufnahme"** oder **"Video speichern"** → **AUS**
4. Alternativ: Ring Dashboard (ring.com) → Geräte → Einstellungen

> ⚠️ **Ohne diese Einstellung werden bei Premium-Abo ALLE Bewegungsvideos in der Amazon Cloud gespeichert!**

---

## 🔄 Datenfluss-Diagramm

```
                              ┌─────────────────────────────────────┐
                              │         RING KAMERA                 │
                              │         (Haustür)                   │
                              └──────────────┬──────────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     │                       │                       │
                     ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │   RING APP       │    │   RING WEBSEITE  │    │   RTSP STREAM    │
          │   öffnet         │    │   ring.com       │    │   (lokal)        │
          └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                   │                       │                       │
                   ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  Snapshot wird   │    │  Snapshot wird   │    │  Kein Daten-     │
          │  von Kamera      │    │  von Kamera      │    │  transfer zu     │
          │  abgerufen       │    │  abgerufen       │    │  Amazon          │
          └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                   │                       │                       │
                   ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  Über ring.com   │    │  Über Amazon     │    │  Lokale          │
          │  API             │    │  CDN (direkt)    │    │  Speicherung     │
          └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                   │                       │                       │
                   ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  ✅ BLOCKIERBAR  │    │  ❌ NICHT        │    │  ✅ KOMPLETT     │
          │  mit Pi-hole     │    │  BLOCKIERBAR     │    │  LOKAL           │
          │  (ring.com)      │    │  (amazonaws.com) │    │  (Home Assistant)│
          └──────────────────┘    └──────────────────┘    └──────────────────┘
```

### Legende

| Pfad | Beschreibung | Blockierbar? |
|------|--------------|--------------|
| **Ring App** | App fragt Snapshot über ring.com API ab | ✅ Ja (Pi-hole blockiert ring.com) |
| **Ring Webseite** | Browser fragt Snapshot über Amazon CDN ab | ❌ Nein (amazonaws.com nicht blockierbar) |
| **RTSP Stream** | Lokaler Videostream ohne Cloud | ✅ Nicht nötig (kein Cloud-Traffic) |

---

## 📊 Welche Daten fließen zu Amazon?

### Datentypen und Trigger

| Datentyp | Trigger | Ziel | Blockierbar | Anmerkung |
|----------|---------|------|-------------|-----------|
| **Live-Snapshots (App)** | Ring App öffnen | Amazon Cloud | ✅ Ja (Pi-hole) | Kamera wird über ring.com API angefragt |
| **Live-Snapshots (Web)** | ring.com öffnen | Amazon Cloud | ❌ Nein | Kamera wird über Amazon CDN angefragt |
| **Event-Snapshots** | Bewegung erkannt | Amazon Cloud | ✅ Ja (Pi-hole) | Nur Thumbnail, kein Video |
| **Video-Clips** | Nur mit Premium-Abo | Amazon Cloud | ✅ Ja (Pi-hole) | **Ohne Premium: Keine Videos gespeichert!** |
| **Telemetrie** | Kontinuierlich | Amazon Analytics | ✅ Teilweise | Geräte-Status, Batterielevel etc. |

### ⚠️ Wichtig: Video-Speicherung

```
┌─────────────────────────────────────────────────────────────────┐
│                    VIDEO-SPEICHERUNG IN CLOUD                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  OHNE Premium-Abo:                                             │
│  ├── Keine Videos werden in Cloud gespeichert                 │
│  ├── Nur Live-Snapshots bei App/Web-Öffnung                   │
│  └── Event-Benachrichtigungen ohne Videoclip                  │
│                                                                 │
│  MIT Premium-Abo (Protect Plan):                               │
│  ├── ALLE Bewegungsvideos werden gespeichert                  │
│  ├── 30-60 Tage Cloud-Speicherung                             │
│  └── ⚠️ MUSS MANUELL DEAKTIVIERT WERDEN!                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Detaillierte Erklärung

#### 1. Live-Snapshots via Ring App (BLOCKIERBAR ✅)

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Ring App    │────▶│  ring.com       │────▶│  Ring Kamera     │
│  geöffnet    │     │  API Request    │     │  sendet Snapshot │
└──────────────┘     └─────────────────┘     └──────────────────┘
                              │
                              │ Pi-hole blockiert ring.com
                              ▼
                     ┌─────────────────┐
                     │  🚫 BLOCKIERT   │
                     │  Kein Snapshot  │
                     │  zu Amazon      │
                     └─────────────────┘
```

**Verhalten:**
- App sendet Request an ring.com API
- ring.com kontaktiert die Kamera
- Kamera sendet Snapshot zurück
- **Pi-hole blockiert ring.com → Kein Snapshot möglich**

#### 2. Live-Snapshots via Webseite (NICHT BLOCKIERBAR ❌)

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Browser     │────▶│  ring.com       │────▶│  Ring Kamera     │
│  öffnet      │     │  Webseite       │     │  sendet Snapshot │
│  ring.com    │     │                 │     │                  │
└──────────────┘     └─────────────────┘     └──────────────────┘
                              │
                              │ Snapshot-Abruf über Amazon CDN
                              ▼
                     ┌─────────────────────────────────────┐
                     │  amazonaws.com / cloudfront.net     │
                     │  ❌ Nicht blockierbar ohne andere   │
                     │  Amazon-Dienste zu brechen          │
                     └─────────────────────────────────────┘
```

**Problem:**
- Die Webseite ruft Snapshots über Amazon-Infrastruktur ab
- Dieselben Domains werden für Amazon Shopping, Prime Video, AWS etc. genutzt
- **Blockieren würde alle Amazon-Dienste brechen**
- Die Kamera liefert den Snapshot direkt an Amazon CDN

---

## 🛡️ Pi-hole Blocking Ergebnisse

### Blockierte Domains (erfolgreich)

| Domain | Zweck | Auswirkung wenn blockiert |
|--------|-------|---------------------------|
| `*.ring.com` | Ring Cloud API | ✅ App funktioniert nicht |
| `app-snips.ring.com` | Snapshot-Uploads | ✅ Keine Snapshots zu Cloud |
| `prod-snips.ring.com` | Produktions-Snapshots | ✅ Keine Snapshots zu Cloud |
| `fw.ring.com` | Firmware Updates | ⚠️ Keine Updates mehr |
| `api.ring.com` | Haupt-API | ✅ App komplett blockiert |
| `oauth.ring.com` | Authentifizierung | ✅ Login nicht möglich |
| `nw.ring.com` | Netzwerk-Services | ✅ Kein Cloud-Zugriff |

### Nicht blockierbare Domains

| Domain | Grund | Problem |
|--------|-------|---------|
| `*.amazonaws.com` | AWS Services | Würde viele andere Dienste brechen |
| `*.cloudfront.net` | Amazon CDN | Wird von vielen Webseiten genutzt |
| `*.amazon.com` | Amazon allgemein | Würde Shopping etc. blockieren |

### Pi-hole Konfiguration

```
# /etc/pihole/custom.list oder über Admin-Interface

# Ring komplett blockieren
0.0.0.0 ring.com
0.0.0.0 app-snips.ring.com
0.0.0.0 prod-snips.ring.com
0.0.0.0 api.ring.com
0.0.0.0 oauth.ring.com
0.0.0.0 fw.ring.com
0.0.0.0 nw.ring.com
0.0.0.0 account.ring.com
0.0.0.0 app.ring.com
0.0.0.0 pki.ring.com
0.0.0.0 rings.solutions
0.0.0.0 *.rings.solutions
```

---

## 📈 Datenfluss-Szenarien

### Szenario 1: Normale Nutzung (ohne Blocking)

```
┌────────────────────────────────────────────────────────────────┐
│                    OHNE PI-HOLE BLOCKING                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. App öffnen ──────▶ Snapshot zu Amazon ──────▶ 📤 GESENDET │
│                                                                │
│  2. Bewegung ────────▶ Event zu Amazon ─────────▶ 📤 GESENDET │
│                                                                │
│  3. Video abrufen ───▶ Stream von Amazon ───────▶ 📤 GESENDET │
│                                                                │
│  4. Webseite ────────▶ Snapshot über CDN ───────▶ 📤 GESENDET │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Szenario 2: Mit Pi-hole Blocking (Ring-Domains)

```
┌────────────────────────────────────────────────────────────────┐
│                    MIT PI-HOLE BLOCKING                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. App öffnen ──────▶ DNS blockiert ───────────▶ 🚫 BLOCKIERT│
│                                                                │
│  2. Bewegung ────────▶ API nicht erreichbar ────▶ 🚫 BLOCKIERT│
│                                                                │
│  3. Video abrufen ───▶ Cloud nicht erreichbar ──▶ 🚫 BLOCKIERT│
│                                                                │
│  4. Webseite ────────▶ CDN nicht blockierbar ───▶ 📤 GESENDET │
│                           (amazonaws.com)                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Szenario 3: RTSP Recorder (komplett lokal)

```
┌────────────────────────────────────────────────────────────────┐
│                    MIT RTSP RECORDER                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Ring Kamera ─────────────────────────────────────────────────│
│       │                                                        │
│       │ RTSP Stream (lokal, Port 8554)                        │
│       ▼                                                        │
│  ┌─────────────────┐                                          │
│  │ Home Assistant  │                                          │
│  │ RTSP Recorder   │ ◀── Keine Cloud-Verbindung nötig         │
│  └─────────────────┘                                          │
│       │                                                        │
│       │ Lokale Speicherung                                    │
│       ▼                                                        │
│  ┌─────────────────┐                                          │
│  │ /media/rtsp/    │ ◀── Alle Daten bleiben lokal             │
│  │ recordings/     │                                          │
│  └─────────────────┘                                          │
│                                                                │
│  📍 Zu Amazon gesendet: NICHTS (0 Bytes)                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Technische Details

### Ring Snapshot-Mechanismus

```python
# Vereinfachte Darstellung des Ring-Snapshot-Prozesses

class RingCamera:
    def on_app_opened(self):
        """Wird getriggert wenn Ring App geöffnet wird"""
        # 1. Ring App sendet API-Request an ring.com
        # 2. Ring Cloud sendet Anfrage an Kamera
        # 3. Kamera nimmt aktuellen Frame auf
        # 4. Frame wird zu Amazon Cloud hochgeladen
        # 5. App zeigt Snapshot an
        
        snapshot = self.capture_current_frame()
        self.upload_to_cloud(snapshot)  # <-- DAS wollen wir verhindern
        
    def on_motion_detected(self):
        """Wird bei Bewegungserkennung getriggert"""
        # Event wird an Ring Cloud gesendet
        # Cloud entscheidet ob Recording starten soll
        
        event = self.create_motion_event()
        self.send_to_cloud(event)  # <-- Auch das wird blockiert
```

### RTSP Stream (lokal)

```python
# RTSP Recorder - Lokale Alternative

class RTSPRecorder:
    def on_motion_detected(self):
        """Lokale Bewegungserkennung"""
        # 1. Motion Sensor triggert (binary_sensor)
        # 2. RTSP Stream wird lokal aufgezeichnet
        # 3. Keine Cloud-Verbindung nötig
        
        self.start_local_recording()  # <-- Komplett lokal
        
    def get_rtsp_url(self):
        """Lokaler RTSP Stream"""
        # Ring Kameras bieten RTSP über ring-mqtt an
        return "rtsp://192.168.178.x:8554/ring_haustuer"
```

---

## 📋 Zusammenfassung

### Premium-Abo Status

| Abo | Video-Speicherung | Snapshots bei App | Snapshots bei Webseite |
|-----|-------------------|-------------------|------------------------|
| **Ohne Premium** | ❌ Keine Videos in Cloud | ✅ Ja (blockierbar) | ✅ Ja (nicht blockierbar) |
| **Mit Premium** | ⚠️ ALLE Videos in Cloud | ✅ Ja (blockierbar) | ✅ Ja (nicht blockierbar) |

> ⚠️ **Mit Premium-Abo: Videospeicherung manuell deaktivieren!**

### App vs Webseite - Der entscheidende Unterschied

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  RING APP (blockierbar mit Pi-hole)                            │
│  ├── Ruft Snapshots über ring.com API ab                       │
│  ├── Pi-hole blockiert ring.com → Kein Snapshot                │
│  └── ✅ EMPFOHLEN: Ring App nicht nutzen                       │
│                                                                 │
│  RING WEBSEITE (NICHT blockierbar)                             │
│  ├── Ruft Snapshots über Amazon CDN ab                         │
│  ├── amazonaws.com nicht blockierbar                           │
│  └── ❌ Bei Webseiten-Nutzung: Snapshot fließt zu Amazon       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Was wird blockiert (mit Pi-hole)

| Aktion | Status | Ergebnis |
|--------|--------|----------|
| Ring App öffnen | 🚫 Blockiert | App zeigt Fehler, **kein Snapshot** |
| Bewegungs-Events | 🚫 Blockiert | Keine Push-Benachrichtigungen |
| Cloud-Video-Abruf | 🚫 Blockiert | Keine Cloud-Wiedergabe |
| Firmware-Updates | 🚫 Blockiert | Kamera bleibt auf alter Version |

### Was NICHT blockiert werden kann

| Aktion | Status | Grund |
|--------|--------|-------|
| ring.com Webseite öffnen | ⚠️ Nicht blockierbar | Nutzt Amazon CDN (amazonaws.com) |
| Snapshots über Webseite | ⚠️ Nicht blockierbar | Kamera liefert direkt an Amazon CDN |

### Empfehlung: RTSP Recorder

| Aspekt | Ring Cloud | RTSP Recorder |
|--------|------------|---------------|
| Daten an Amazon | ✅ Ja (bei App/Web-Nutzung) | ❌ Nein (komplett lokal) |
| Video-Speicherung | Nur mit Premium (Cloud) | ✅ Lokal (unbegrenzt) |
| Pi-hole Blocking | ⚠️ Nur für App, nicht Web | Nicht nötig |
| Datenschutz | ❌ Fragwürdig | ✅ Vollständig |
| Internetausfall | ❌ Keine Funktion | ✅ Weiterhin aktiv |

---

## 🎯 Fazit

### Die wichtigsten Erkenntnisse

1. **Ohne Premium-Abo:** Ring speichert **keine Videos** in der Cloud - nur Snapshots bei App/Web-Nutzung
2. **Mit Premium-Abo:** Alle Videos werden gespeichert → **Videospeicherung manuell deaktivieren!**
3. **Ring App blockierbar:** Pi-hole blockiert ring.com → Keine Snapshots bei App-Öffnung
4. **Ring Webseite NICHT blockierbar:** Snapshots werden über Amazon CDN abgerufen
5. **RTSP Recorder:** Komplett lokale Aufnahme ohne jeglichen Cloud-Verkehr

### Handlungsempfehlung

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMPFOHLENE KONFIGURATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. ✅ RTSP Recorder installieren (lokale Aufnahmen)           │
│                                                                 │
│  2. ✅ Pi-hole: ring.com blockieren (verhindert App-Snapshots) │
│                                                                 │
│  3. ⚠️ Ring Webseite (ring.com) NICHT im Browser öffnen        │
│     → Snapshots werden sonst zu Amazon gesendet                │
│                                                                 │
│  4. ⚠️ Bei Premium-Abo: Videospeicherung in Ring App AUS       │
│                                                                 │
│  5. ✅ Benachrichtigungen über Home Assistant statt Ring App   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📚 Weitere Dokumentation

- [RTSP Recorder README](../README.md)
- [HANDOVER_v1.2.2.md](../HANDOVER_v1.2.2.md)
- [AGENT_PROMPT_v1.2.2.md](../AGENT_PROMPT_v1.2.2.md)

---

**Erstellt:** 07. Februar 2026  
**Autor:** RTSP Recorder Projekt
