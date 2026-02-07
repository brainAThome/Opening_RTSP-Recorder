# 🚀 RTSP Recorder - Installationsanleitung

> 🇬🇧 **[English Version](INSTALLATION.md)**

**Version:** 1.2.2  
**Letzte Aktualisierung:** 07. Februar 2026

---

## Inhaltsverzeichnis

1. [Systemanforderungen](#1-systemanforderungen)
2. [Installation via HACS](#2-installation-via-hacs)
3. [Manuelle Installation](#3-manuelle-installation)
4. [Detector Add-on Setup](#4-detector-add-on-setup)
5. [Coral USB Einrichtung](#5-coral-usb-einrichtung)
6. [Erste Konfiguration](#6-erste-konfiguration)
7. [Verifizierung](#7-verifizierung)

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
- ✅ Ring Doorbell (via Ring Integration)
- ✅ Frigate Cameras
- ✅ Generic Cameras (MJPEG, HLS)

---

## 2. Installation via HACS

### Schritt 1: Custom Repository hinzufügen

1. **HACS** öffnen in Home Assistant
2. Klicke auf **⋮** (Drei-Punkte-Menü) oben rechts
3. Wähle **Custom repositories**
4. Füge hinzu:
   - **Repository:** `https://github.com/brainAThome/RTSP-Recorder`
   - **Category:** Integration
5. Klicke **Add**

### Schritt 2: Integration installieren

1. Suche in HACS nach "**RTSP Recorder**"
2. Klicke **Download**
3. Wähle Version **1.1.0** (oder neueste)
4. Bestätige mit **Download**

### Schritt 3: Home Assistant neustarten

```yaml
# In der UI: Entwicklerwerkzeuge → YAML → Home Assistant neustarten
# Oder in configuration.yaml Verzeichnis:
ha core restart
```

### Schritt 4: Integration aktivieren

1. **Einstellungen** → **Geräte & Dienste**
2. Klicke **+ Integration hinzufügen**
3. Suche "**RTSP Recorder**"
4. Folge dem Einrichtungsassistenten

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
│       ├── exceptions.py
│       ├── manifest.json
│       ├── migrations.py
│       ├── performance.py
│       ├── rate_limiter.py
│       ├── recorder.py
│       ├── services.py
│       ├── translations/
│       │   ├── de.json
│       │   ├── en.json
│       │   ├── es.json
│       │   ├── fr.json
│       │   └── nl.json
│       └── websocket_handlers.py
└── www/
    └── rtsp-recorder-card.js
```

---

## 4. Detector Add-on Setup

Das Detector Add-on ermöglicht KI-Analyse mit Coral USB.

### 4.1 Add-on installieren

1. Kopiere das Add-on:
   ```bash
   cp -r addons/rtsp-recorder-detector/ /addons/
   ```

2. **Einstellungen** → **Add-ons** → **Add-on Store**

3. Klicke **⋮** → **Check for updates**

4. Finde "**RTSP Recorder Detector**" unter "Lokale Add-ons"

5. Klicke **Installieren**

### 4.2 Add-on konfigurieren

```yaml
# Add-on Konfiguration
port: 5000
log_level: info
model_path: /models
coral_enabled: true
```

### 4.3 Add-on starten

1. Klicke **Starten**
2. Aktiviere **Bei Systemstart starten**
3. Optional: Aktiviere **Watchdog**

---

## 5. Coral USB Einrichtung

### 5.1 Hardware-Passthrough (Home Assistant OS)

1. **Einstellungen** → **System** → **Hardware**
2. Finde "Google Coral USB Accelerator"
3. Notiere den Pfad (z.B. `/dev/bus/usb/001/002`)

### 5.2 Add-on USB-Zugriff

In der Add-on Konfiguration:

```yaml
# Konfiguration für Coral USB
devices:
  - /dev/bus/usb
```

### 5.3 Coral verifizieren

1. Öffne Add-on **Log**
2. Suche nach:
   ```
   INFO: Coral USB EdgeTPU detected
   INFO: Using EdgeTPU delegate
   ```

### 5.4 Troubleshooting Coral

| Problem | Lösung |
|---------|--------|
| Coral nicht erkannt | USB neu einstecken, HA neustarten |
| Permission denied | Prüfe USB-Passthrough Einstellungen |
| Delegate error | libedgetpu Version prüfen |

---

## 6. Erste Konfiguration

### 6.1 Integration Setup

Nach der Installation:

1. **Einstellungen** → **Geräte & Dienste**
2. Klicke **+ Integration hinzufügen**
3. Suche "**RTSP Recorder**"

### 6.2 Basis-Einstellungen

| Einstellung | Empfehlung | Beschreibung |
|-------------|------------|--------------|
| Storage Path | `/media/rtsp_recorder` | Aufnahme-Speicherort |
| Snapshot Path | `/media/rtsp_recorder/thumbnails` | Thumbnail-Speicherort |
| Retention Days | 7 | Aufbewahrungsdauer |

### 6.3 Kameras hinzufügen

1. In der Integration, klicke **Konfigurieren**
2. Wähle **Kameras verwalten**
3. Füge deine Kameras hinzu:
   - **Name:** z.B. "Wohnzimmer"
   - **Motion Sensor:** `binary_sensor.wohnzimmer_motion`
   - **Camera Entity:** `camera.wohnzimmer` (optional)
   - **RTSP URL:** `rtsp://user:pass@192.168.1.x/stream`

### 6.4 Analyse aktivieren

1. In **Optionen** → **Analyse**
2. **Analyse aktiviert:** ✅
3. **Detector URL:** `http://local-rtsp-recorder-detector:5000`
4. **Gerät:** Coral USB (wenn verfügbar)

---

## 7. Verifizierung

### 7.1 Integration prüfen

```bash
# Auf dem HA Server:
grep -i rtsp_recorder /config/home-assistant.log | tail -10
```

Erwartete Ausgabe:
```
INFO: Setup of rtsp_recorder completed successfully
```

### 7.2 Detector prüfen

```bash
# API-Test
curl http://localhost:5000/info
```

Erwartete Ausgabe:
```json
{
  "version": "1.0.9",
  "coral_available": true,
  "models_loaded": true
}
```

### 7.3 Test-Aufnahme

1. Löse Bewegung an einem konfigurierten Sensor aus
2. Prüfe Log auf "Recording started"
3. Prüfe Storage-Pfad auf neue .mp4 Datei

### 7.4 Dashboard Card testen

```yaml
# In einem Dashboard:
type: custom:rtsp-recorder-card
```

---

## Nächste Schritte

- 📖 [Benutzerhandbuch](USER_GUIDE.md) - Alle Features im Detail
- 🧠 [Personen-Training](FACE_RECOGNITION.md) - Gesichtserkennung einrichten
- ⚙️ [Konfiguration](CONFIGURATION.md) - Alle Optionen erklärt
- 🔧 [Troubleshooting](TROUBLESHOOTING.md) - Problemlösung

---

*Bei Problemen: [GitHub Issues](https://github.com/brainAThome/RTSP-Recorder/issues)*
