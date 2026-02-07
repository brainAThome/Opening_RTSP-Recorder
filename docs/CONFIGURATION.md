# ⚙️ RTSP Recorder - Configuration Reference

> 🇩🇪 **[Deutsche Version / German Version](CONFIGURATION_DE.md)**

**Version:** 1.2.2  
**Last Updated:** February 7, 2026

---

## Table of Contents

1. [Basic Configuration](#1-basic-configuration)
2. [Camera Settings](#2-camera-settings)
3. [Analysis Options](#3-analysis-options)
4. [Face Recognition](#4-face-recognition)
5. [Automatic Analysis](#5-automatic-analysis)
6. [Performance Settings](#6-performance-settings)
7. [Advanced Options](#7-advanced-options)
8. [Example Configurations](#8-example-configurations)

---

## 1. Basic Configuration

### Storage Paths

| Option | Default | Description |
|--------|---------|-------------|
| `storage_path` | `/media/rtsp_recorder/ring_recordings` | Recording storage location |
| `snapshot_path` | `/media/rtsp_recorder/thumbnails` | Thumbnail storage location |
| `analysis_output_path` | `/media/rtsp_recorder/ring_recordings/_analysis` | Analysis results |

### Retention

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| `retention_days` | 7 | 1-365 | Keep recordings (days) |
| `retention_hours` | 0 | 0-23 | Additional hours |
| `snapshot_retention_days` | 7 | 1-365 | Keep thumbnails (days) |

**Example:**
```yaml
retention_days: 14
retention_hours: 12
# = 14 days and 12 hours
```

### Database

| Option | Default | Description |
|--------|---------|-------------|
| `use_sqlite` | `false` | SQLite instead of JSON for people DB |

**Recommendation:** Enable SQLite with >20 persons for better performance.

---

## 2. Camera Settings

### Available Per Camera

| Option | Format | Description |
|--------|--------|-------------|
| `sensor_{Camera}` | Entity ID | Motion sensor for trigger |
| `duration_{Camera}` | Seconds | Recording duration |
| `snapshot_delay_{Camera}` | Seconds | Delay for thumbnail |

### Example

```yaml
# Camera: Living Room
sensor_LivingRoom: binary_sensor.living_room_motion
duration_LivingRoom: 90
snapshot_delay_LivingRoom: 4

# Camera: Front Door
sensor_FrontDoor: binary_sensor.front_door_motion
duration_FrontDoor: 120
snapshot_delay_FrontDoor: 3
```

### Recommended Recording Durations

| Camera Type | Recommendation | Reason |
|-------------|----------------|--------|
| Indoor | 60-90s | Typical activity duration |
| Entrance/Hallway | 30-60s | Short transit times |
| Outdoor | 120-180s | Longer paths |
| Front Door | 90-120s | Package pickup etc. |

---

## 3. Analysis Options

### Basic Analysis

| Option | Default | Description |
|--------|---------|-------------|
| `analysis_enabled` | `true` | Analysis feature active |
| `analysis_detector_url` | `http://local-rtsp-recorder-detector:5000` | Detector endpoint |
| `analysis_device` | `coral_usb` | Inference hardware |

### Available Devices

| Value | Hardware | Speed |
|-------|----------|-------|
| `coral_usb` | Google Coral USB | ~50ms/frame |
| `coral_pcie` | Google Coral PCIe | ~30ms/frame |
| `cpu` | CPU (fallback) | ~500ms/frame |

### Object Detection

| Option | Default | Description |
|--------|---------|-------------|
| `analysis_detector_confidence` | 0.5 | Global confidence threshold |
| `analysis_frame_interval` | 2 | Every X-th frame analyzed |
| `analysis_objects` | List | Objects to detect |

### Available Objects

```yaml
analysis_objects:
  - person        # Persons
  - car           # Cars
  - truck         # Trucks
  - bicycle       # Bicycles
  - motorcycle    # Motorcycles
  - dog           # Dogs
  - cat           # Cats
  - bird          # Birds
  - package       # Packages
  - backpack      # Backpacks
  - suitcase      # Suitcases
  - bottle        # Bottles
  - cup           # Cups
  - chair         # Chairs
  - couch         # Couches
  - bed           # Beds
  - tv            # TVs
  - laptop        # Laptops
  - cell phone    # Cell phones
  - book          # Books
  - potted plant  # Plants
  - umbrella      # Umbrellas
  - remote        # Remotes
  - dining table  # Dining tables
```

### Per-Camera Objects

```yaml
# Only specific objects per camera
analysis_objects_LivingRoom:
  - person
  - dog
  - cat
  - remote
  - book

analysis_objects_FrontDoor:
  - person
  - package
  - car
  - bicycle
```

### Per-Camera Confidence

```yaml
# Higher confidence for well-lit rooms
detector_confidence_LivingRoom: 0.6
detector_confidence_Hallway: 0.4
detector_confidence_Garden: 0.5
```

---

## 4. Face Recognition

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| `analysis_face_enabled` | `false` | true/false | Face detection active |
| `analysis_face_confidence` | 0.2 | 0.1-0.9 | Face detection threshold |
| `analysis_face_match_threshold` | 0.35 | 0.2-0.6 | Matching threshold |
| `person_entities_enabled` | `false` | true/false | HA entities per person |

### Recommended Settings

| Scenario | face_confidence | match_threshold |
|----------|-----------------|-----------------|
| Standard | 0.2 | 0.35 |
| High accuracy | 0.3 | 0.30 |
| Difficult lighting | 0.15 | 0.40 |
| Many similar persons | 0.2 | 0.28 |

---

## 5. Automatic Analysis

### Scheduling Options

| Option | Default | Description |
|--------|---------|-------------|
| `analysis_auto_enabled` | `false` | Auto-analysis active |
| `analysis_auto_mode` | `daily` | Mode: `daily` or `interval` |
| `analysis_auto_time` | `03:00` | Time (for daily) |
| `analysis_auto_interval_hours` | 24 | Interval in hours |

### Filter Options

| Option | Default | Description |
|--------|---------|-------------|
| `analysis_auto_since_days` | 1 | Recordings from last X days |
| `analysis_auto_limit` | 50 | Max recordings per run |
| `analysis_auto_skip_existing` | `true` | Skip already analyzed |
| `analysis_auto_new` | `true` | Only analyze new recordings |

### Example: Daily Analysis at 3 AM

```yaml
analysis_auto_enabled: true
analysis_auto_mode: daily
analysis_auto_time: "03:00"
analysis_auto_since_days: 1
analysis_auto_limit: 100
analysis_auto_skip_existing: true
```

### Example: Every 6 Hours

```yaml
analysis_auto_enabled: true
analysis_auto_mode: interval
analysis_auto_interval_hours: 6
analysis_auto_limit: 25
```

---

## 6. Performance Settings

### Hardware Monitoring

| Option | Default | Description |
|--------|---------|-------------|
| `analysis_perf_cpu_entity` | `null` | CPU sensor entity |
| `analysis_perf_coral_entity` | `null` | Coral temperature entity |
| `analysis_perf_igpu_entity` | `null` | iGPU entity (optional) |

### Recommended System Sensors

```yaml
# System Monitor Integration
sensor:
  - platform: systemmonitor
    resources:
      - type: processor_use
      - type: memory_use_percent
      - type: disk_use_percent
        arg: /

# Coral USB Temperature (if available)
analysis_perf_coral_entity: sensor.coral_temperature
```

---

## 7. Advanced Options

### Internal Settings

These options typically don't need changing:

| Option | Default | Description |
|--------|---------|-------------|
| Frame Stability Check | 1s, 2 checks | Wait time for stable files |
| Inference History | 1000 entries | Buffer for TPU load calculation |
| Rate Limiter | Token Bucket | DoS protection for API |

### Debug Logging

In `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.rtsp_recorder: debug
```

### Enable Metrics

Metrics are automatically logged:
```bash
# Display
grep METRIC /config/home-assistant.log | tail -20

# Format
METRIC|camera_name|metric_type|value
METRIC|LivingRoom|recording_to_saved|32.1s
METRIC|LivingRoom|analysis_duration|6.2s
```

---

## 8. Example Configurations

### Minimal (Recording Only)

```yaml
storage_path: /media/rtsp_recorder/recordings
snapshot_path: /media/rtsp_recorder/thumbnails
retention_days: 7

sensor_LivingRoom: binary_sensor.living_room_motion
duration_LivingRoom: 60

analysis_enabled: false
```

### Standard (with Analysis)

```yaml
storage_path: /media/rtsp_recorder/recordings
snapshot_path: /media/rtsp_recorder/thumbnails
retention_days: 14

# Cameras
sensor_LivingRoom: binary_sensor.living_room_motion
duration_LivingRoom: 90
snapshot_delay_LivingRoom: 4

sensor_FrontDoor: binary_sensor.front_door_motion
duration_FrontDoor: 120
snapshot_delay_FrontDoor: 3

# Analysis
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

### Complete (All Features)

```yaml
# Storage
storage_path: /media/rtsp_recorder/recordings
snapshot_path: /media/rtsp_recorder/thumbnails
analysis_output_path: /media/rtsp_recorder/analysis
retention_days: 30
snapshot_retention_days: 14
use_sqlite: true

# Cameras
sensor_LivingRoom: binary_sensor.living_room_motion
duration_LivingRoom: 90
snapshot_delay_LivingRoom: 4
analysis_objects_LivingRoom: [person, dog, cat, remote]
detector_confidence_LivingRoom: 0.6

sensor_FrontDoor: binary_sensor.front_door_motion
duration_FrontDoor: 120
snapshot_delay_FrontDoor: 3
analysis_objects_FrontDoor: [person, package, car, bicycle]
detector_confidence_FrontDoor: 0.5

sensor_Garden: binary_sensor.garden_motion
duration_Garden: 180
snapshot_delay_Garden: 5
analysis_objects_Garden: [person, car, dog, bird]

# Analysis
analysis_enabled: true
analysis_detector_url: http://local-rtsp-recorder-detector:5000
analysis_device: coral_usb
analysis_detector_confidence: 0.5
analysis_frame_interval: 2
analysis_objects: [person, car, dog, cat, package]

# Face Recognition
analysis_face_enabled: true
analysis_face_confidence: 0.2
analysis_face_match_threshold: 0.35
person_entities_enabled: true

# Auto-Analysis
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

## See Also

- 📖 [User Guide](USER_GUIDE.md)
- 🚀 [Installation](INSTALLATION.md)
- 🧠 [Face Recognition](FACE_RECOGNITION.md)
- 🔧 [Troubleshooting](TROUBLESHOOTING.md)

---

*For problems: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
