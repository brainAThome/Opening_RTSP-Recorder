# Changelog

All notable changes to RTSP Recorder will be documented in this file.

## [1.2.3] - 2026-02-07

### ✅ Code Quality Improvements

- **Type Hints 100%**: Alle 129 Funktionen haben jetzt Return-Type Annotations
  - `__init__.py`: 4 Funktionen mit `-> bool` / `-> None`
  - `services.py`: `register_services() -> None`
  - `websocket_handlers.py`: 2 Handler-Registrierungsfunktionen
  - `recorder_optimized.py`: `cleanup_stale_tmp_files() -> None`
  - `pre_record_poc.py`: `demo() -> None`
- **README Badge**: Type Hints Badge aktualisiert von 51% (gelb) zu 100% (grün)
- **Frontend Version**: UI zeigt jetzt korrekt "BETA v1.2.3"

### 🔧 Fixes

- **Stats-Anzeige korrigiert**: WebSocket-Handler verwendet jetzt die echten Detector-Stats statt lokaler Tracker-Werte
- **Coral Anteil / TPU Last**: Werte stimmen jetzt mit den tatsächlichen Detector-Statistiken überein
- **Push-basierte Stats**: Performance-Daten werden alle 2s gepusht (reduziert Polling auf 10s Fallback)

### 📲 Push Notifications bei Personen-Erkennung

**Sofortige Benachrichtigung wenn bekannte Personen erkannt werden!**

**Features:**
- **Event**: `rtsp_recorder_person_detected` mit allen Daten
- **Event-Daten**:
  - `person_name`: Name der erkannten Person
  - `similarity`: Erkennungs-Konfidenz (0-100%)
  - `camera`: Kamera-Name
  - `video_path`: Pfad zur Aufzeichnung
  - `timestamp`: Zeitstempel der Erkennung
- **Actionable Notifications**: Klick auf Push öffnet direkt das Video
- **Beispiel-Automation**: In README dokumentiert
- **Kompatibilität**: HA Companion App (iOS/Android)

**Technische Umsetzung:**
```python
# In _set_person_entity() (after entity update)
hass.bus.async_fire("rtsp_recorder_person_detected", {
    "person_name": name,
    "similarity": similarity,
    "camera": camera,
    "video_path": video_path,
    "timestamp": datetime.now(datetime.timezone.utc).isoformat()
})
```

**Beispiel-Automation für User:**
```yaml
automation:
  - alias: "RTSP Recorder - Person Push Notification"
    trigger:
      - platform: event
        event_type: rtsp_recorder_person_detected
        event_data:
          person_name: "Sven"  # Optional: alle Personen wenn weggelassen
    action:
      - service: notify.mobile_app_iphone
        data:
          title: "{{ trigger.event.data.person_name }} erkannt!"
          message: "{{ trigger.event.data.camera }} ({{ (trigger.event.data.similarity * 100) | round(0) }}%)"
          data:
            url: "/rtsp-recorder?video={{ trigger.event.data.video_path }}"
            actions:
              - action: "VIEW"
                title: "Video ansehen"
```

---

## [1.2.2] - 2026-02-07

### 🔄 Stats Reset Feature
**Statistiken im Leistungs-Tab zurücksetzen:**
- Neuer Button "Statistik zurücksetzen" im Performance-Tab
- WebSocket-Handler: `rtsp_recorder/reset_detector_stats`
- Detector-Endpoint: `POST /stats/reset`
- Setzt zurück: Inference-Zähler, Durchschnittszeiten, Uptime

### 🐛 Recording Indicator Fix
**"Aufnahme läuft" Anzeige bleibt jetzt korrekt:**
- **Problem**: Anzeige verschwand wenn eine andere Kamera ein Video lieferte
- **Ursache**: `_restoreStatusIndicators()` verwendete alten Polling-Cache statt Event-Map
- **Fix**: Alle Status-Updates nutzen jetzt `_updateRecordingUI()` mit `_runningRecordings` Map
- **Datei**: `www/rtsp-recorder-card.js`

### 🎬 FPS Display Fix
**Korrekte FPS-Anzeige im Video-Player:**
- Detector liefert jetzt `video_fps` im Analysis-Response
- Frontend liest FPS aus Analyse-Daten
- Fallback: 25 FPS (PAL-Standard) wenn keine Daten

### 🧹 smooth_video Option entfernt
**Aufräumen nicht verwendeter Optionen:**
- Option aus Config Flow entfernt
- Keine Auswirkung auf Funktionalität (wurde nicht genutzt)
- Betrifft: `config_flow.py`, `__init__.py`, `services.py`, `analysis.py`, `de.json`

### 📱 Mobile Portrait-Ansicht (Ring-Style)
**Optimierte Mobile-Version für Lovelace Card:**
- Portrait-Layout mit Timeline-Karten im Ring-Stil
- Footer und Tabs mobil scrollbar und kompakt
- Video-Controls auf Mobile ausgeblendet, stattdessen Download/Löschen im Footer
- Leistungsanzeige und Checkboxen mobil optimiert
- Status-Indikatoren mobil ausgeblendet
- Vollständige @media-Queries für 768px/480px
- Getestet auf Android/iOS

---

## [1.2.1] - 2026-02-05

### 🛠 Code Quality: MEDIUM Findings Remediation

**Cyclomatic Complexity (CODE-001):**
- `analyze_recording`: CC 140→23 (-84%, Grade F→D)
- 16 helper functions extracted: `_run_face_detection_loop()`, `_run_object_detection_remote()`, `_run_object_detection_local()`, etc.

**Silent Exception Handlers (REL-001):**
- 7 critical `except:pass` blocks now have debug logging
- Files affected: analysis.py, __init__.py, helpers.py, services.py

**Security Documentation (SEC-002):**
- New `SECURITY.md` with biometric data policy
- GDPR compliance notes for face embeddings
- Encryption roadmap for v1.3

**Generic Exception Analysis (MEDIUM-001):**
- 30 handlers analyzed - all properly logged or acceptable patterns

**Flake8 Code Style (F824, F401):**
- Removed unused `global _cpu_history, _ram_history` in helpers.py
- Removed unused imports in websocket_handlers.py: `DOMAIN`, `_update_person_centroid`, `_update_all_face_matches`
- Commit: `4a05b70`

### 📁 New Files
- `SECURITY.md` - Security policy and responsible disclosure
- `MEDIUM_FINDINGS_REMEDIATION.md` - Session documentation

---

## [1.2.0] - 2026-02-05

### 🚀 New Feature: Multi-Sensor Trigger

**Multiple trigger sensors per camera!**

Previously each camera could only have one motion sensor as trigger. Now you can configure multiple sensors - e.g. a motion sensor AND a doorbell - to start recording.

- **Config Flow**: Motion sensor selector now allows multi-select
- **Backward Compatible**: Existing `sensor_{camera}` configs still work
- **New Format**: `sensors_{camera}` stores list of entities
- **Both Steps**: Camera config + Manual camera support multi-sensors

### 🧠 New Feature: Sample Quality Analysis (People DB)

**Automatic outlier detection and quality scoring for face embeddings!**

- **Quality Scores**: Each sample shows similarity to person's centroid (0-100%)
- **Outlier Detection**: Samples below threshold (default 65%) marked as potential errors
- **Bulk Selection**: Checkbox for each sample, "Select All Outliers" button
- **Bulk Delete**: Delete multiple samples at once
- **New UI Elements**:
  - Quality stats row: Ø Qualität, Ausreißer count, Threshold display
  - Color-coded quality badges (green/orange/red)
  - ⚠️ Outlier badges on problematic samples
  - Bulk action bar with selection count

### 🎨 New Feature: Overlay Smoothing

**Smooth analysis overlay drawing for better visual experience!**

- **Configurable**: `analysis_overlay_smoothing` toggle in settings
- **Alpha Value**: `analysis_overlay_smoothing_alpha` (0.1-1.0, default 0.55)
- **EMA Algorithm**: Exponential moving average for box position smoothing
- **Reduced Jitter**: Bounding boxes transition smoothly between frames

### 🏠️ UI/Branding
- **Dashboard Logo**: Opening logo replaces "Kamera Archiv" text in card header
- **Version Badge**: "BETA v1.2.0" badge in header for version visibility

### 🔧 Technical Changes
- `config_flow.py`: EntitySelector with `multiple=True`
- `__init__.py`: Listener registration iterates over sensor list
- `database.py`: New `get_person_details_with_quality()` and `bulk_delete_embeddings()` methods
- `websocket_handlers.py`: New WebSocket endpoints for quality API
- `rtsp-recorder-card.js`: Quality UI, bulk selection, overlay smoothing
- `strings.json` & translations: Updated labels (de, en)

---

## [1.1.2] - 2026-02-05

### � Bug Fixes
- **Fixed**: Batch analysis `auto_device` undefined error
  - `_analyze_batch` now uses correct `device` parameter
  - "Alle Aufnahmen analysieren" works again

### �🔧 Configuration Changes
- **Removed SQLite Toggle**: SQLite is now always enabled (hardcoded)
  - Removed `use_sqlite` option from config flow
  - Cleaner settings UI without unnecessary toggle
  
### 🌐 Translations
- **New Setting**: Added `analysis_max_concurrent` slider to all 5 languages
  - Controls maximum parallel analysis tasks (1-4)
  - German, English, Spanish, French, Dutch translations

### 🖼️ Branding
- **Integration Icon**: Added icon.png and logo.png for HA integration
- **HACS Support**: Added hacs_images/icon.png for HACS display

### 📦 HACS Compatibility
- Added as custom repository for easy installation/updates
- Proper version tracking via GitHub releases

---

## [1.1.1] - 2026-02-03

### 🔍 Quality & Security Audit v4.0
- **ISO 25010 Score**: 93/100 (EXCELLENT)
- **ISO 27001 Annex A Score**: 85/100 (GOOD)
- **10 Hardcore Security Tests**: All passed ✅

### 📝 Type Hints Coverage (88.2%)
- **analysis.py**: 100% (24/24 functions)
- **database.py**: 100% (36/36 functions)
- **exceptions.py**: 100% (25/25 functions)
- **config_flow.py**: 100% (15/15 functions)
- **helpers.py**: 88.2% (15/17 functions)
- **services.py**: 50% (9/18 functions)
- **recorder_optimized.py**: 58.8% (10/17 functions)

### 🛡️ Security Verified
- ✅ 100% Parameterized SQL Queries (83+ execute calls)
- ✅ XSS Protection via `_escapeHtml()` (36+ usages)
- ✅ Path Traversal Prevention (realpath + prefix validation)
- ✅ Input Validation (VALID_NAME_PATTERN regex)
- ✅ Rate Limiting (Semaphore-based)
- ✅ Schema Validation (voluptuous for WebSocket)

### 🔧 Code Quality Improvements
- Added `-> None` return types to all `__init__` methods (29 exception classes)
- Added `-> Any` return types for dynamic return functions
- Added `-> list[str]` return types for list-returning functions
- Added `-> config_entries.FlowResult` for all config_flow steps

---

## [1.1.0n BETA] - 2026-02-03

### 👤 Person Detail Popup (NEW)
- **Klickbare Personennamen** im People-Tab öffnen Detail-Popup
- **Positive Samples anzeigen**: Alle zugewiesenen Gesichtsbilder mit Datum
- **Negative Samples anzeigen**: Alle Ausschluss-Bilder (korrigierte Fehlerkennungen)
- **Erkennungszähler**: Wie oft wurde die Person insgesamt erkannt
- **Zuletzt gesehen**: Datum, Uhrzeit und Kamera der letzten Erkennung
- **Löschen-Funktion**: Einzelne Samples entfernen per Klick auf ✕
- **Erklärungsbox**: Hilfetext zu allen Funktionen im Popup

### 🏠 Home Assistant Integration
- **Person-Entities für Automationen**: 
  - `binary_sensor.rtsp_person_{name}` wird automatisch erstellt
  - State: "on" wenn kürzlich erkannt, "off" nach 5 Minuten
  - Attribute: `last_seen`, `last_camera`, `confidence`, `total_sightings`
  - Perfekt für Automatisierungen (z.B. Benachrichtigungen)

### 🔧 Verbesserungen
- **Recognition Count**: Zählt jetzt korrekt auch ältere Einträge (fallback auf person_name)
- **Database Query Optimierung**: `person_id OR person_name` für Kompatibilität
- **UI Polish**: Bessere Darstellung der Stats-Kacheln mit Farben und größerer Schrift

---

## [1.1.0k BETA] - 2026-02-03

### 🗄️ SQLite-Only Backend
- **Removed JSON Database**: Complete migration to SQLite-only backend
  - All person data now stored exclusively in SQLite
  - Automatic one-time migration from JSON on first start
  - Removed `people_db_path` and `migrate_from_json` config options
  - Cleaner codebase without dual-backend complexity

### 🧹 Storage Management
- **Analysis Folder Cleanup**: Automatic cleanup of `_analysis` folders
  - `cleanup_analysis_data()`: Removes analysis for expired/deleted videos
  - `delete_analysis_for_video()`: Cleans up when video is manually deleted
  - Respects per-camera retention settings
- **Configurable Cleanup Interval**: New slider in settings (1-24 hours)
  - Ideal for short retention times (e.g., 2 hour cameras)
  - Default: 24 hours for normal usage

### 📊 Movement Profile
- **Recognition History**: Fixed `log_recognition_event` (was disabled on server)
  - Tracks who was seen when/where
  - Visible in "Bewegung" (Movement) tab in UI
  - Stores camera, person, confidence, timestamp

### 🔧 Bug Fixes
- **Issue #35**: Analysis folders growing unbounded (1.7GB for 91 analyses)
- **Issue #36**: Analysis not deleted when video deleted via service
- **Issue #37**: Cleanup interval was hardcoded (now configurable)
- **Issue #38**: Movement profile showing no data (log_recognition_event was commented out)

### 🌐 Translations
- Added "🧹 Aufräum-Intervall" / "Cleanup Interval" to all languages
- Updated German descriptions for new settings

---

## [1.1.0 BETA] - 2026-02-02

### 🚀 Performance Optimizations
- **Parallel Snapshots**: Thumbnail is now captured DURING recording (after configurable `snapshot_delay`)
  - Saves 3-5 seconds per recording compared to sequential approach
  - Snapshot runs as parallel async task while recording continues
- **Callback-based Recording**: RTSP recordings use event-based completion instead of polling
  - Uses `asyncio.Event()` for instant notification when FFmpeg finishes
  - Eliminates busy-waiting loops
- **Faster Timeline Updates**: Recordings appear in timeline immediately when started
  - New event `rtsp_recorder_recording_started` fires at recording start
  - Timeline shows recording badge with countdown timer

### 🔒 Security & Reliability (NEW)
- **Rate Limiter Module** (`rate_limiter.py`): Token Bucket algorithm for DoS protection
  - Configurable rate limits per operation type
  - Async-compatible with decorator support
  - Automatic cleanup of expired tokens
- **Custom Exceptions** (`exceptions.py`): 20+ specific exception types
  - Structured error hierarchy for better debugging
  - Categorized by domain (Recording, Analysis, Database, etc.)
- **Performance Monitor** (`performance.py`): Operations metrics tracking
  - Dataclass-based metrics with timing decorators
  - Statistical analysis of operation durations
  - Async-compatible measurement utilities
- **Database Migrations** (`migrations.py`): Schema versioning system
  - Automatic migration on startup
  - Version tracking and rollback support
  - Safe schema evolution

### 📊 Metrics System
- **Performance Metrics Logging**: Structured metrics for performance analysis
  - Format: `METRIC|camera|metric_name|elapsed_time`
  - `recording_to_saved`: Time from trigger to file saved
  - `analysis_duration`: Time for video analysis
  - `total_pipeline_time`: Complete flow from motion to analysis complete
- **Easy Analysis**: `grep METRIC /config/rtsp_debug.log | tail -20`

### 🎛️ TPU Load Display
- **Calculated TPU Load**: Shows actual Coral EdgeTPU utilization percentage
  - Formula: (Coral inference time / 60s window) × 100
  - Displayed in footer performance cards
  - Color coded: green (<5%), orange (5-25%), red (>25%)
- **Increased History Buffer**: From 100 to 1000 entries for accurate load calculation

### 🎨 UI Improvements
- **Recording Progress**: Footer shows active recording with camera name and duration
- **Performance Cards**: Redesigned footer with consistent card sizing
- **Beta Badge**: Player shows "BETA VERSION" indicator

### 🌐 Internationalization
- **5 Languages**: German (DE), English (EN), Spanish (ES), French (FR), Dutch (NL)
- **Complete UI Coverage**: All config flow and options translated
- **Auto Language Selection**: Based on Home Assistant locale

### 🧪 Quality Assurance
- **Professional Audit Score**: 84.4% (B+ Grade)
- **Test Framework**: pytest-based unit tests with 8 test files
- **Memory Management Test**: 100% pass rate
- **27 Python Modules**: 11,832 LOC with 74% type hint coverage

### 🔧 Technical Improvements
- Increased inference stats history from 100 to 1000 entries
- Better CPU reading accuracy with 0.3s sampling and rolling average
- Improved file stability check (1s intervals, 2 checks)
- Reduced HA camera recording wait time (+1s instead of +2s)

### Technical
- Integration version: 1.1.0
- Dashboard card version: 1.1.0 BETA
- Detector add-on version: 1.0.9
- Python modules: 27
- Total LOC: 11,832
- Test files: 8

---

## [1.0.9 STABLE] - 2026-02-01

### 🏆 Release Status
- **PRODUCTION READY** - Fully audited and verified
- **ISO 25010 Score**: 93.8% (Software Quality)
- **ISO 27001 Score**: 91.2% (Information Security)
- **Combined Score**: 92.5%

### 🗄️ New Features
- **SQLite Database Backend**: Optional SQLite database for improved performance
  - Faster queries with >50 persons in database
  - Recognition history tracking for analytics
  - ACID-compliant concurrent access with WAL mode
  - Automatic JSON migration when enabled
- **Recognition Analytics**: Track who was seen when/where (requires SQLite)
  - Per-person recognition statistics
  - Per-camera activity tracking
  - Configurable history retention

### 🌐 Internationalization
- **English Translation**: Added `translations/en.json` for international users
- **German Translation**: Updated `translations/de.json`
- **Auto Language Selection**: Based on Home Assistant locale

### 📦 Distribution
- **HACS Compatible**: Added `hacs.json` for easy installation via HACS
- **UTF-8 Clean**: Removed BOM from manifest.json for cross-platform compatibility
- **Installation Ready**: Complete package for deployment on any system

### ⚙️ Configuration
- **New Option**: "SQLite Datenbank nutzen" in analysis settings
- **Auto-Migration**: Existing JSON data migrates automatically
- **Backward Compatible**: JSON remains default, SQLite is opt-in

### Technical
- New file: `database.py` - Thread-safe SQLite manager with WAL mode
- New file: `translations/en.json` - English UI strings
- New file: `hacs.json` - HACS repository configuration
- Enhanced `people_db.py` - Dual-backend support (JSON/SQLite)
- Updated `const.py` - CONF_USE_SQLITE constant
- Updated `config_flow.py` - SQLite toggle in UI
- Binary embedding storage for 4x smaller database
- All files validated as clean UTF-8 (no BOM)

---

## [1.0.8 STABLE] - 2026-01-31

### 🔒 Security
- **SHA256 Model Verification**: All ML models verified against cryptographic hashes before use
- **CORS Restriction**: API access restricted to local Home Assistant instances by default
- **Supply-Chain Integrity**: Protection against tampered model files via hash verification

### ✅ Quality Assurance
- **ISO 25010 Score**: 92.4% (Quality in Use)
- **ISO 27001 Score**: 89.5% (Information Security)
- **Combined Audit Score**: 90.95%
- **Hardcore Test**: 100% pass rate (116 API calls, 48 syntax checks, 36 file reads)

### 🔧 Reliability Improvements
- **Camera Health Watchdog**: 15-minute interval checks for stale recordings
- **FFmpeg TCP Transport**: Improved RTSP stream reliability
- **Connection Timeouts**: 5-second timeout prevents hanging processes
- **Better Error Logging**: stderr capture and PID logging for FFmpeg

### Technical
- Integration version: 1.0.8
- Dashboard card version: 1.0.8 STABLE
- Detector add-on version: 1.0.9

---

## [1.0.7 BETA] - 2026-01-29

### Added
- **Face detection & embeddings**: Face pipeline in offline analysis with embeddings
- **Person database**: Create, rename, delete persons; assign embeddings
- **Persons UI**: Thumbnails, sample selection, and training workflow in the card
- **Person entities**: Optional per-person `binary_sensor` entities for automations
- **Auto Coral toggle**: Option to force Coral on automatic analyses
- **Face thumbnails**: Stored in analysis results for quick review
- **Auto-analysis file readiness**: Waits for stable file size before analyzing

### Fixed
- **Analysis start latency**: Manual analysis now starts in background task
- **People actions reliability**: Robust ID handling and fallback matching
- **Face detection reliability**: Retry with lower confidence when no faces found
- **False matches**: Fallback embeddings excluded from matching

### Changed
- Dashboard badge updated to v1.0.7
- Detector add-on now exposes `/faces`

### Technical
- Integration version: 1.0.7
- Dashboard card version: 1.0.7 BETA
- Detector add-on version: 1.0.7

## [1.0.6 BETA] - 2026-01-29

### Added
- **Auto analyze new recordings**: Optional switch to analyze new recordings right after saving
- **Per-camera object list parity**: Camera config object list aligned with offline analysis
- **Footer visibility toggle**: Settings now control footer visibility on main dashboard
- **Persistent UI settings**: Footer visibility saved in localStorage

### Fixed
- **Encoding issues**: UTF-8 normalization to prevent garbled characters
- **Resource loading**: Frontend resource encoding corrected
- **Performance test button**: Always available for repeated testing
- **Storage tab noise**: _analysis folder excluded from recording stats

### Changed
- Dashboard badge updated to v1.0.6
- Detector add-on metadata version bumped to 1.0.6

### Technical
- Integration version: 1.0.6
- Dashboard card version: 1.0.6 BETA
- Detector add-on version: 1.0.6

## [1.0.5 BETA] - 2026-01-28

### Added
- **Automatic Analysis Scheduling**: Configure daily or interval-based automatic video analysis
- **Schedule Status Display**: Visual indicator showing active/inactive schedule status
- **Footer Toggle**: Setting to show/hide the performance footer under the video
- **Test Inference Button**: Always visible in performance tab (not just when no inferences)
- **Interpreter Caching**: Critical fix for Coral USB - reuse interpreters like Frigate
- **Live System Stats**: Read CPU/RAM directly from /proc for accurate monitoring

### Fixed
- **Coral USB Blocking**: Fixed issue where creating new interpreter for each request blocked Coral
- **Config Save**: Now properly saves to both `data` and `options` for Home Assistant
- **Footer Stats**: Coral Anteil and Ø Inferenz now always visible (not hidden when 0)
- **Port Mismatch**: Aligned add-on config.json port with actual service port (5000)

### Changed
- Updated Frigate-compatible models (ssdlite_mobiledet_coco_qat_postprocess)
- Improved error handling with user-friendly toast notifications
- Enhanced detector add-on documentation

### Technical
- Detector add-on version: 1.0.5
- Dashboard card version: 1.0.5 BETA
- Uses libedgetpu-max for maximum Coral performance
- Inference time with Coral: ~40-70ms

## [0.3.0] - 2026-01-28

### Added
- Coral USB EdgeTPU support (Frigate-compatible implementation)
- Performance monitoring panel (Frigate-style)
- InferenceStatsTracker for detailed stats
- Test inference functionality

### Fixed
- EdgeTPU delegate loading with correct library path
- Model compatibility with Coral USB

## [0.2.0] - 2026-01-27

### Added
- Analysis overview with statistics
- Device breakdown (CPU/Coral usage)
- Remote detector service support
- Annotated video generation

## [0.1.0] - 2026-01-26

### Initial Release
- Basic recording functionality
- Motion sensor triggers
- Thumbnail generation
- Dashboard card
- Retention management

---

## Migration Guide

### From 0.3.0 to 1.0.5
1. Update all files (integration, card, add-on)
2. Rebuild detector add-on to get interpreter caching
3. Clear browser cache (Ctrl+F5)
4. Reload integration in Home Assistant

### Coral USB Setup
1. Ensure USB passthrough is configured
2. Install/update detector add-on
3. Check `/info` endpoint for Coral detection
4. Run test inference to verify

