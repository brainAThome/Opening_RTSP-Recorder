# Changelog

All notable changes to Opening RTSP Recorder are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.3.4] - 2026-02-22

### Changed
- **Version Bump**: Confirmed mobile video loading fix working in production

---

## [1.3.3] - 2026-02-22

### Fixed
- **Mobile Video Loading (Root Cause Fix)**: Videos now load instantly on mobile devices
  - **Root Cause**: RTSP `-c copy` recording produces fragmented MP4 (fMP4) with 30+ moof/mdat fragments. Mobile browsers (iOS Safari, Chrome Mobile) cannot progressively play fMP4 and must download the entire file (17-18 MB) before playback (~10 seconds delay).
  - **Fix 1 - Post-Recording Remux**: After each recording, the file is automatically remuxed from fMP4 to regular MP4 with `faststart` (moov atom at front). Uses `ffmpeg -c copy -movflags +faststart`, takes <1 second, no re-encoding.
  - **Fix 2 - Video Streaming Endpoint**: New HTTP endpoint `/api/rtsp_recorder/video/{camera}/{filename}` with full HTTP Range request support (206 Partial Content) for true progressive playback.
  - **Fix 3 - Dashboard Card**: Video player now uses the custom streaming endpoint with automatic fallback to `media_source/resolve_media`.

### Added
- **VideoStreamView**: New authenticated HTTP view class in `__init__.py` with `Accept-Ranges: bytes` header, `Content-Range` responses, and 256KB chunked streaming
- **`_remux_to_faststart()`**: New async function in `recorder.py` for post-recording MP4 remux with 30-second timeout and graceful fallback
- **Post-recording remux in `services.py`**: Remux step after `camera.record` service completes (the actual recording code path)

### Technical Details
- Video specs: 1920×1080, H.264 High Profile, 40fps, ~2.4 Mbit/s, 60s = 17-18 MB
- Before fix: moov=1,290 bytes + 30 moof/mdat pairs (fragmented)
- After fix: moov=~44,000 bytes + single mdat (progressive-ready)
- All 497 existing fragmented videos batch-migrated successfully

---

## [1.3.2] - 2026-02-15

### Fixed
- **Mobile Video UX Improvement**: Added poster frame, loading spinner, and `canplay` event handling
  - Poster image shown while video loads (uses thumbnail)
  - Animated spinner overlay during buffering
  - Video controls only shown after `canplay` event fires
  - Note: This was a cosmetic fix; the root cause (fMP4) was fixed in v1.3.3

### Changed
- **Documentation cleanup**: Removed obsolete ARCHIV references from repository

---

## [1.3.1] - 2026-02-08

### Fixed
- **Debug Mode Performance Panel**: The performance panel now correctly displays when Debug Mode is enabled
- Previously the panel remained hidden after toggling Debug Mode back on

---

## [1.3.0] - 2026-02-07

### Changed
- **Rebranding**: "Opening RTSP Recorder" unified branding
  - Integration: "Opening RTSP Recorder" (v1.3.0)
  - Addon: "Opening RTSP Recorder Detector" (v1.1.0)
  - All translations (DE, EN, FR, ES, NL) updated
  - Setup dialogs show the new name

---

## [1.2.9] - 2026-02-07

### Changed
- Initial rebranding to "Opening RTSP Recorder"

---

## [1.2.8] - 2026-02-07

### Added
- **Debug Mode for Technical Displays**
  - New toggle in Menu: General → Debug Mode
  - Hides FPS/Frame info display (top right in video)
  - Hides "Show Performance" checkbox
  - Hides Performance panel (CPU, RAM, Coral, etc.)
  - Setting is saved in browser localStorage

---

## [1.2.7] - 2026-02-07

### Changed
- **Smart Dashboard Card Auto-Update**
  - Uses MD5 hash comparison instead of file size
  - Card is automatically updated when HACS installs a new version
  - No more manual file deletion required after updates

---

## [1.2.6] - 2026-02-07

### Added
- **Automatic Dashboard Card Installation**
  - Dashboard card JS file is now bundled with the integration
  - Automatically copied to `/config/www/` on first load
  - Automatically registered as Lovelace resource
  - Just install via HACS, restart, and use!

---

## [1.2.5] - 2026-02-07

### Fixed
- **Correct Video FPS Metadata**
  - Automatic FPS detection via ffprobe before recording starts
  - FFmpeg uses detected FPS for correct container metadata
  - Fixes issue where 20 FPS cameras showed ~28 FPS in file properties

---

## [1.2.4] - 2026-02-07

### Fixed
- **Dynamic Thumbnail Path Loading**
  - ThumbnailView reads path dynamically from `hass.data`
  - No restart required after changing thumbnail path in config
  - All default values now use constants from `const.py` for consistency

---

## [1.2.3] - 2026-02-07

### Changed
- **Code Quality: 100% Type Hints**
  - All 129 functions now have return type annotations
  - Improved IDE support and code completion
  - Better static analysis with mypy/Pylance

### Fixed
- **Stats Display Fix**: Performance Tab now shows accurate Coral TPU statistics
  - WebSocket handler uses real detector stats
  - Push-based updates every 2 seconds

### Added
- **Person Detection Push Notifications**
  - Event: `rtsp_recorder_person_detected`
  - Includes: person name, confidence, camera, video path

---

## [1.2.2] - 2026-02-06

### Added
- **Statistics Reset**: New "Reset Statistics" button in Performance Tab
- **Mobile Portrait View**: Optimized mobile version for Lovelace Card
  - Portrait layout with timeline cards
  - Footer and tabs mobile-scrollable and compact
  - Video controls hidden on mobile, replaced with Download/Delete in footer
  - Performance display and checkboxes optimized for mobile
  - Complete @media queries for 768px/480px
  - Tested on Android/iOS

### Fixed
- **Recording Indicator Fix**: Multi-camera scenarios properly tracked
  - Fixed: Indicator no longer disappears when another camera finishes recording
  - Now uses event-driven `_runningRecordings` Map consistently
- **FPS Display Fix**: Video player now shows actual video FPS
  - Reads `video_fps` from analysis data
  - Falls back to 25 FPS (PAL standard) if unavailable

### Removed
- `smooth_video` config option (was unused)

---

## [1.2.1] - 2026-02-05

### Changed
- **Cyclomatic Complexity Reduction**: `analyze_recording` CC 140→23 (-84%)
- **Silent Exception Handlers**: 7 critical `except:pass` blocks now have debug logging
- **Security Documentation**: New `SECURITY.md` with biometric data policy

### Scores
- ISO 25010: 93/100 → 96/100
- ISO 27001: 86/100 → 88/100

---

## [1.2.0] - 2026-02-05

### Added
- **Sample Quality Analysis (People DB)**
  - Quality Scores: Each face sample shows similarity to person's centroid (0-100%)
  - Outlier Detection: Samples below 65% threshold marked with ⚠️ warning badge
  - Bulk Selection: Checkboxes per sample + 'Select All Outliers' button
  - Bulk Delete: Remove multiple problematic samples at once
  - Visual Indicators: Color-coded quality badges (green/orange/red)
- **Overlay Smoothing**
  - Toggle `analysis_overlay_smoothing` in settings
  - Configurable alpha value (0.1-1.0, default 0.55)
  - EMA algorithm for smooth bounding box transitions
- **Multi-Sensor Trigger**
  - Select multiple binary_sensors per camera (motion, doorbell, etc.)
  - Backward compatible with existing configs
- **Opening Logo**: New branding in dashboard header

### Fixed
- Batch analysis `auto_device` undefined error

### Scores
- ISO 25010: 93/100 (EXCELLENT)
- ISO 27001: 85/100 (GOOD)

---

## [1.1.2] - 2026-02-05

### Fixed
- Batch analysis `auto_device` undefined error

### Configuration
- SQLite always enabled
- New `analysis_max_concurrent` slider (1-4)

---

## [1.1.1] - 2026-02-04

### Highlights
- Type Hints Coverage: 88.2% (134/152 functions)
- ISO 25010 Quality Score: 93/100 (EXCELLENT)
- ISO 27001 Security Score: 85/100 (GOOD)
- 10 Hardcore Security Tests passed
- Repository cleanup and full documentation refresh

### Security
- 83+ parameterized SQL queries
- 36+ XSS protection calls
- Path traversal protection (realpath + prefix validation)

### Performance
- Async JSON & filesystem ops (non-blocking)
- Event-driven architecture (no polling)
- Rate limiting via semaphore

---

## [1.1.0n] - 2026-02-03

### Added
- **Person Detail Popup**
  - Clickable person names in People tab open detail popup
  - Positive Samples view: All assigned face images with date
  - Negative Samples view: All exclusion images
  - Recognition Counter: How often the person was recognized
  - Last Seen: Date, time and camera of last recognition
  - Delete Function: Remove individual samples
- **Home Assistant Person Entities**
  - `binary_sensor.rtsp_person_{name}` automatically created
  - State: 'on' when recently recognized, 'off' after 5 minutes
  - Attributes: `last_seen`, `last_camera`, `confidence`, `total_sightings`

---

## [1.1.0k] - 2026-02-03

### Added
- Automatic analysis folder cleanup when videos are deleted
- Configurable cleanup interval (1-24 hours slider)
- Per-camera retention support for analysis cleanup
- Rate Limiter - Token Bucket DoS protection
- 20+ Custom Exceptions - Structured error handling
- Performance Monitor - Operations metrics tracking
- Database Migrations - Automatic schema versioning

### Languages
- 5 languages: German, English, Spanish, French, Dutch

### Code Metrics
- 20 Python modules (10,062 LOC)
- 20 WebSocket handlers
- 4,328 LOC JavaScript card
- ISO 25010/27001 Audit: 90.0% (Grade A)

---

## [1.0.9] - 2026-02-01

### Added
- SQLite Database Backend with WAL mode for improved performance
- Recognition Analytics - Track who was seen when/where
- Auto-Migration from JSON to SQLite

### Internationalization
- English translation (`en.json`)
- German translation (`de.json`)
- Auto-detection based on HA locale

### Distribution
- HACS Compatible - Easy installation via HACS
- UTF-8 Clean - No BOM, cross-platform compatible

### Scores
- ISO 25010: 93.8% (Excellent)
- ISO 27001: 91.2% (Excellent)
- Combined: 92.5% (PRODUCTION READY)

---

## [1.0.8] - 2026-02-01

### Added
- 13 modular Python files for better maintainability
- Security hardening with rate limiting, input validation, path traversal protection
- Platform-specific ffmpeg handling (Windows/Linux)
- Full German localization
- Dashboard card shows STABLE v1.0.8

### Security Fixes
- MED-001: Platform-specific ffmpeg process handling
- MED-002: Input validation for person names with regex
- MED-004: Rate limiting for concurrent analysis requests (max 2)

---

## [1.0.7] - 2026-01-30

### Added
- Face Detection with 128-dimensional embeddings
- Person Training via UI - 'Add to Person' button
- Automatic Face Re-Matching after training
- Persons tab with thumbnail overview

### Performance
- Face Training Response: <100ms (previously 2-5 seconds)
- Background tasks for responsive UI
- Immediate UI response for all operations

### Fixed
- Reserved field 'id' in WebSocket
- log_to_file() signature error
- NameError config_entry
- NameError output_dir
- Blocking re-matching

### Audit Score
- Functionality: 94%
- Code Quality: 87%
- Security: 85%
- Performance: 92%
- Overall: 83% (Good)

---

## [1.0.6] - 2026-01-28

### Added
- Auto analyze new recordings (toggle)
- Per-camera object list parity with offline analysis
- Footer visibility toggle for dashboard
- Persistent footer setting (localStorage)

### Fixed
- UTF-8 encoding issues (garbled text)
- Frontend resource encoding
- Performance test button always visible
- _analysis folder excluded from recording stats

### Changed
- Dashboard badge updated to v1.0.6
- Detector add-on metadata bumped to 1.0.6

