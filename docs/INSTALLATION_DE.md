# 🚀 RTSP Recorder - Installationsanleitung

> 🇬🇧 **[English Version](INSTALLATION.md)**

**Version:** 1.2.5  
**Letzte Aktualisierung:** 07. Februar 2026

---

## Inhaltsverzeichnis

1. [Systemanforderungen](#1-systemanforderungen)
2. [Installation via HACS](#2-installation-via-hacs)
3. [Manuelle Installation](#3-manuelle-installation)
4. [Detector Add-on Setup](#4-detector-add-on-setup)
5. [Coral USB Einrichtung](#5-coral-usb-einrichtung)
6. [Erste Konfiguration](#6-erste-konfiguration)
7. [Dashboard einrichten](#7-dashboard-einrichten)
8. [Verifizierung](#8-verifizierung)

---

## 1. Systemanforderungen

### Minimum

| Komponente | Anforderung |
|------------|-------------|
| Home Assistant | 2024.1+ |
| Python | 3.11+ |
| Speicher | 50 GB frei |
| RAM | 2 GB verfügbar |

### Empfohlen

| Komponente | Empfehlung |
|------------|------------|
| Home Assistant | 2024.12+ |
| Speicher | 200+ GB SSD |
| RAM | 4+ GB verfügbar |
| Hardware | Google Coral USB Accelerator |

### Unterstützte Kameras

- ✅ Jede RTSP-fähige IP-Kamera
- ✅ Home Assistant Camera Entities
- ✅ Ring Doorbell (via ring-mqtt Add-on)
- ✅ Frigate Cameras
- ✅ Generic Cameras (MJPEG, HLS)

---

## 2. Installation via HACS

### Schritt 1: Custom Repository hinzufügen

1. Öffne **HACS** in der Home Assistant Seitenleiste
2. Klicke auf das **⋮** (Drei-Punkte-Menü) oben rechts
3. Wähle **Custom repositories**
4. Im Popup-Fenster:
   - **Repository:** `https://github.com/brainAThome/Opening_RTSP-Recorder`
   - **Category:** Wähle **Integration** aus dem Dropdown
5. Klicke **Add**
6. Schließe das Popup

### Schritt 2: Integration installieren

1. In HACS, klicke **+ Explore & Download Repositories** (unten rechts)
2. Suche nach "**RTSP Recorder**"
3. Klicke auf das Ergebnis **"Opening RTSP Recorder"**
4. Klicke **Download** (unten rechts)
5. Wähle die neueste Version
6. Klicke erneut **Download** zur Bestätigung

### Schritt 3: Home Assistant neustarten

**Wichtig: Neustart ist erforderlich!**

1. Gehe zu **Einstellungen** → **System** → **Neustarten**
2. Klicke **Neustarten**
3. Warte 1-2 Minuten bis HA vollständig neugestartet ist

### Schritt 4: Integration aktivieren

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Klicke **+ Integration hinzufügen** (unten rechts)
3. Suche nach "**RTSP Recorder**"
4. Klicke darauf und folge dem Einrichtungsassistenten

---

## 3. Manuelle Installation

### 3.1 Dateien kopieren

```bash
# Integration kopieren
cp -r custom_components/rtsp_recorder/ /config/custom_components/

# Dashboard Card kopieren
cp www/rtsp-recorder-card.js /config/www/
```

### 3.2 Lovelace Resource registrieren

**Option A: UI (Empfohlen)**

1. Einstellungen → Dashboards → Ressourcen
2. **+ Ressource hinzufügen**
3. URL: `/local/rtsp-recorder-card.js`
4. Typ: **JavaScript-Modul**

**Option B: YAML**

```yaml
# In configuration.yaml
lovelace:
  mode: yaml
  resources:
    - url: /local/rtsp-recorder-card.js
      type: module
```

### 3.3 Verzeichnisstruktur prüfen

```
/config/
├── custom_components/
│   └── rtsp_recorder/
│       ├── __init__.py
│       ├── analysis.py
│       ├── config_flow.py
│       ├── database.py
│       ├── ...
│       └── websocket_handlers.py
└── www/
    └── rtsp-recorder-card.js
```

---

## 4. Detector Add-on Setup

Das Detector Add-on ermöglicht KI-Analyse mit Coral USB EdgeTPU.

> ⚠️ **Dieser Schritt ist optional aber empfohlen für KI-Objekterkennung und Gesichtserkennung!**

### 4.1 Add-on Dateien kopieren

1. Zugriff auf deinen Home Assistant Config-Ordner (via SSH, Samba, oder File Editor)
2. Erstelle den Ordner `/addons/rtsp-recorder-detector/` falls er nicht existiert
3. Kopiere alle Dateien aus `addons/rtsp-recorder-detector/` dorthin

### 4.2 Add-on installieren

1. Gehe zu **Einstellungen** → **Add-ons**
2. Klicke **Add-on Store** (unten rechts)
3. Klicke **⋮** (drei Punkte oben rechts) → **Nach Updates suchen**
4. Scrolle runter zu **"Lokale Add-ons"**
5. Finde **"RTSP Recorder Detector"** und klicke darauf
6. Klicke **Installieren** und warte (das kann 5-10 Minuten dauern)

### 4.3 USB-Zugriff konfigurieren (für Coral)

1. Nach der Installation, gehe zum **Konfiguration** Tab
2. Wenn du Coral USB hast, stelle sicher dass es angeschlossen ist
3. Das Add-on erkennt Coral automatisch - keine spezielle Konfiguration nötig

### 4.4 Add-on starten

1. Klicke **Starten**
2. Aktiviere **Bei Systemstart starten** (Schalter)
3. Aktiviere **Watchdog** (optional, startet Add-on bei Absturz neu)
4. Warte bis das Add-on gestartet ist (prüfe den Log Tab)

### 4.5 Deine Detector URL finden (KRITISCH!)

> ⚠️ **Die Detector URL ist bei jeder Installation anders! Du MUSST deine korrekte URL finden!**

1. Gehe zum **Info** Tab des Detector Add-ons
2. Finde den **Hostname** - er sieht so aus:
   ```
   a861495c-rtsp-recorder-detector
   ```
3. Deine Detector URL ist:
   ```
   http://[HOSTNAME]:5000
   ```
   Beispiel: `http://a861495c-rtsp-recorder-detector:5000`

**Häufige Fehler vermeiden:**
- ❌ `http://local-rtsp-recorder-detector:5000` - Das funktioniert NICHT!
- ❌ `http://localhost:5000` - Das funktioniert NICHT von HA aus!
- ✅ `http://[dein-slug]-rtsp-recorder-detector:5000` - Das ist korrekt!

### 4.6 Integration mit Detector URL konfigurieren

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Finde **RTSP Recorder** und klicke **Konfigurieren**
3. Gib die **Detector URL** ein, die du in Schritt 4.5 gefunden hast
4. Klicke **Absenden**

---

## 5. Coral USB Einrichtung

### 5.1 Hardware-Passthrough (Home Assistant OS)

Das Detector Add-on erkennt Coral USB automatisch wenn angeschlossen.

1. Stecke den Coral USB Accelerator ein
2. Starte das Detector Add-on neu
3. Prüfe das Log auf:
   ```
   INFO: Coral USB EdgeTPU detected
   INFO: Using EdgeTPU delegate
   ```

### 5.2 Coral funktioniert verifizieren

1. Öffne den Detector Add-on **Log** Tab
2. Suche nach "Coral" oder "EdgeTPU" in den Startmeldungen
3. In der RTSP Recorder Card, gehe zum **Performance** Tab um Coral Stats zu sehen

### 5.3 Troubleshooting Coral

| Problem | Lösung |
|---------|--------|
| Coral nicht erkannt | USB raus/rein stecken, Add-on neustarten |
| Permission denied | Gesamtes Home Assistant neustarten |
| Langsame Inferenz (>500ms) | Coral funktioniert nicht, Logs prüfen |

---

## 6. Erste Konfiguration

### 6.1 Integrations-Einrichtungsassistent

Wenn du die Integration zum ersten Mal hinzufügst, wirst du durch folgendes geführt:

1. **Basis-Einstellungen**
   - Storage Path: `/media/rtsp_recorder/ring_recordings`
   - Thumbnail Path: `/config/www/thumbnails`
   - Detector URL: (aus Schritt 4.5)

2. **Kameras hinzufügen**
   - Name: z.B. "Wohnzimmer"
   - Motion Sensor: Aus Dropdown auswählen
   - Camera Entity oder RTSP URL

3. **Analyse-Einstellungen** (optional)
   - Auto-Analyse: Aktivieren/Deaktivieren
   - Analyse-Intervall

### 6.2 Empfohlene Einstellungen

| Einstellung | Empfohlener Wert | Beschreibung |
|-------------|------------------|--------------|
| **Retention Days** | 7 | Wie lange Aufnahmen behalten werden |
| **Recording Duration** | 30 Sekunden | Länge jeder Aufnahme |
| **Snapshot Delay** | 2 Sekunden | Wann Thumbnail erstellt wird |
| **Auto-Analyze** | Aktiviert | Neue Aufnahmen automatisch analysieren |

---

## 7. Dashboard einrichten

### 7.1 Neues Dashboard erstellen (Empfohlen)

1. Gehe zu **Einstellungen** → **Dashboards**
2. Klicke **+ Dashboard hinzufügen**
3. Name: "RTSP Recorder"
4. Icon: `mdi:cctv`
5. Klicke **Erstellen**

### 7.2 RTSP Recorder Card hinzufügen

1. Öffne dein neues Dashboard
2. Klicke **✏️** (Bearbeiten, oben rechts)
3. Klicke **+ Karte hinzufügen**
4. Scrolle ganz nach unten und wähle **"Manuell"** (oder suche "rtsp")
5. Lösche den bestehenden Inhalt und füge ein:

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recorder/ring_recordings
thumb_path: /local/thumbnails
```

6. Klicke **Speichern**

### 7.3 Auf Vollbild-Panel-Modus stellen (WICHTIG!)

Die Card sieht im **Panel-Modus** (Vollbild) am besten aus:

1. Klicke **✏️** (Bearbeiten-Modus)
2. Klicke den **✏️** neben "Unbenannte Ansicht" oben
3. Finde die Einstellung **"Ansichtstyp"**
4. Ändere von "Kacheln" zu **"Panel (1 Karte)"**
5. Klicke **Speichern**
6. Klicke **Fertig** (oben rechts)

Jetzt füllt die RTSP Recorder Card den gesamten Bildschirm!

### 7.4 Browser-Cache aktualisieren

Nach der Einrichtung, erzwinge Browser-Refresh:
- **Windows/Linux:** `Strg + Shift + R`
- **Mac:** `Cmd + Shift + R`

---

## 8. Verifizierung

### 8.1 Integration-Status prüfen

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Finde **RTSP Recorder**
3. Es sollte "Konfiguriert" ohne Fehler anzeigen

### 8.2 Detector-Verbindung prüfen

1. Öffne die RTSP Recorder Card
2. Klicke auf den **"Menue"** Tab
3. Prüfe den **Performance** Bereich
4. Du solltest "Coral: ✓" sehen wenn Coral erkannt wurde

### 8.3 Test-Aufnahme

1. Löse Bewegung an einem konfigurierten Sensor aus (laufe an der Kamera vorbei)
2. Du solltest sehen:
   - "Aufnahme läuft" im Card-Footer
   - Neue Aufnahme erscheint in der Timeline nach ~30 Sekunden

### 8.4 Häufige Erstinstallations-Probleme

| Problem | Lösung |
|---------|--------|
| Card zeigt "Keine Aufnahmen" | Warte auf Motion-Trigger, oder prüfe Storage-Pfad |
| "Detector nicht verfügbar" | Prüfe Detector URL (Schritt 4.5) |
| Card lädt nicht | Browser-Cache leeren (Strg+Shift+R) |
| Keine Thumbnails | Prüfe ob thumb_path auf `/local/thumbnails` zeigt |

---

## Nächste Schritte

- 📖 [Benutzerhandbuch](USER_GUIDE_DE.md) - Alle Features erklärt
- 🧠 [Gesichtserkennung](FACE_RECOGNITION_DE.md) - Personen-Training
- ⚙️ [Konfiguration](CONFIGURATION_DE.md) - Alle Optionen
- 🔧 [Troubleshooting](TROUBLESHOOTING_DE.md) - Problemlösung

---

*Bei Problemen: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
