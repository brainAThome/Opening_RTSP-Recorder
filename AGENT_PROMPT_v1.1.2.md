# AGENT PROMPT v1.1.2 FINAL

Du arbeitest als automatisierter Coding-Agent an **RTSP Recorder** - einer Home Assistant Integration für Videoüberwachung mit KI-Objekterkennung.

---

## 1) KRITISCHE ARBEITSREGELN

### 1.1 Arbeitsverzeichnis (EINZIGES)
```
C:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder\Opening RTSP-Recorder beta v1.1.2
```
- **NUR hier Dateien ändern**
- Alle anderen Ordner (ARCHIV, etc.) sind READ-ONLY

### 1.2 Server-Zugang
```
Host: 192.168.178.123
User: root
SSH: ssh root@192.168.178.123
```

### 1.3 Deployment nach Änderungen
```powershell
# Datei hochladen
scp "<lokaler-pfad>" root@192.168.178.123:/config/custom_components/rtsp_recorder/

# HA neu starten
ssh root@192.168.178.123 "ha core restart"
```

### 1.4 Git-Workflow
```powershell
cd "Opening RTSP-Recorder beta v1.1.2"
git add -A
git commit -m "type: description"
git push origin main
```

---

## 2) PROJEKTÜBERSICHT

### 2.1 Was ist RTSP Recorder?
Eine Home Assistant Integration für:
- **RTSP-Recording:** Bewegungsgesteuerte Aufnahmen von IP-Kameras
- **KI-Analyse:** Objekterkennung, Gesichtserkennung, Personenerkennung
- **Timeline-UI:** Lovelace Card mit Video-Player und Overlay
- **Person-Management:** Training, Positive/Negative Samples, Centroids

### 2.2 Technologie-Stack
| Komponente | Technologie |
|------------|-------------|
| Backend | Python 3.11+, Home Assistant Core |
| Frontend | JavaScript (Lovelace Custom Card) |
| Datenbank | SQLite mit WAL-Modus |
| AI | Coral EdgeTPU, MobileDet, MobileNet, EfficientNet, MoveNet |
| Container | Docker (Detector Add-on) |

---

## 3) ARCHITEKTUR IM DETAIL

### 3.1 Backend-Module (`custom_components/rtsp_recorder/`)

| Datei | Verantwortung | Wichtige Funktionen |
|-------|---------------|---------------------|
| `__init__.py` | Setup, Views, Events | `async_setup_entry()`, `async_unload_entry()` |
| `analysis.py` | AI-Pipeline | `analyze_recording()`, `_match_face()`, `_run_detector()` |
| `database.py` | SQLite CRUD | `add_person()`, `get_people()`, `add_embedding()` |
| `services.py` | HA Services | `handle_analyze_recording()`, `_analyze_batch()` |
| `websocket_handlers.py` | WebSocket API | `handle_get_recordings()`, `handle_train_person()` |
| `config_flow.py` | Konfiguration | `async_step_user()`, `async_step_options()` |
| `helpers.py` | Utilities | `validate_path()`, `get_system_stats()` |
| `recorder_optimized.py` | FFmpeg | `async_record()`, `_capture_snapshot()` |
| `retention.py` | Cleanup | `cleanup_old_recordings()`, `cleanup_analysis_data()` |

### 3.2 Frontend (`www/rtsp-recorder-card.js`)

**Haupt-Klasse:** `RTSPRecorderCard extends LitElement`

**Key Methoden:**
- `_renderTimeline()` - Rendert Recording-Liste
- `_renderVideoSection()` - Video-Player mit Overlay
- `_renderSettingsPanel()` - 6-Tab Settings UI
- `_renderPeopleTab()` - Person Management
- `analyzeAllRecordings()` - Batch Analysis starten
- `_escapeHtml()` - **XSS-Schutz (IMMER nutzen!)**

### 3.3 Detector Add-on

**URL:** `http://local-rtsp-recorder-detector:5000`

**Endpoints:**
- `POST /detect` - Object Detection
- `POST /face/detect` - Face Detection
- `POST /face/embedding` - Face Embedding generieren
- `POST /movenet` - Pose Estimation

### 3.4 Datenbank-Schema

```sql
-- Personen
CREATE TABLE people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    centroid BLOB,
    created_at TEXT,
    updated_at TEXT
);

-- Face Embeddings
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    person_id TEXT,
    vector BLOB NOT NULL,
    source_image TEXT,
    is_negative INTEGER DEFAULT 0,
    created_at TEXT
);

-- Erkennungs-Historie
CREATE TABLE recognition_history (
    id INTEGER PRIMARY KEY,
    person_id TEXT,
    person_name TEXT,
    camera TEXT,
    confidence REAL,
    timestamp TEXT
);
```

---

## 4) WICHTIGE CODE-PATTERNS

### 4.1 SQL - IMMER Parameterized!
```python
# RICHTIG
cursor.execute("SELECT * FROM people WHERE id = ?", (person_id,))

# FALSCH - NIE machen!
cursor.execute(f"SELECT * FROM people WHERE id = '{person_id}'")
```

### 4.2 XSS-Schutz - IMMER escapen!
```javascript
// RICHTIG
innerHTML = `<div>${this._escapeHtml(userName)}</div>`;

// FALSCH - NIE machen!
innerHTML = `<div>${userName}</div>`;
```

### 4.3 Path Validation
```python
# RICHTIG
real_path = os.path.realpath(user_path)
if not real_path.startswith(allowed_prefix):
    raise PathTraversalError("Invalid path")
```

### 4.4 Async I/O
```python
# CPU-intensive Operationen im Executor
result = await hass.async_add_executor_job(blocking_function, args)
```

---

## 5) AKTUELLE KONFIGURATION (Server)

```
Storage: /media/rtsp_recorder/ring_recordings
Thumbnails: /media/rtsp_recorder/thumbnails
Analysis: /media/rtsp_recorder/ring_recordings/_analysis
Database: /config/rtsp_recorder.db
Device: coral_usb
Detector: http://local-rtsp-recorder-detector:5000
```

**Wichtige Schwellwerte:**
- `analysis_detector_confidence`: 0.55 (55% für Object Detection)
- `analysis_face_confidence`: 0.2 (20% für Face Detection)
- `analysis_face_match_threshold`: 0.35 (35% für Face Matching) ⚠️ NIEDRIG!

---

## 6) DEBUGGING

### 6.1 Logs prüfen
```bash
# HA Logs
ssh root@192.168.178.123 "tail -100 /config/home-assistant.log | grep -i rtsp"

# Debug Log
ssh root@192.168.178.123 "tail -200 /config/rtsp_debug.log"
```

### 6.2 Häufige Fehler

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `auto_device undefined` | Variable nicht im Scope | Korrekten Parameter nutzen |
| `No such file or directory` | Pfad falsch | `realpath()` + Prefix prüfen |
| `database is locked` | Concurrent Access | WAL-Modus + Retry-Logic |
| XSS/Script Injection | `_escapeHtml()` fehlt | Alle User-Inputs escapen |

### 6.3 Datenbank prüfen
```bash
ssh root@192.168.178.123 "sqlite3 /config/rtsp_recorder.db '.tables'"
ssh root@192.168.178.123 "sqlite3 /config/rtsp_recorder.db 'SELECT id, name FROM people'"
```

---

## 7) QUALITÄTSSTANDARDS

### 7.1 Code Quality (einhalten!)
- **Type Hints:** Auf 88%+ halten
- **SQL:** NUR parameterized queries
- **XSS:** ALLE User-Inputs escapen
- **Paths:** IMMER validieren
- **Logging:** Strukturiert mit METRIC| Prefix

### 7.2 Audit Scores (Stand v1.1.2)
- ISO 25010: 93/100 (EXCELLENT)
- ISO 27001: 85/100 (GOOD)

---

## 8) GIT & RELEASE

### 8.1 Commit Messages
```
fix: beschreibung (für Bugfixes)
feat: beschreibung (für Features)
docs: beschreibung (für Dokumentation)
refactor: beschreibung (für Refactoring)
```

### 8.2 Release erstellen
```powershell
# Tag aktualisieren
git tag -d v1.1.2
git push origin :refs/tags/v1.1.2
git tag v1.1.2
git push origin v1.1.2

# Release erstellen
gh release create v1.1.2 --title "v1.1.2" --notes "Release notes..."
```

---

## 9) REFERENZDOKUMENTE

Lies diese Dokumente für vollständiges Verständnis:

1. **HANDOVER_v1.1.2_FINAL.md** - Vollständige Projektübergabe
2. **COMPREHENSIVE_AUDIT_REPORT_v4.0_2026-02-03.md** - Qualitäts-Audit
3. **README.md** - Feature-Übersicht
4. **CHANGELOG.md** - Versionshistorie
5. **docs/CONFIGURATION.md** - Alle Konfigurationsoptionen
6. **docs/TROUBLESHOOTING.md** - Bekannte Probleme

---

## 10) SCHNELLREFERENZ

### Server-Dateien
```
/config/custom_components/rtsp_recorder/  # Backend
/config/www/rtsp-recorder-card.js         # Frontend
/config/rtsp_recorder.db                  # Datenbank
/config/.storage/core.config_entries      # HA Konfiguration
```

### Lokale Dateien
```
custom_components/rtsp_recorder/  # Backend
www/rtsp-recorder-card.js         # Frontend
docs/                             # Dokumentation
tests/                            # Tests
```

### Wichtige Befehle
```powershell
# Server-Status
ssh root@192.168.178.123 "ha core info"

# Logs live
ssh root@192.168.178.123 "tail -f /config/home-assistant.log | grep -i rtsp"

# Dateien vergleichen
ssh root@192.168.178.123 "sha256sum /config/custom_components/rtsp_recorder/services.py"
Get-FileHash "custom_components\rtsp_recorder\services.py" -Algorithm SHA256
```

---

**Version:** 1.1.2 FINAL  
**Erstellt:** 05. Februar 2026  
**Gültig für:** RTSP Recorder v1.1.2
