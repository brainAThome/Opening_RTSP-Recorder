# Changelog

All notable changes to RTSP Recorder will be documented in this file.

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

