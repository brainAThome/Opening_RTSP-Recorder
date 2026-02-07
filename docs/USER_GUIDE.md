# RTSP Recorder - User Guide

> 🇩🇪 **[Deutsche Version / German Version](USER_GUIDE_DE.md)**

**Version:** 1.2.2  
**Date:** February 2026  
**Compatibility:** Home Assistant 2024.1+

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Installation](#2-installation)
3. [Getting Started](#3-getting-started)
4. [Dashboard Card](#4-dashboard-card)
5. [Recordings & Timeline](#5-recordings--timeline)
6. [AI Analysis](#6-ai-analysis)
7. [Person Recognition](#7-person-recognition)
8. [Settings in Detail](#8-settings-in-detail)
9. [Automations](#9-automations)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-faq)

> 📚 **Additional Documentation:**
> - [Installation](INSTALLATION.md) - Detailed installation guide
> - [Configuration](CONFIGURATION.md) - All options explained
> - [Face Recognition](FACE_RECOGNITION.md) - Training & Matching
> - [Troubleshooting](TROUBLESHOOTING.md) - Problem solving

---

## 1. Introduction

RTSP Recorder is a comprehensive video surveillance solution for Home Assistant with AI-powered object detection and face recognition.

### What's New in v1.2.2?

| Feature | Description |
|---------|-------------|
| 📊 **Statistics Reset** | Reset detector statistics from UI |
| 🔴 **Recording Indicator Fix** | Multi-camera display fixed |
| 🎬 **FPS Display** | Shows actual video FPS |
| 📖 **Ring Privacy Docs** | Amazon data flow documentation |

### Main Features

| Feature | Description |
|---------|-------------|
| **Motion-triggered Recording** | Automatic recording on motion detection |
| **AI Object Detection** | Detection of persons, cars, animals etc. |
| **Face Recognition** | Training and recognition of known persons |
| **Coral USB Support** | Hardware-accelerated inference (~50ms vs ~600ms) |
| **Timeline View** | Visual overview of all recordings |
| **Retention Management** | Automatic cleanup of old recordings |

### System Requirements

- Home Assistant 2024.1 or newer
- Python 3.11+
- Optional: Google Coral USB Accelerator
- Storage space for recordings (recommended: min. 50 GB)

---

## 2. Installation

### 2.1 Installation via HACS (Recommended)

1. **Open HACS** in Home Assistant
2. Click **⋮** (three-dot menu) → **Custom repositories**
3. Enter repository URL:
   ```
   https://github.com/brainAThome/Opening_RTSP-Recorder
   ```
4. Category: **Integration**
5. Click **Add**
6. Search for "RTSP Recorder" and click **Download**
7. **Restart Home Assistant**

### 2.2 Manual Installation

1. **Copy integration:**
   ```
   custom_components/rtsp_recorder/ → /config/custom_components/rtsp_recorder/
   ```

2. **Copy dashboard card:**
   ```
   www/rtsp-recorder-card.js → /config/www/rtsp-recorder-card.js
   ```

3. **Add Lovelace resource:**
   
   Settings → Dashboards → Resources → Add Resource:
   ```yaml
   URL: /local/rtsp-recorder-card.js
   Type: JavaScript Module
   ```

4. **Restart Home Assistant**

### 2.3 Detector Add-on (Optional, for Coral USB)

The Detector Add-on enables hardware-accelerated AI analysis.

1. Copy `addons/rtsp-recorder-detector/` to `/addons/`
2. Settings → Add-ons → Add-on Store
3. Click **⋮** → **Repositories** (auto-detected)
4. Install "RTSP Recorder Detector"
5. Configure USB passthrough for Coral
6. Start the add-on

---

## 3. Getting Started

### 3.1 Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **"RTSP Recorder"**
4. Follow the configuration wizard

### 3.2 Configure First Camera

In the configuration wizard:

| Field | Description | Example |
|-------|-------------|---------|
| **Name** | Display name of camera | `Living Room` |
| **Camera Entity** | Home Assistant camera entity | `camera.living_room` |
| **RTSP URL** | Direct RTSP stream (optional) | `rtsp://192.168.1.100/stream` |
| **Motion Sensor** | Entity for motion detection | `binary_sensor.living_room_motion` |

### 3.3 Add Dashboard Card

1. Edit dashboard → **+ Add Card**
2. Choose **Manual** (YAML)
3. Add:

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recordings
thumb_path: /local/thumbnails
```

---

## 4. Dashboard Card

The dashboard card is the heart of the user interface.

### 4.1 Overview

The card shows:
- **Video player** with current/selected recording
- **Timeline** with thumbnails of all recordings
- **Camera selection** (dropdown)
- **Settings button** (gear icon)
- **Performance footer** (optional)

### 4.2 Navigation

| Element | Function |
|---------|----------|
| **Timeline thumbnails** | Click to play |
| **Left/right arrows** | Browse through recordings |
| **Camera dropdown** | Switch between cameras |
| **Date filter** | Filter recordings by date |
| **⚙️ Gear** | Open settings |

### 4.3 Video Controls

- **Play/Pause:** Click on video or Spacebar
- **Forward/Back:** Arrow keys or timeline
- **Fullscreen:** Double-click on video
- **Download:** Right-click → Save

---

## 5. Recordings & Timeline

### 5.1 Automatic Recording

Recordings are automatically created when:
1. The configured motion sensor switches to **ON**
2. The camera is available
3. No recording is already in progress

**Recording Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| Recording duration | 30 seconds | After motion ends |
| Snapshot delay | 2 seconds | For thumbnail |
| Format | MP4 (H.264) | Compatible with all browsers |

### 5.2 Manual Recording

**Via Service Call:**
```yaml
service: rtsp_recorder.save_recording
data:
  camera_name: living_room
  duration: 60  # Optional, in seconds
```

### 5.3 Delete Recordings

**Single recording:**
- Right-click on thumbnail → Delete
- Or via service call

**Multiple recordings:**
```yaml
service: rtsp_recorder.delete_all_recordings
data:
  camera_name: living_room  # Optional
  older_than_days: 7        # Optional
```

### 5.4 Retention (Storage Management)

Retention settings control how long recordings are kept.

**Global settings:**
- Recordings: X days
- Snapshots: X days
- Analysis data: X days

**Per-camera override:**
Each camera can have its own retention values that override the global ones.

---

## 6. AI Analysis

### 6.1 How It Works

AI analysis detects objects in recordings:

```
Video → Extract frames → Object detection → Save results
```

**Detectable Objects:**
- Person, Bicycle, Car, Motorcycle, Bus, Truck
- Dog, Cat, Bird, Horse
- And 70+ more COCO classes

### 6.2 Analysis Modes

| Mode | Description |
|------|-------------|
| **Manual** | Analyze single recording |
| **Auto-Analysis** | Automatically analyze new recordings |
| **Batch Analysis** | Analyze all/filtered recordings |
| **Schedule** | Daily automatic analysis |

### 6.3 Enable Auto-Analysis

1. Open **Settings** → **Analysis**
2. Enable **"Automatically analyze new recordings"**
3. Optional: **"Force Coral for auto-analysis"**

### 6.4 Batch Analysis

For retroactive analysis of all recordings:

1. Settings → Analysis
2. Click **"Analyze all"**
3. Optional: Set filters (camera, time period)
4. **"Skip already analyzed"** for efficiency

### 6.5 Analysis Schedule

Automatic analysis at specific times:

| Option | Description |
|--------|-------------|
| **Daily at** | Fixed time (e.g., 03:00) |
| **Every X hours** | Interval-based |

### 6.6 Detection Thresholds

Configurable per camera:

| Threshold | Description | Recommended |
|-----------|-------------|-------------|
| **Detector** | Minimum confidence for object detection | 0.5 - 0.7 |
| **Face** | Minimum confidence for face detection | 0.6 - 0.8 |
| **Match** | Minimum similarity for person match | 0.6 - 0.75 |

### 6.7 Object Filters

Choose which objects to detect per camera:

```
☑ Person  ☑ Car  ☐ Dog  ☐ Cat  ☐ Bicycle
```

Unchecked objects are ignored (saves resources).

---

## 7. Person Recognition

Face recognition enables identification of known persons.

### 7.1 Concept

```
Face detected → Create embedding → Compare with database → Identify person
```

**Terms:**
- **Embedding:** 1280-dimensional vector of a face
- **Positive Samples:** Images that BELONG to a person
- **Negative Samples:** Images that do NOT belong to a person

### 7.2 Create Person

1. Open **Settings** → **People**
2. Click **"+ Add Person"**
3. Enter a name (e.g., "Max")
4. Confirm with **OK**

### 7.3 Training from Analysis

Training is done via detected faces from analyses:

1. Select an **analyzed recording** from the dropdown
2. Click **"Load Analysis"**
3. Detected faces are displayed

**Assign face:**
- Select a person from the dropdown
- Click on an **unassigned image** → added directly
- The image is marked **green** (✓)

**Correct:**
- Click on an **already assigned (green) image**
- A **correction popup** appears
- Select the correct person or "Skip"

### 7.4 Negative Samples

Negative samples prevent false assignments.

**When to use?**
- When Person A is incorrectly recognized as Person B
- With similar-looking persons

**How to:**
1. Click on an image → Popup appears
2. Click on **❌** next to the wrong person
3. The image is marked as "Not this person"

**Threshold:** 75% - If a face has >75% similarity with a negative sample, it's excluded.

### 7.5 Recommendations for Good Training

| Recommendation | Reason |
|----------------|--------|
| **3-5 Positive Samples** per person | Different angles/lighting |
| **Prefer clear frontal shots** | Better embedding quality |
| **Negative Samples** for mix-ups | Prevents false positives |
| **Retrain regularly** | Improves accuracy over time |

### 7.6 Person Detail Popup

Click on a **person's name** in the People tab to open the detail popup.

**What does the popup show?**
- **Positive Samples:** All assigned face images with date
- **Negative Samples:** All exclusion images
- **Detections:** How often this person was detected
- **Last seen:** Date, time and camera of last detection

**Manage samples:**
- Click the red **✕** to delete individual samples
- Ideal for quality control of your training data

### 7.7 Person Entities for Automations

Create Home Assistant entities for detected persons:

1. Go to **Settings** → **RTSP Recorder** → **Configure**
2. Enable **Create Person Entities**

**Created entities:**
```yaml
binary_sensor.rtsp_person_max:
  state: "on"  # When recently detected
  attributes:
    last_seen: "2026-02-03T14:30:00"
    last_camera: "Living Room"
    confidence: 0.87
```

**Example Automation:**
```yaml
automation:
  - alias: "Max detected"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_max
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Max was seen at {{ trigger.to_state.attributes.last_camera }}"
```

> 📚 **More details:** See [Face Recognition](FACE_RECOGNITION.md#8-person-entities-for-automations)

### 7.8 Rename/Delete Person

- **Rename:** Click ✏️ next to the name
- **Delete:** Click 🗑️ → Confirm

⚠️ **Warning:** When deleting, all embeddings are permanently removed!

---

## 8. Settings in Detail

The settings are organized in 5 tabs:

### 8.1 Tab: General

| Setting | Description |
|---------|-------------|
| **Recording duration** | Seconds after motion ends (default: 30) |
| **Snapshot delay** | Seconds until thumbnail (default: 2) |
| **Show footer** | Performance display below video |

### 8.2 Tab: Storage

| Setting | Description |
|---------|-------------|
| **Keep recordings** | Days until automatic deletion |
| **Keep snapshots** | Days for thumbnail retention |
| **Keep analysis data** | Days for JSON results |
| **Per-camera settings** | Override for individual cameras |

**Storage display:**
- Total size of all recordings
- Number of files
- Breakdown by camera

### 8.3 Tab: Analysis

| Setting | Description |
|---------|-------------|
| **Detector URL** | Address of Detector add-on |
| **Auto-Analysis** | Automatically analyze new recordings |
| **Force Coral** | Use Coral USB for auto-analysis |
| **Schedule** | Automatic batch analysis |
| **Use SQLite** | Database instead of JSON for people |

**Actions:**
- **Test Inference:** Checks connection to detector
- **Analyze all:** Starts batch analysis

### 8.4 Tab: People

| Area | Description |
|------|-------------|
| **People list** | All created persons with embeddings |
| **Training from analysis** | Assign faces from recordings |
| **Detected faces** | Images for assigning/correcting |

**Per person:**
- Name + embedding count
- Preview images (thumbnails)
- Edit/Delete buttons

### 8.5 Tab: Performance

Live statistics from the Detector add-on:

| Metric | Description |
|--------|-------------|
| **CPU** | Current CPU usage |
| **RAM** | Memory usage |
| **Coral Status** | Connected/Not connected |
| **Inferences** | Number of analyses performed |
| **Avg Inference Time** | Average analysis time (ms) |
| **Coral Percentage** | Percent of Coral analyses |

**Test button:** Runs a test inference and shows time.

---

## 9. Automations

### 9.1 Person Detected - Notification

```yaml
automation:
  - alias: "Person detected - Push notification"
    trigger:
      - platform: event
        event_type: rtsp_recorder_person_detected
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.person_name != 'Unknown' }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Person detected"
          message: "{{ trigger.event.data.person_name }} was detected by {{ trigger.event.data.camera }}"
          data:
            image: "{{ trigger.event.data.thumbnail }}"
```

### 9.2 Unknown Person - Alarm

```yaml
automation:
  - alias: "Unknown person - Alarm"
    trigger:
      - platform: event
        event_type: rtsp_recorder_person_detected
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.person_name == 'Unknown' }}"
      - condition: state
        entity_id: alarm_control_panel.home
        state: "armed_away"
    action:
      - service: notify.all
        data:
          title: "⚠️ Unknown Person!"
          message: "Unknown person at {{ trigger.event.data.camera }}"
```

### 9.3 Daily Analysis at Night

```yaml
automation:
  - alias: "Nightly batch analysis"
    trigger:
      - platform: time
        at: "03:00:00"
    action:
      - service: rtsp_recorder.analyze_all_recordings
        data:
          skip_analyzed: true
          use_coral: true
```

### 9.4 Recording When Away

```yaml
automation:
  - alias: "Record when nobody home"
    trigger:
      - platform: state
        entity_id: binary_sensor.entrance_motion
        to: "on"
    condition:
      - condition: state
        entity_id: group.family
        state: "not_home"
    action:
      - service: rtsp_recorder.save_recording
        data:
          camera_name: entrance
          duration: 60
```

### 9.5 Available Events

| Event | Description | Data |
|-------|-------------|------|
| `rtsp_recorder_recording_saved` | Recording saved | camera, filename, duration |
| `rtsp_recorder_analysis_complete` | Analysis finished | camera, filename, detections |
| `rtsp_recorder_person_detected` | Person detected | camera, person_name, confidence, thumbnail |

### 9.6 Available Services

| Service | Description |
|---------|-------------|
| `rtsp_recorder.save_recording` | Start manual recording |
| `rtsp_recorder.delete_recording` | Delete single recording |
| `rtsp_recorder.delete_all_recordings` | Bulk deletion |
| `rtsp_recorder.analyze_recording` | Single analysis |
| `rtsp_recorder.analyze_all_recordings` | Batch analysis |

---

## 10. Troubleshooting

### 10.1 Recordings Don't Start

**Possible causes:**

| Problem | Solution |
|---------|----------|
| Wrong motion sensor | Check entity ID in camera settings |
| Camera not reachable | Test RTSP URL, check network |
| Storage full | Delete old recordings, adjust retention |
| FFmpeg error | Check logs, reinstall FFmpeg |

**Diagnosis:**
```bash
# In HA Terminal:
tail -f /config/home-assistant.log | grep rtsp_recorder
```

### 10.2 Coral USB Not Detected

1. **Check USB passthrough:**
   ```bash
   lsusb | grep -i coral
   # Should show "Global Unichip Corp"
   ```

2. **Add-on configuration:**
   - Settings → Add-ons → Detector → Configuration
   - Add USB device

3. **Try reset:**
   - Restart Detector add-on
   - Or: Call `/tpu_reset` endpoint

### 10.3 Face Recognition Inaccurate

| Symptom | Solution |
|---------|----------|
| Wrong assignments | Add more training samples |
| Person not recognized | Better images (frontal, well-lit) |
| Mix-ups | Negative samples for confused person |
| Too many unknowns | Lower match threshold (e.g., 0.55) |

### 10.4 Analysis Very Slow

| Cause | Solution |
|-------|----------|
| CPU fallback active | Install/check Coral USB |
| Too many frames | Increase frame interval |
| Large videos | Shorter recording duration |
| Server overloaded | Schedule analysis at night |

### 10.5 Dashboard Card Not Loading

1. **Clear browser cache:** Ctrl+F5
2. **Check resource:**
   ```yaml
   # In Lovelace YAML:
   resources:
     - url: /local/rtsp-recorder-card.js?v=1.2.2
       type: module
   ```
3. **File exists?** `/config/www/rtsp-recorder-card.js`
4. **Check console:** F12 → Console → Look for errors

---

## 11. FAQ

### General

**Q: How much storage do I need?**
> A: About 1-5 MB per minute of recording (depending on quality). With 10 cameras with 10 recordings/day at 30 sec each ≈ 1-3 GB/day.

**Q: Does it work without Coral USB?**
> A: Yes, but analyses take 10-15x longer (CPU fallback).

**Q: Can I use multiple Coral USB devices?**
> A: Currently only one Coral is supported.

### Recordings

**Q: Why are some recordings very short?**
> A: Recording ends X seconds after last motion. Short motion = short recording.

**Q: Can I change recording quality?**
> A: Quality is determined by camera/RTSP stream, not by RTSP Recorder.

**Q: Are recordings encrypted?**
> A: No, recordings are saved as normal MP4 files.

### AI Analysis

**Q: Which objects are detected?**
> A: All 80 COCO classes (Person, Car, Dog, Cat, etc.). Full list: https://cocodataset.org

**Q: How accurate is face recognition?**
> A: With good training data ~85-95% accuracy. Depends heavily on image quality and lighting.

**Q: Is data sent to the cloud?**
> A: No, all analyses run locally on your server.

### People

**Q: How many people can I train?**
> A: Technically unlimited. Recommended: max. 50 for best performance.

**Q: Can I export/import embeddings?**
> A: Data is stored in `/config/rtsp_recorder.db` (SQLite) or `rtsp_recorder_people.json`.

**Q: What about identical twins?**
> A: Use negative samples to minimize confusion.

---

## Appendix

### A. File Paths

| Path | Description |
|------|-------------|
| `/config/custom_components/rtsp_recorder/` | Integration |
| `/config/www/rtsp-recorder-card.js` | Dashboard Card |
| `/media/rtsp_recordings/` | Recordings |
| `/config/www/thumbnails/` | Thumbnails |
| `/media/rtsp_analysis/` | Analysis results |
| `/config/rtsp_recorder.db` | SQLite database |
| `/config/rtsp_recorder_people.json` | People (JSON mode) |

### B. API Reference

**Detector Add-on Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/info` | GET | Device info |
| `/metrics` | GET | Performance metrics |
| `/detect` | POST | Object detection |
| `/faces` | POST | Face detection |
| `/embed_face` | POST | Extract embedding |

### C. AI Models Used

| Model | Task | Input | Hardware |
|-------|------|-------|----------|
| MobileDet SSD | Object detection | 320x320 | Coral/CPU |
| MobileNet V2 | Face detection | 320x320 | Coral/CPU |
| EfficientNet-S | Face Embedding | 224x224 | Coral/CPU |
| MoveNet Lightning | Pose Estimation | 192x192 | CPU |

---

*RTSP Recorder v1.2.2 BETA - © 2026 brainAThome*
