# RTSP Recorder for Home Assistant

Eine vollständige Videoüberwachungslösung mit KI-gestützter Objekt- und Gesichtserkennung für Home Assistant.

![Version](https://img.shields.io/badge/version-1.0.7%20BETA-orange)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coral](https://img.shields.io/badge/Coral%20USB-Supported-brightgreen)
![Quality](https://img.shields.io/badge/Audit%20Score-83%25-yellowgreen)

---

## 🌟 Features

### Kernfunktionen
- 🎥 **Motion-triggered Recording** - Automatische Aufnahme bei Bewegungserkennung
- 🔍 **KI-Objekterkennung** - Erkennt Personen, Autos, Tiere und mehr
- 👤 **Gesichtserkennung** - Erkennt und trainiert bekannte Personen
- 🧠 **Coral USB EdgeTPU** - Hardware-beschleunigte Inferenz (40-70ms)
- 📊 **Live Performance Monitoring** - CPU, RAM, Coral-Statistiken

### Dashboard
- 🎬 **Video-Playback** mit Timeline und Kalender
- 📷 **Multi-Kamera Support** mit Filter
- 👥 **Personen-Management** mit Training-UI
- ⚙️ **Analyse-Konfiguration** direkt in der UI
- 🔴 **Overlay** mit erkannten Objekten

### Automatisierung
- ⏰ **Geplante Analysen** (täglich oder im Intervall)
- 🗑️ **Automatische Retention** für alte Aufnahmen
- 🔄 **Auto-Analyse** für neue Aufnahmen

---

## 📦 Komponenten

```
RTSP Recorder/
├── custom_components/rtsp_recorder/   # Home Assistant Integration
│   ├── __init__.py                    # Hauptlogik & WebSocket API
│   ├── analysis.py                    # Videoanalyse-Modul
│   ├── config_flow.py                 # Konfigurationsassistent
│   ├── recorder.py                    # FFmpeg Recording
│   ├── retention.py                   # Aufbewahrungsmanagement
│   └── ...
├── www/
│   └── rtsp-recorder-card.js          # Lovelace Dashboard Card
└── addons/rtsp-recorder-detector/     # KI-Detector Add-on
    ├── app.py                         # FastAPI Server
    ├── Dockerfile                     # Container Build
    └── config.json                    # Add-on Konfiguration
```

---

## 🚀 Installation

### Schritt 1: Integration installieren

Kopiere den `custom_components/rtsp_recorder` Ordner nach `/config/custom_components/`:

```bash
# Via SSH
cd /config/custom_components
git clone https://github.com/brainAThome/RTSP-Recorder.git temp
mv temp/custom_components/rtsp_recorder .
rm -rf temp
```

### Schritt 2: Dashboard Card installieren

Kopiere `www/rtsp-recorder-card.js` nach `/config/www/`.

Füge zu deinen Lovelace-Ressourcen hinzu:
```yaml
resources:
  - url: /local/rtsp-recorder-card.js
    type: module
```

### Schritt 3: Detector Add-on installieren

1. Kopiere `addons/rtsp-recorder-detector` nach `/addons/`
2. Gehe zu **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
3. Nach Refresh erscheint das Add-on
4. Installieren und starten

### Schritt 4: Integration konfigurieren

1. **Einstellungen → Geräte & Dienste**
2. Klicke **"+ Integration hinzufügen"**
3. Suche **"RTSP Recorder"**
4. Folge dem Konfigurationsassistenten

---

## 👤 Gesichtserkennung (NEU in v1.0.7)

### Wie es funktioniert

1. **Gesichter erkennen** - Bei jeder Analyse werden automatisch Gesichter erkannt
2. **Embeddings extrahieren** - 128-dimensionale Vektoren für jedes Gesicht
3. **Personen trainieren** - Klicke "Zu Person" um ein Gesicht einer Person zuzuweisen
4. **Automatisches Matching** - Neue Gesichter werden gegen bekannte Personen gematched

### Training-Workflow

```
1. Öffne Tab "Personen" in der Dashboard Card
2. Erstelle neue Person mit "+" Button
3. Wähle Aufnahme mit Gesicht der Person
4. Klicke auf das Gesicht → "Zu Person" Button
5. Wähle Person aus Liste
6. ✅ Training abgeschlossen!
```

### Threshold-Einstellung

Der **Face Match Threshold** (Standard: 0.6) bestimmt, wie strikt das Matching ist:
- **Niedriger (0.4)** = Mehr Matches, aber mehr False Positives
- **Höher (0.8)** = Weniger Matches, aber genauer

---

## 🏠 Entitäten für Automationen

RTSP Recorder erstellt automatisch **Binary Sensors** für erkannte Personen, die du in Home Assistant Automationen verwenden kannst!

### Automatisch erstellte Entitäten

| Entität | Typ | Beschreibung |
|---------|-----|--------------|
| `binary_sensor.rtsp_recorder_person_<name>` | Binary Sensor | Wird `on` wenn Person erkannt wird |

### Entitäts-Attribute

Jede Person-Entität hat folgende Attribute:

| Attribut | Beschreibung |
|----------|--------------|
| `person_name` | Name der Person |
| `similarity` | Matching-Score (0.0 - 1.0) |
| `camera` | Kamera, die die Person erkannt hat |
| `video_path` | Pfad zur Aufnahme |
| `last_seen` | Zeitstempel der letzten Erkennung |

### Beispiel: Automation bei Personenerkennung

```yaml
automation:
  - alias: "Benachrichtigung wenn Thorin erkannt wird"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_recorder_person_thorin
        to: "on"
    condition: []
    action:
      - service: notify.mobile_app
        data:
          title: "Person erkannt!"
          message: >
            {{ state_attr('binary_sensor.rtsp_recorder_person_thorin', 'person_name') }} 
            wurde an Kamera {{ state_attr('binary_sensor.rtsp_recorder_person_thorin', 'camera') }} 
            erkannt (Similarity: {{ state_attr('binary_sensor.rtsp_recorder_person_thorin', 'similarity') | round(2) }})
```

### Beispiel: Willkommensnachricht

```yaml
automation:
  - alias: "Willkommen zuhause"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_recorder_person_sven
        to: "on"
    condition:
      - condition: state
        entity_id: person.sven
        state: "not_home"
    action:
      - service: tts.google_translate_say
        data:
          entity_id: media_player.wohnzimmer
          message: "Willkommen zuhause, Sven!"
```

### Beispiel: Unbekannte Person-Alarm

```yaml
automation:
  - alias: "Alarm bei unbekannter Person"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_recorder_person_unknown
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Unbekannte Person!"
          message: "Eine unbekannte Person wurde erkannt"
          data:
            image: "/local/thumbnails/latest_face.jpg"
```

> **Hinweis:** Die Binary Sensors werden für 30 Sekunden auf `on` gesetzt und dann automatisch auf `off` zurückgesetzt. Dies ermöglicht präzise Automationen.

---

## 🔧 Coral USB EdgeTPU

### Voraussetzungen
- Google Coral USB Accelerator
- USB Passthrough konfiguriert

### Performance-Vergleich

| Gerät | Inferenzzeit | CPU-Last |
|-------|--------------|----------|
| **Coral USB** | ~40-70ms | Minimal |
| CPU (Fallback) | ~500-800ms | Hoch |

### Troubleshooting

```bash
# Prüfe ob Coral erkannt wird
lsusb | grep "Global Unichip"

# Erwartete Ausgabe:
# Bus 001 Device 002: ID 1a6e:089a Global Unichip Corp.
```

---

## 📡 API Referenz

### WebSocket Commands

| Command | Beschreibung |
|---------|--------------|
| `rtsp_recorder/get_events` | Aufnahmen abrufen |
| `rtsp_recorder/get_analysis_result` | Analyse-Ergebnisse |
| `rtsp_recorder/get_people` | Personen-Datenbank |
| `rtsp_recorder/create_person` | Person erstellen |
| `rtsp_recorder/rename_person` | Person umbenennen |
| `rtsp_recorder/delete_person` | Person löschen |
| `rtsp_recorder/add_person_embedding` | Face Training |
| `rtsp_recorder/get_inference_stats` | Performance Stats |
| `rtsp_recorder/get_system_stats` | System Monitoring |

### Detector Add-on API

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/health` | GET | Health Check |
| `/devices` | GET | Verfügbare Geräte |
| `/detect` | POST | Objekterkennung |
| `/faces` | POST | Gesichtserkennung |
| `/stats` | GET | Performance-Statistiken |

---

## 🎛️ Dashboard Card Konfiguration

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recordings
thumb_path: /local/thumbnails
```

### Debug-Modus aktivieren

```javascript
// In Browser-Konsole:
localStorage.setItem('rtsp_recorder_debug', 'true');

// Deaktivieren:
localStorage.removeItem('rtsp_recorder_debug');
```

---

## 📋 Changelog

### v1.0.7 BETA (29.01.2026)

**Neue Features:**
- ✅ Vollständige Gesichtserkennung mit Embeddings
- ✅ Person Training über UI ("Zu Person" Button)
- ✅ Automatisches Face Re-Matching nach Training
- ✅ Background Tasks für responsive UI

**Bugfixes:**
- 🐛 Fixed: Reserved field "id" in WebSocket
- 🐛 Fixed: log_to_file() Signatur-Fehler
- 🐛 Fixed: NameError config_entry/output_dir
- 🐛 Fixed: Blockierendes Re-Matching

**Performance:**
- ⚡ Face Training Response: <100ms (vorher 2-5s)
- ⚡ Background Re-Matching

[Vollständiger Changelog →](CHANGELOG.md)

---

## 🔍 Audit Report

RTSP Recorder v1.0.7 wurde umfassend auditiert:

| Kriterium | Bewertung |
|-----------|-----------|
| **Gesamtqualität** | 83% |
| Funktionalität | 94% |
| Code-Qualität | 87% |
| Sicherheit | 85% |
| Performance | 92% |

[Vollständiger Audit Report →](AUDIT_REPORT_v1.0.7_FINAL.md)

---

## ❓ Troubleshooting

### Coral USB nicht erkannt
1. USB-Verbindung und Passthrough prüfen
2. Mit `lsusb` verifizieren
3. Add-on USB-Zugriff prüfen

### Aufnahme startet nicht
1. Motion Sensor Entity ID prüfen
2. Kamera Entity oder RTSP URL verifizieren
3. Speicherpfad-Berechtigungen prüfen

### Face Training fehlgeschlagen
1. Prüfe ob Gesichter in der Aufnahme erkannt wurden
2. Stelle sicher dass Person existiert
3. Debug-Modus aktivieren für Details

---

## 📄 Lizenz

MIT License - Siehe [LICENSE](LICENSE) für Details.

---

## 🙏 Credits

- Built for [Home Assistant](https://home-assistant.io)
- Coral USB Support inspiriert von [Frigate NVR](https://frigate.video)
- Uses [TensorFlow Lite Runtime](https://www.tensorflow.org/lite)
- Models from Google Coral

---

**Entwickelt mit ❤️ für die Home Assistant Community**

*[@brainAThome](https://github.com/brainAThome)*

