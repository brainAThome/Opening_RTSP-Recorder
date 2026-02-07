# ⚙️ RTSP Recorder - Konfigurationsreferenz

> 🇬🇧 **[English Version](CONFIGURATION.md)**

**Version:** 1.2.2  
**Letzte Aktualisierung:** 07. Februar 2026

---

## Inhaltsverzeichnis

1. [Basis-Konfiguration](#1-basis-konfiguration)
2. [Kamera-Einstellungen](#2-kamera-einstellungen)
3. [Analyse-Optionen](#3-analyse-optionen)
4. [Gesichtserkennung](#4-gesichtserkennung)
5. [Automatische Analyse](#5-automatische-analyse)
6. [Performance-Einstellungen](#6-performance-einstellungen)
7. [Erweiterte Optionen](#7-erweiterte-optionen)
8. [Beispiel-Konfigurationen](#8-beispiel-konfigurationen)

---

## 1. Basis-Konfiguration

### Speicherpfade

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `storage_path` | `/media/rtsp_recorder/ring_recordings` | Aufnahme-Speicherort |
| `snapshot_path` | `/media/rtsp_recorder/thumbnails` | Thumbnail-Speicherort |
| `analysis_output_path` | `/media/rtsp_recorder/ring_recordings/_analysis` | Analyse-Ergebnisse |

### Retention (Aufbewahrung)

| Option | Standard | Bereich | Beschreibung |
|--------|----------|---------|--------------|
| `retention_days` | 7 | 1-365 | Aufnahmen behalten (Tage) |
| `retention_hours` | 0 | 0-23 | Zusätzliche Stunden |
| `snapshot_retention_days` | 7 | 1-365 | Thumbnails behalten (Tage) |

**Beispiel:**
```yaml
retention_days: 14
retention_hours: 12
# = 14 Tage und 12 Stunden
```

### Datenbank

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `use_sqlite` | `false` | SQLite statt JSON für Personen-DB |

**Empfehlung:** SQLite aktivieren bei >20 Personen für bessere Performance.

---

## 2. Kamera-Einstellungen

### Pro Kamera verfügbar

| Option | Format | Beschreibung |
|--------|--------|--------------|
| `sensor_{Kamera}` | Entity ID | Motion Sensor für Trigger |
| `duration_{Kamera}` | Sekunden | Aufnahmedauer |
| `snapshot_delay_{Kamera}` | Sekunden | Verzögerung für Thumbnail |

### Beispiel

```yaml
# Kamera: Wohnzimmer
sensor_Wohnzimmer: binary_sensor.wohnzimmer_motion
duration_Wohnzimmer: 90
snapshot_delay_Wohnzimmer: 4

# Kamera: Haustür
sensor_Haustuer: binary_sensor.haustur_motion
duration_Haustuer: 120
snapshot_delay_Haustuer: 3
```

### Empfohlene Aufnahmedauern

| Kamera-Typ | Empfehlung | Grund |
|------------|------------|-------|
| Innenraum | 60-90s | Typische Aktivitätsdauer |
| Eingang/Flur | 30-60s | Kurze Durchgangszeiten |
| Außenbereich | 120-180s | Längere Wege |
| Haustür | 90-120s | Paketannahme etc. |

---

## 3. Analyse-Optionen

### Basis-Analyse

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `analysis_enabled` | `true` | Analyse-Feature aktiv |
| `analysis_detector_url` | `http://local-rtsp-recorder-detector:5000` | Detector-Endpunkt |
| `analysis_device` | `coral_usb` | Inferenz-Hardware |

### Verfügbare Geräte

| Wert | Hardware | Geschwindigkeit |
|------|----------|-----------------|
| `coral_usb` | Google Coral USB | ~50ms/Frame |
| `coral_pcie` | Google Coral PCIe | ~30ms/Frame |
| `cpu` | CPU (Fallback) | ~500ms/Frame |

### Objekt-Detection

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `analysis_detector_confidence` | 0.5 | Globale Confidence-Schwelle |
| `analysis_frame_interval` | 2 | Jeder X-te Frame analysiert |
| `analysis_objects` | Liste | Zu erkennende Objekte |

### Verfügbare Objekte

```yaml
analysis_objects:
  - person        # Personen
  - car           # Autos
  - truck         # LKW
  - bicycle       # Fahrräder
  - motorcycle    # Motorräder
  - dog           # Hunde
  - cat           # Katzen
  - bird          # Vögel
  - package       # Pakete
  - backpack      # Rucksäcke
  - suitcase      # Koffer
  - bottle        # Flaschen
  - cup           # Tassen
  - chair         # Stühle
  - couch         # Sofas
  - bed           # Betten
  - tv            # Fernseher
  - laptop        # Laptops
  - cell phone    # Handys
  - book          # Bücher
  - potted plant  # Pflanzen
  - umbrella      # Regenschirme
  - remote        # Fernbedienungen
  - dining table  # Esstische
```

### Pro-Kamera Objekte

```yaml
# Nur bestimmte Objekte pro Kamera
analysis_objects_Wohnzimmer:
  - person
  - dog
  - cat
  - remote
  - book

analysis_objects_Haustuer:
  - person
  - package
  - car
  - bicycle
```

### Pro-Kamera Confidence

```yaml
# Höhere Confidence für gut beleuchtete Räume
detector_confidence_Wohnzimmer: 0.6
detector_confidence_Flur: 0.4
detector_confidence_Garten: 0.5
```

---

## 4. Gesichtserkennung

| Option | Standard | Bereich | Beschreibung |
|--------|----------|---------|--------------|
| `analysis_face_enabled` | `false` | true/false | Face Detection aktiv |
| `analysis_face_confidence` | 0.2 | 0.1-0.9 | Gesichts-Erkennungsschwelle |
| `analysis_face_match_threshold` | 0.35 | 0.2-0.6 | Matching-Schwelle |
| `person_entities_enabled` | `false` | true/false | HA-Entities pro Person |

### Empfohlene Einstellungen

| Szenario | face_confidence | match_threshold |
|----------|----------------|-----------------|
| Standard | 0.2 | 0.35 |
| Hohe Genauigkeit | 0.3 | 0.30 |
| Schwierige Lichtverhältnisse | 0.15 | 0.40 |
| Viele ähnliche Personen | 0.2 | 0.28 |

---

## 5. Automatische Analyse

### Scheduling-Optionen

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `analysis_auto_enabled` | `false` | Auto-Analyse aktiv |
| `analysis_auto_mode` | `daily` | Modus: `daily` oder `interval` |
| `analysis_auto_time` | `03:00` | Uhrzeit (bei daily) |
| `analysis_auto_interval_hours` | 24 | Intervall in Stunden |

### Filter-Optionen

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `analysis_auto_since_days` | 1 | Aufnahmen der letzten X Tage |
| `analysis_auto_limit` | 50 | Max. Aufnahmen pro Durchlauf |
| `analysis_auto_skip_existing` | `true` | Bereits analysierte überspringen |
| `analysis_auto_new` | `true` | Nur neue Aufnahmen analysieren |

### Beispiel: Tägliche Analyse um 3 Uhr

```yaml
analysis_auto_enabled: true
analysis_auto_mode: daily
analysis_auto_time: "03:00"
analysis_auto_since_days: 1
analysis_auto_limit: 100
analysis_auto_skip_existing: true
```

### Beispiel: Alle 6 Stunden

```yaml
analysis_auto_enabled: true
analysis_auto_mode: interval
analysis_auto_interval_hours: 6
analysis_auto_limit: 25
```

---

## 6. Performance-Einstellungen

### Hardware-Monitoring

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `analysis_perf_cpu_entity` | `null` | CPU-Sensor Entity |
| `analysis_perf_coral_entity` | `null` | Coral-Temperatur Entity |
| `analysis_perf_igpu_entity` | `null` | iGPU Entity (optional) |

### Empfohlene System-Sensoren

```yaml
# System Monitor Integration
sensor:
  - platform: systemmonitor
    resources:
      - type: processor_use
      - type: memory_use_percent
      - type: disk_use_percent
        arg: /

# Coral USB Temperatur (wenn verfügbar)
analysis_perf_coral_entity: sensor.coral_temperature
```

---

## 7. Erweiterte Optionen

### Interne Einstellungen

Diese Optionen sind normalerweise nicht zu ändern:

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| Frame Stability Check | 1s, 2 Checks | Wartezeit für stabile Dateien |
| Inference History | 1000 Einträge | Buffer für TPU-Load-Berechnung |
| Rate Limiter | Token Bucket | DoS-Schutz für API |

### Debug-Logging

In `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.rtsp_recorder: debug
```

### Metriken aktivieren

Metriken werden automatisch geloggt:
```bash
# Anzeigen
grep METRIC /config/home-assistant.log | tail -20

# Format
METRIC|camera_name|metric_type|value
METRIC|Wohnzimmer|recording_to_saved|32.1s
METRIC|Wohnzimmer|analysis_duration|6.2s
```

---

## 8. Beispiel-Konfigurationen

### Minimal (nur Recording)

```yaml
storage_path: /media/rtsp_recorder/recordings
snapshot_path: /media/rtsp_recorder/thumbnails
retention_days: 7

sensor_Wohnzimmer: binary_sensor.wohnzimmer_motion
duration_Wohnzimmer: 60

analysis_enabled: false
```

### Standard (mit Analyse)

```yaml
storage_path: /media/rtsp_recorder/recordings
snapshot_path: /media/rtsp_recorder/thumbnails
retention_days: 14

# Kameras
sensor_Wohnzimmer: binary_sensor.wohnzimmer_motion
duration_Wohnzimmer: 90
snapshot_delay_Wohnzimmer: 4

sensor_Haustuer: binary_sensor.haustur_motion
duration_Haustuer: 120
snapshot_delay_Haustuer: 3

# Analyse
analysis_enabled: true
analysis_detector_url: http://local-rtsp-recorder-detector:5000
analysis_device: coral_usb
analysis_detector_confidence: 0.5
analysis_objects:
  - person
  - car
  - dog
  - package
```

### Vollständig (alle Features)

```yaml
# Speicher
storage_path: /media/rtsp_recorder/recordings
snapshot_path: /media/rtsp_recorder/thumbnails
analysis_output_path: /media/rtsp_recorder/analysis
retention_days: 30
snapshot_retention_days: 14
use_sqlite: true

# Kameras
sensor_Wohnzimmer: binary_sensor.wohnzimmer_motion
duration_Wohnzimmer: 90
snapshot_delay_Wohnzimmer: 4
analysis_objects_Wohnzimmer: [person, dog, cat, remote]
detector_confidence_Wohnzimmer: 0.6

sensor_Haustuer: binary_sensor.haustur_motion
duration_Haustuer: 120
snapshot_delay_Haustuer: 3
analysis_objects_Haustuer: [person, package, car, bicycle]
detector_confidence_Haustuer: 0.5

sensor_Garten: binary_sensor.garten_motion
duration_Garten: 180
snapshot_delay_Garten: 5
analysis_objects_Garten: [person, car, dog, bird]

# Analyse
analysis_enabled: true
analysis_detector_url: http://local-rtsp-recorder-detector:5000
analysis_device: coral_usb
analysis_detector_confidence: 0.5
analysis_frame_interval: 2
analysis_objects: [person, car, dog, cat, package]

# Gesichtserkennung
analysis_face_enabled: true
analysis_face_confidence: 0.2
analysis_face_match_threshold: 0.35
person_entities_enabled: true

# Auto-Analyse
analysis_auto_enabled: true
analysis_auto_mode: daily
analysis_auto_time: "03:00"
analysis_auto_since_days: 1
analysis_auto_limit: 100
analysis_auto_skip_existing: true
analysis_auto_new: true

# Performance
analysis_perf_cpu_entity: sensor.processor_use
analysis_perf_coral_entity: sensor.coral_temperature
```

---

## Siehe auch

- 📖 [Benutzerhandbuch](USER_GUIDE.md)
- 🚀 [Installation](INSTALLATION.md)
- 🧠 [Gesichtserkennung](FACE_RECOGNITION.md)
- 🔧 [Troubleshooting](TROUBLESHOOTING.md)

---

*Bei Problemen: [GitHub Issues](https://github.com/brainAThome/RTSP-Recorder/issues)*
