# RTSP Recorder - Agent Prompt v1.2.3

**Für:** Neue AI-Coding-Agenten die an RTSP Recorder arbeiten  
**Version:** 1.2.3 BETA  
**Datum:** 7. Februar 2026  
**Sprache:** Deutsch bevorzugt, Englisch akzeptiert

---

## 🚨 LIES DAS ZUERST - FALLSTRICKE VERMEIDEN

### Die 6 wichtigsten Regeln die du beachten musst

#### 0. Versions-Konsistenz & Documentation (NEU & KRITISCH!)

**Was passiert:** Inkonsistente Releases, fehlende deutsche Doku, verwirrte User.

**Regel:**
1. **GitHub Releases:** Prüfe IMMER `gh release view` bevor du Annahmen triffst.
2. **Versionierung:** `manifest.json` == `hacs.json` == Code == Docs.
3. **Bilinguale Doku:** Erstellst du `DOC_EN.md`, MUSST du `DOC_DE.md` erstellen/updaten.
4. **Keine Annahmen:** Frage nicht "Soll ich Version fixen?", wenn du nicht geprüft hast ob sie wirklich falsch ist.

#### 1. Windows CRLF in JavaScript (WICHTIGSTE REGEL!)

**Was passiert:** Nach Upload einer JS-Datei kommt "Konfigurationsfehler" im HA Dashboard.

**Warum:** Windows speichert mit CRLF (`\r\n`), Linux braucht LF (`\n`).

**IMMER nach scp Upload ausführen:**
```bash
ssh root@homeassistant.local "sed -i 's/\r$//' /config/www/rtsp-recorder-card.js"
```

#### 2. Browser-Cache ignorieren

**Was passiert:** Nutzer sieht alte Version obwohl Upload korrekt war.

**Lösung:** Nutzer muss `Strg+Shift+R` machen oder Browser neu starten.

#### 3. PowerShell SSH Escaping

**Was passiert:** Befehle funktionieren lokal aber nicht über SSH.

**Falsch:**
```powershell
ssh root@homeassistant.local "grep 'word*' file.txt"
```

**Richtig:**
```powershell
ssh root@homeassistant.local 'grep "pattern" file.txt'
```

#### 4. lovelace_resources editieren

**Was passiert:** Home Assistant Dashboard kaputt.

**NIEMALS** `/config/.storage/lovelace_resources` manuell editieren!

#### 5. Falschen Ordner bearbeiten

**AKTUELLER ARBEITSORDNER:**
```
c:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder\Opening RTSP-Recorder beta v1.2.3\
```

**NICHT ANFASSEN:**
```
ARCHIV\  # Alte Versionen, nur Backup
```

---

## 📁 PROJEKTSTRUKTUR IM DETAIL

### Hauptverzeichnisse

```
Opening RTSP-Recorder beta v1.2.3\
├── custom_components\rtsp_recorder\     # Python Backend
│   ├── __init__.py                      # 715 Zeilen - HA Integration Setup
│   ├── services.py                      # 1001 Zeilen - HA Services
│   ├── websocket_handlers.py            # 1092 Zeilen - 20 WebSocket Handler
│   ├── analysis.py                      # 1952 Zeilen - KI-Analyse Pipeline
│   ├── database.py                      # 1469 Zeilen - SQLite ORM
│   ├── config_flow.py                   # 886 Zeilen - UI-Konfiguration
│   ├── people_db.py                     # 428 Zeilen - Personen-Verwaltung
│   ├── recorder_optimized.py            # 432 Zeilen - FFmpeg Recording
│   ├── face_matching.py                 # 290 Zeilen - Embedding-Vergleich
│   ├── retention.py                     # 273 Zeilen - Auto-Cleanup
│   ├── helpers.py                       # 470 Zeilen - Hilfsfunktionen
│   ├── performance.py                   # 352 Zeilen - CPU/RAM/TPU Metriken
│   ├── exceptions.py                    # 323 Zeilen - 29 Exception-Typen
│   ├── migrations.py                    # 320 Zeilen - DB-Migrationen
│   ├── rate_limiter.py                  # 219 Zeilen - DoS-Schutz
│   ├── analysis_helpers.py              # 255 Zeilen - Analyse-Hilfsfunktionen
│   ├── const.py                         # 62 Zeilen - Konstanten
│   ├── pre_record_poc.py                # 911 Zeilen - Pre-Recording PoC (ungenutzt)
│   ├── recorder.py                      # 317 Zeilen - Legacy (ungenutzt)
│   ├── manifest.json                    # HA Manifest
│   └── translations\                    # DE, EN, ES, FR, NL
├── www\
│   ├── rtsp-recorder-card.js            # 5486 Zeilen - Frontend
│   └── opening_logo4.png                # Logo
├── addons\rtsp-recorder-detector\
│   ├── app.py                           # FastAPI Server
│   ├── Dockerfile                       # Alpine + TFLite
│   ├── config.yaml                      # Add-on Config
│   └── requirements.txt                 # Dependencies
├── tests\                               # 14 Testdateien, 3547 Zeilen
├── docs\                                # 17 Dokumentationsdateien
└── README.md                            # Hauptdokumentation (1184 Zeilen)
```

### Modul-Abhängigkeiten

```
                    __init__.py (Entry Point)
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    services.py   websocket_handlers   retention.py
          │              │              │
          └──────────────┼──────────────┘
                         │
              analysis.py (KI-Pipeline)
              ┌──────────┼──────────┐
              │          │          │
        face_matching  people_db  database
                         │
                    SQLite DB
```

---

## 🖥️ SERVER-ZUGANG

### SSH-Verbindung

```powershell
ssh root@homeassistant.local
# Alternativ: ssh root@192.168.178.123
```

### Wichtige Server-Pfade

| Pfad | Beschreibung |
|------|--------------|
| `/config/custom_components/rtsp_recorder/` | Python Integration |
| `/config/www/rtsp-recorder-card.js` | Frontend Card |
| `/config/www/opening_logo4.png` | Dashboard Logo |
| `/config/rtsp_recorder/rtsp_recorder.db` | SQLite Datenbank |
| `/media/rtsp_recorder/ring_recordings/` | Video-Aufnahmen |
| `/media/rtsp_recorder/thumbnails/` | Vorschaubilder |

### Aktuelle Statistiken

- **SQLite Version:** 3.51.2
- **Datenbank:** 2.6 MB
- **Recordings:** 5.0 GB (567 Videos)
- **Kameras:** 6 (Flur_oben, Garten_hinten, Haustuer, Testcam, Thorins_Zimmer, Wohnzimmer)

---

## 🔧 DEPLOYMENT-BEFEHLE

### Python-Datei deployen

```powershell
scp "c:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder\Opening RTSP-Recorder beta v1.2.3\custom_components\rtsp_recorder\DATEINAME.py" root@homeassistant.local:/config/custom_components/rtsp_recorder/
```

**Danach:** In HA: Entwickler-Tools → YAML → RTSP Recorder neu laden

### JavaScript-Datei deployen (MIT CRLF-FIX!)

```powershell
scp "c:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder\Opening RTSP-Recorder beta v1.2.3\www\rtsp-recorder-card.js" root@homeassistant.local:/config/www/
ssh root@homeassistant.local "sed -i 's/\r$//' /config/www/rtsp-recorder-card.js"
```

**Danach:** Browser Hard-Refresh (`Strg+Shift+R`)

### Git-Operationen

```powershell
cd "c:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder\Opening RTSP-Recorder beta v1.2.3"

# Status
git status

# Commit
git add .
git commit -m "feat: Beschreibung"

# Push
git push origin main

# Tag + Release
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3

# GitHub Release erstellen
$notes = @"
## What's New
- Feature 1
"@
Compress-Archive -Path custom_components, www, addons, hacs.json, LICENSE, README.md -DestinationPath "..\rtsp-recorder-v1.2.3.zip" -Force
gh release create v1.2.3 "..\rtsp-recorder-v1.2.3.zip" --title "v1.2.3 - Title" --notes $notes
```

### Tests ausführen

```powershell
cd "c:\Users\sven-\OneDrive\Desktop\VS code Projekte\RTSP Recorder"
.\.venv\Scripts\Activate.ps1
cd "Opening RTSP-Recorder beta v1.2.3"
pytest tests/ -v
```

---

## 🔌 API-REFERENZ

### HA Services (5)

| Service | Beschreibung |
|---------|--------------|
| `rtsp_recorder.save_recording` | Startet Aufnahme |
| `rtsp_recorder.analyze_recording` | Analysiert Video |
| `rtsp_recorder.analyze_all_recordings` | Batch-Analyse |
| `rtsp_recorder.delete_recording` | Löscht Aufnahme |
| `rtsp_recorder.delete_all_recordings` | Löscht alle |

### WebSocket Handler (25)

**Beispiel-Aufruf aus Card:**
```javascript
this._hass.connection.sendMessagePromise({
    type: 'rtsp_recorder/get_detector_stats'
}).then(result => {
    console.log(result);
});
```

**Analyse:**
- `rtsp_recorder/get_analysis_overview`
- `rtsp_recorder/get_analysis_progress`
- `rtsp_recorder/get_single_analysis_progress`
- `rtsp_recorder/get_recording_progress`
- `rtsp_recorder/get_analysis_result`
- `rtsp_recorder/get_detector_stats`
- `rtsp_recorder/reset_detector_stats`
- `rtsp_recorder/test_inference`
- `rtsp_recorder/get_analysis_config`
- `rtsp_recorder/set_analysis_config`
- `rtsp_recorder/set_camera_objects`
- `rtsp_recorder/stop_batch_analysis`

**Personen:**
- `rtsp_recorder/get_people`
- `rtsp_recorder/get_person_details`
- `rtsp_recorder/get_person_details_quality`
- `rtsp_recorder/add_person`
- `rtsp_recorder/rename_person`
- `rtsp_recorder/delete_person`
- `rtsp_recorder/add_person_embedding`
- `rtsp_recorder/add_negative_sample`
- `rtsp_recorder/add_ignored_embedding`
- `rtsp_recorder/delete_embedding`
- `rtsp_recorder/bulk_delete_embeddings`

**Anderes:**
- `rtsp_recorder/get_movement_profile`
- `rtsp_recorder/thumbnails`

### Detector REST API

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/detect` | POST | Objekterkennung |
| `/detect_faces` | POST | Gesichtserkennung |
| `/compute_embedding` | POST | Face Embedding |
| `/health` | GET | Health Check |
| `/status` | GET | Status |
| `/reset_stats` | POST | Stats zurücksetzen |

---

## 🗃️ DATENBANK

### Schema (Version 2)

```sql
-- Personen
CREATE TABLE people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    is_active INTEGER DEFAULT 1,
    metadata TEXT
);

-- Face Embeddings (1280-dim)
CREATE TABLE face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT REFERENCES people(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    source_image TEXT,
    created_at TEXT,
    confidence REAL
);

-- Negative Embeddings
CREATE TABLE negative_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT REFERENCES people(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    source TEXT,
    thumb TEXT,
    created_at TEXT
);

-- Ignorierte Gesichter
CREATE TABLE ignored_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    embedding BLOB NOT NULL,
    reason TEXT,
    created_at TEXT
);

-- Erkennungs-Historie
CREATE TABLE recognition_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_name TEXT,
    person_id TEXT,
    person_name TEXT,
    confidence REAL,
    recording_path TEXT,
    frame_path TEXT,
    is_unknown INTEGER DEFAULT 0,
    metadata TEXT,
    recognized_at TEXT
);
```

### Datenbank-Abfragen

```bash
# Auf Server
ssh root@homeassistant.local 'sqlite3 /config/rtsp_recorder/rtsp_recorder.db ".tables"'

# Personen auflisten
ssh root@homeassistant.local 'sqlite3 /config/rtsp_recorder/rtsp_recorder.db "SELECT id, name FROM people"'
```

---

## 📊 WAS HAT FUNKTIONIERT

### Erfolgreiche Patterns

1. **Event-driven statt Polling**
   - `rtsp_recorder_recording_started` Event
   - `rtsp_recorder_recording_saved` Event
   - Sofortige UI-Updates

2. **SQLite WAL-Modus**
   - Concurrent Reads während Writes
   - In `database.py`: `PRAGMA journal_mode=WAL`

3. **Parallel Snapshots**
   - Thumbnail WÄHREND Recording erstellen
   - Spart 3-5 Sekunden

4. **Map statt Boolean für Multi-Kamera**
   - `_runningRecordings = new Map()`
   - Pro Kamera separater Status

5. **Type Hints überall**
   - 88.2% Coverage
   - Bessere Fehlerdiagnose

### Erfolgreiche Refactorings

1. **CC-Reduktion analyze_recording**
   - Von CC=140 auf CC=23
   - Aufgeteilt in `analysis_helpers.py`

2. **Bilingual Documentation**
   - English primary
   - German `_DE.md` suffix

---

## ❌ WAS NICHT FUNKTIONIERT HAT

### Gescheiterte Ansätze

1. **Polling für Status**
   - ❌ 1-Sekunden Timer zu langsam
   - ✅ Events + Callbacks

2. **Einzelner Boolean für Recording**
   - ❌ Multi-Kamera bricht zusammen
   - ✅ Map pro Kamera

3. **Pre-Recording**
   - ❌ Ring unterstützt kein kontinuierliches RTSP
   - ⚠️ PoC existiert in `pre_record_poc.py`

4. **Frigate-Integration**
   - ❌ Andere Architektur
   - ✅ Eigener Detector Add-on

### Technische Schulden

1. `recorder.py` - Ungenutzt, sollte gelöscht werden
2. `pre_record_poc.py` - 911 Zeilen ungenutzt

---

## 🎯 ROADMAP

### v1.2.3 (Nächste)

1. Push Notifications bei Personen-Erkennung
2. Timeline-Filter nach Person

### v1.3.0 (Langfristig)

1. Pre-Recording
2. Multi-Instance Support
3. Cloud-Backup

---

## 🐛 DEBUGGING

### Logs prüfen

```bash
# HA Logs
ssh root@homeassistant.local "grep 'rtsp_recorder' /config/home-assistant.log | tail -50"

# Detector Logs
# HA → Einstellungen → Add-ons → RTSP Recorder Detector → Protokoll
```

### Coral prüfen

```bash
ssh root@homeassistant.local "lsusb | grep -i coral"
# Sollte "Global Unichip Corp" zeigen
```

### Card-Fehler

1. F12 → Console prüfen
2. Network Tab → Card-Request prüfen

---

## 📝 CHECKLISTE BEI ÄNDERUNGEN

### Python-Änderungen

- [ ] Datei lokal editieren
- [ ] `scp` zum Server
- [ ] Integration neu laden (Entwickler-Tools → YAML)
- [ ] Logs prüfen
- [ ] Tests ausführen
- [ ] Git commit + push

### JavaScript-Änderungen

- [ ] Datei lokal editieren
- [ ] `scp` zum Server
- [ ] **`sed -i 's/\r$//'`** ausführen
- [ ] Browser Hard-Refresh
- [ ] Console prüfen
- [ ] Git commit + push

### Neue Features

- [ ] Code implementieren
- [ ] Tests schreiben
- [ ] Dokumentation aktualisieren (EN + DE)
- [ ] README aktualisieren
- [ ] Version in manifest.json erhöhen
- [ ] CHANGELOG aktualisieren
- [ ] Deploy + Test
- [ ] Git tag + release

---

## 📞 REFERENZEN

- **GitHub:** https://github.com/brainAThome/Opening_RTSP-Recorder
- **HANDOVER:** `HANDOVER_v1.2.3.md`
- **ISSUE_REPORT:** `ISSUE_REPORT_v1.2.3.md`
- **README:** `README.md`

---

**Prompt erstellt:** 7. Februar 2026  
**Version:** 1.2.3 BETA  
**Agent:** Claude Opus 4.5
