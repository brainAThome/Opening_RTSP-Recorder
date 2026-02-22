# Opening RTSP Recorder - Release History

Quick overview of all releases with links to detailed changelogs.

📋 **[Full CHANGELOG](../CHANGELOG.md)** for detailed information on each release.

---

## Latest: v1.3.4 (February 22, 2026)

**Mobile Video Fix - Confirmed**

- ✅ Version bump after confirming mobile video loading fix works in production

---

## v1.3.3 (February 22, 2026)

**Mobile Video Loading Root Cause Fix**

- 📱 Fixed: Videos now load instantly on mobile devices
- 🔧 Post-recording remux: fMP4 → regular MP4 with faststart (<1s, no re-encoding)
- 🌐 New video streaming endpoint with HTTP Range/206 support
- 🎴 Dashboard card uses custom video endpoint with fallback
- 📦 497 existing fragmented videos batch-migrated

---

## v1.3.2 (February 15, 2026)

**Mobile Video UX Improvement**

- 🖼️ Poster frame shown while video loads
- ⏳ Loading spinner during buffering
- 🎬 Video controls shown after `canplay` event

---

## v1.3.1 (February 8, 2026)

**Debug Mode Bugfix Release**

- 🐛 Fixed: Performance panel visibility when toggling Debug Mode

---

## v1.3.0 (February 7, 2026)

**Rebranding Release**

- 🏷️ Unified "Opening RTSP Recorder" branding
- 🌍 All 5 translations updated (DE, EN, FR, ES, NL)

---

## v1.2.9 (February 7, 2026)

**Initial Rebranding**

- 🏷️ Integration name changed to "Opening RTSP Recorder"

---

## v1.2.8 (February 7, 2026)

**Debug Mode Feature**

- 🔧 Debug Mode toggle to hide/show technical displays
- 📊 Hides FPS, Performance panel when disabled

---

## v1.2.7 (February 7, 2026)

**Smart Auto-Update**

- 🔄 MD5 hash comparison for card updates
- ✅ Reliable auto-update via HACS

---

## v1.2.6 (February 7, 2026)

**Auto-Install Dashboard Card**

- 🚀 Card bundled with integration
- 📦 Auto-copied to `/config/www/`

---

## v1.2.5 (February 7, 2026)

**FPS Detection Fix**

- 🎥 Correct FPS metadata via ffprobe
- 📺 Fixes 20 FPS cameras showing ~28 FPS

---

## v1.2.4 (February 7, 2026)

**Dynamic Path Loading**

- 🐛 Thumbnail path now read dynamically
- ⚡ No restart needed after config change

---

## v1.2.3 (February 7, 2026)

**Type Hints Complete**

- ✅ 100% Type Hints (129 functions)
- 🔧 Stats display fix for Coral TPU
- 📲 Push notifications for person detection

---

## v1.2.2 (February 6, 2026)

**Mobile & Stats**

- 📱 Mobile portrait view
- 📊 Statistics reset button
- 🐛 Recording indicator fix

---

## v1.2.1 (February 5, 2026)

**Code Quality**

- 🛠️ Cyclomatic Complexity: CC 140→23 (-84%)
- 🔒 SECURITY.md with biometric policy
- 📈 ISO 25010: 96/100

---

## v1.2.0 (February 5, 2026)

**Quality Analysis & Multi-Sensor**

- 🧠 Sample Quality Analysis with outlier detection
- 🚀 Multi-Sensor Trigger (motion + doorbell)
- 🎨 Overlay Smoothing (EMA algorithm)
- 🖼️ Opening logo branding

---

## v1.1.x (February 3-4, 2026)

**Person Entities & Popup**

- 👤 Person Detail Popup with samples
- 🏠 HA Person Entities (`binary_sensor.rtsp_person_*`)
- 🧹 Automatic analysis cleanup
- ⚡ Rate Limiter, 20+ Custom Exceptions

---

## v1.0.9 (February 1, 2026)

**SQLite Backend - STABLE**

- 💾 SQLite with WAL mode
- 📊 Recognition Analytics
- 🔄 Auto-migration from JSON
- ✅ ISO 25010: 93.8%, ISO 27001: 91.2%

---

## v1.0.8 (February 1, 2026)

**Modular Architecture - STABLE**

- 📦 13 modular Python files
- 🔒 Security hardening
- 🌍 German localization

---

## v1.0.7 (January 30, 2026)

**Face Detection**

- 🙂 128-dimensional face embeddings
- 👤 Person training via UI
- 🔄 Automatic re-matching

---

## v1.0.6 (January 28, 2026)

**Initial Features**

- 🎥 Auto-analyze recordings
- 📁 Per-camera object list
- 🦶 Footer visibility toggle
- 🔧 UTF-8 encoding fixes

---

📋 **[Full CHANGELOG](../CHANGELOG.md)** | 📊 **[Audit Report v1.3.1](FINAL_AUDIT_REPORT_v1.3.1.md)**
