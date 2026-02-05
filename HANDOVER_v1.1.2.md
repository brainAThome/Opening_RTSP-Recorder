# HANDOVER v1.1.2 FINAL

**Projekt:** RTSP Recorder (Home Assistant Integration)  
**Version:** v1.1.2  
**Datum:** 05. Februar 2026  
**Status:** Produktiv auf Server, GitHub Release aktuell

---

## 1) Aktuelle Arbeitsumgebung

### Lokales Arbeitsverzeichnis
```
C:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder\Opening RTSP-Recorder beta v1.1.2
```

### Server (Home Assistant)
- **Host:** 192.168.178.123
- **User:** root
- **Integration:** /config/custom_components/rtsp_recorder/
- **Frontend Card:** /config/www/rtsp-recorder-card.js
- **Recordings:** /media/rtsp_recorder/ring_recordings/
- **Thumbnails:** /media/rtsp_recorder/thumbnails/
- **Analysis Output:** /media/rtsp_recorder/ring_recordings/_analysis/

### GitHub Repository
- **URL:** https://github.com/brainAThome/RTSP-Recorder
- **Branch:** main
- **Release:** v1.1.2

---

## 2) Architektur-Übersicht

### 2.1 Backend (Python - Home Assistant Integration)
Pfad: `custom_components/rtsp_recorder/`

| Datei | LOC | Funktion |
|-------|-----|----------|
| `__init__.py` | ~900 | Setup, Views, Scheduler, Event-Hooks |
| `analysis.py` | ~1350 | AI-Pipeline: Object Detection, Face Recognition, MoveNet |
| `database.py` | ~1200 | SQLite WAL, Thread-Local Connections, CRUD |
| `config_flow.py` | ~1100 | HA Config Flow, Options Flow, Validierung |
| `services.py` | ~920 | HA Services, Batch Analysis, Progress Tracking |
| `websocket_handlers.py` | ~1100 | WebSocket API, voluptuous Schema-Validierung |
| `helpers.py` | ~450 | Path-Validation, Logging, System Stats |
| `recorder_optimized.py` | ~450 | FFmpeg Recording, Parallel Snapshots |
| `retention.py` | ~300 | Cleanup-Jobs, Retention-Management |
| `performance.py` | ~350 | Metrics, TPU Load, Inference Stats |
| `people_db.py` | ~350 | Person Database, Centroids, Embeddings |
| `face_matching.py` | ~250 | Cosine Similarity, Negative Samples |
| `exceptions.py` | ~250 | 29 Custom Exception Classes |
| `const.py` | ~80 | Konstanten, Regex, Limits |
| `migrations.py` | ~300 | Schema-Migrationen |
| `rate_limiter.py` | ~200 | Semaphore-basiertes Rate Limiting |

### 2.2 Frontend (JavaScript - Lovelace Card)
Pfad: `www/rtsp-recorder-card.js` (~6500 LOC)

**Hauptkomponenten:**
- Timeline mit Live-Updates und WebSocket-Events
- Video-Player mit Overlay (Bounding Boxes, Face Labels)
- Settings-Panel (6 Tabs: Allgemein, Speicher, Analyse, Personen, Bewegung, Leistung)
- Person-Management (Training, Samples, Detail-Popup)
- Batch-Analysis mit Progress-Anzeige

**Sicherheit:**
- `_escapeHtml()` für alle User-Inputs (36+ Aufrufe)
- Keine inline eval/innerHTML mit unvalidiertem Content

### 2.3 Detector Add-on
- **Container:** local-rtsp-recorder-detector
- **URL:** http://local-rtsp-recorder-detector:5000
- **Modelle:**
  - MobileDet (Object Detection) - Coral EdgeTPU optimiert
  - MobileNet V2 (Face Detection)
  - EfficientNet-EdgeTPU-S (Face Embeddings)
  - MoveNet (Pose Estimation)

### 2.4 Datenbank
- **Engine:** SQLite mit WAL-Modus
- **Pfad:** /config/rtsp_recorder.db
- **Tabellen:**
  - `people` - Personen mit Centroids
  - `embeddings` - Face Embeddings (positive/negative)
  - `recognition_history` - Erkennungs-Log
  - `no_face_embeddings` - False Positive Filter

---

## 3) Aktuelle Konfiguration (Server)

```json
{
  "storage_path": "/media/rtsp_recorder/ring_recordings",
  "snapshot_path": "/media/rtsp_recorder/thumbnails",
  "analysis_output_path": "/media/rtsp_recorder/ring_recordings/_analysis",
  "retention_days": 7,
  "analysis_device": "coral_usb",
  "analysis_detector_url": "http://local-rtsp-recorder-detector:5000",
  "analysis_detector_confidence": 0.55,
  "analysis_face_enabled": true,
  "analysis_face_confidence": 0.2,
  "analysis_face_match_threshold": 0.35,
  "analysis_frame_interval": 2,
  "analysis_max_concurrent": 2,
  "person_entities_enabled": true
}
```

**Hinweis:** `face_match_threshold` von 0.35 ist niedrig! Bei vielen Fehlerkennungen auf 0.55+ erhöhen.

---

## 4) Qualitätsstand (Audit v4.0)

### ISO 25010 Software Quality: 93/100 (EXCELLENT)
- Functional Suitability: 95/100
- Performance Efficiency: 90/100
- Compatibility: 85/100
- Usability: 95/100
- Reliability: 90/100
- Security: 95/100
- Maintainability: 90/100
- Portability: 90/100

### ISO 27001 Security: 85/100 (GOOD)
- A.8 Asset Management: 90/100
- A.9 Access Control: 80/100
- A.10 Cryptography: N/A (keine Secrets)
- A.12 Operations Security: 85/100
- A.14 System Development: 90/100
- A.18 Compliance: 80/100

### Type Hints Coverage: 88.2% (134/152 Funktionen)
| Modul | Coverage |
|-------|----------|
| analysis.py | 100% (24/24) |
| database.py | 100% (36/36) |
| exceptions.py | 100% (25/25) |
| config_flow.py | 100% (15/15) |
| helpers.py | 88.2% (15/17) |
| services.py | 50% (9/18) |
| recorder_optimized.py | 58.8% (10/17) |

### Security Verified
- ✅ 100% Parameterized SQL Queries (83+ execute calls)
- ✅ XSS Protection via `_escapeHtml()` (36+ usages)
- ✅ Path Traversal Prevention (realpath + prefix validation)
- ✅ Input Validation (VALID_NAME_PATTERN regex)
- ✅ Rate Limiting (Semaphore-based)
- ✅ Schema Validation (voluptuous for WebSocket)

---

## 5) Behobene Bugs in v1.1.2

| Bug | Ursache | Fix |
|-----|---------|-----|
| Batch Analysis "auto_device undefined" | `_analyze_batch` nutzte `auto_device` statt `device` Parameter | services.py Zeile 614: `device=device` |

---

## 6) Bekannte Einschränkungen

1. **Integration Icon:** HA zeigt nur Icons aus dem `home-assistant/brands` Repository. Lokale icon.png wird ignoriert. Für Icon-Anzeige muss PR an brands-repo erstellt werden.

2. **Face Match Threshold:** Default 0.35 ist zu niedrig für zuverlässige Unterscheidung. Empfohlen: 0.55-0.60.

3. **pytest-socket:** Blockiert async Tests. Type-Hint-Validierung erfolgt via AST statt pytest.

---

## 7) Wichtige Dateien & Artefakte

### Dokumentation
- `README.md` - Hauptdokumentation
- `CHANGELOG.md` - Versionshistorie
- `COMPREHENSIVE_AUDIT_REPORT_v4.0_2026-02-03.md` - Qualitäts-Audit
- `docs/INSTALLATION.md` - Installationsanleitung
- `docs/USER_GUIDE.md` - Benutzerhandbuch
- `docs/CONFIGURATION.md` - Konfigurationsreferenz
- `docs/FACE_RECOGNITION.md` - Gesichtserkennung
- `docs/TROUBLESHOOTING.md` - Fehlerbehebung

### Code
- `custom_components/rtsp_recorder/` - Backend (19 Python-Dateien)
- `www/rtsp-recorder-card.js` - Frontend Card
- `addons/` - Detector Add-on Definition
- `tests/` - Test Suite (14 Dateien)

### Assets
- `hacs.json` - HACS Konfiguration
- `hacs_images/icon.png` - HACS Icon
- `custom_components/rtsp_recorder/icon.png` - Integration Icon
- `custom_components/rtsp_recorder/translations/` - 5 Sprachen

---

## 8) Deployment-Workflow

### Lokale Änderung → Server
```powershell
# Einzelne Datei
scp "Opening RTSP-Recorder beta v1.1.2\custom_components\rtsp_recorder\services.py" root@192.168.178.123:/config/custom_components/rtsp_recorder/

# Ganzes Verzeichnis
scp -r "Opening RTSP-Recorder beta v1.1.2\custom_components\rtsp_recorder" root@192.168.178.123:/config/custom_components/

# HA Neustart
ssh root@192.168.178.123 "ha core restart"
```

### Git Release
```powershell
cd "Opening RTSP-Recorder beta v1.1.2"
git add -A
git commit -m "fix: description"
git push origin main

# Release erstellen/aktualisieren
gh release delete v1.1.2 -y
git tag -d v1.1.2
git push origin :refs/tags/v1.1.2
git tag v1.1.2
git push origin v1.1.2
gh release create v1.1.2 --title "v1.1.2" --notes "Release notes..."
```

---

## 9) Debugging

### Logs prüfen
```bash
ssh root@192.168.178.123 "tail -50 /config/home-assistant.log | grep -i rtsp"
ssh root@192.168.178.123 "tail -100 /config/rtsp_debug.log"
```

### Konfiguration prüfen
```bash
ssh root@192.168.178.123 "grep -A100 'rtsp_recorder' /config/.storage/core.config_entries | head -120"
```

### Datenbank prüfen
```bash
ssh root@192.168.178.123 "sqlite3 /config/rtsp_recorder.db '.tables'"
ssh root@192.168.178.123 "sqlite3 /config/rtsp_recorder.db 'SELECT * FROM people'"
```

---

## 10) Nächste Schritte (Optional)

1. **Brands PR:** Icon für HA Integrations-Seite via https://github.com/home-assistant/brands
2. **Face Threshold UI:** Empfohlenen Wert in UI anzeigen
3. **Test Coverage:** Mehr Unit Tests für services.py und recorder_optimized.py
4. **Performance:** Batch Analysis Parallelisierung optimieren

---

**Erstellt:** 05. Februar 2026  
**Autor:** Copilot Agent  
**Status:** Vollständig und aktuell
