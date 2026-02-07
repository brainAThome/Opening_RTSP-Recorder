# RTSP Recorder – Operations Manual

> 🇩🇪 **[Deutsche Version](OPERATIONS_MANUAL_DE.md)**

![Version](https://img.shields.io/badge/Version-1.2.2%20BETA-brightgreen)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)

> [!NOTE]
> This operations manual describes the features and usage of the **RTSP Recorder Card** for Home Assistant.
> Last updated: February 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Main Interface](#main-interface)
3. [Browsing Recordings](#browsing-recordings)
4. [Video Playback](#video-playback)
5. [Settings (Card)](#settings-card)
   - [General](#general)
   - [Storage](#storage)
   - [Analysis](#analysis)
   - [Persons](#persons)
   - [Movement](#movement)
   - [Performance](#performance)
6. [Configuration (Integration)](#configuration-integration)
   - [Global Settings](#global-settings)
   - [Adding a Camera](#adding-a-camera)
   - [Offline Analysis](#offline-analysis-configuration)
7. [Performance Display](#performance-display)
8. [Tips & Best Practices](#tips--best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The **RTSP Recorder** is a complete video surveillance solution with AI-powered object detection for Home Assistant. With the integrated Lovelace card you can:

- 🎥 Browse recordings from RTSP cameras
- 🔍 AI-based object detection with Coral USB EdgeTPU
- 👤 Face recognition and person management
- 📊 Real-time performance monitoring
- 🗂️ Automatic storage management

---

## Main Interface

![RTSP Recorder Card Main Interface](images/rtsp_recorder_interface_1770149290384.png)

The main interface consists of three areas:

### 1. Header
| Element | Description |
|---------|-------------|
| **Camera Archive** | Title with version display (BETA v1.2.2) |
| **Last 24 Hours** | Time filter for recordings |
| **Cameras** | Camera selection dropdown |
| **Menu** | Opens settings |

### 2. Video Player (Center)
The central area displays the selected video with standard controls:
- ▶️ Play/Pause
- 🔊 Volume control
- ⛶ Fullscreen mode
- Timeline/Progress bar

### 3. Recordings Timeline (Right)
A vertical, scrollable list of all available recordings:
- Preview thumbnails
- Camera name and timestamp
- Status badges (e.g., "🔄 Analysis")

---

## Browsing Recordings

### Using Time Filters
Click on **"Last 24 Hours"** to change the time period:
- Last 24 hours
- Last 7 days
- Last 30 days
- Custom

### Camera Filter
Click on **"Cameras"** to filter by specific cameras:
- **All** – Shows all cameras
- Select individual cameras (e.g., Living Room, Upstairs Hallway)

Available cameras in this setup:
- Upstairs Hallway
- Backyard
- Front Door
- Kids Room
- Living Room

---

## Video Playback

### Action Bar
The following controls are located below the video player:

| Button | Function |
|--------|----------|
| **Download** | Downloads the current recording |
| **Delete** (red) | Permanently deletes the recording |
| **Overlay** | Toggles object detection markers on/off |

### Playback Speed
Select the playback speed:
- **0.5x** – Slow motion
- **1x** – Normal (default)
- **2x** – Fast forward

### Object Detection Overlay
When enabled, detected objects are marked with colored boxes:
- 🟦 Persons
- 🟩 Animals (cat, dog)
- 🟨 Vehicles (car, bicycle)
- 🟪 Furniture/Objects (couch, plant)

---

## Settings

Open settings via the **"Menu"** button. There are 6 tabs available:

### General

![General Tab](images/general_tab_screenshot_1770149392938.png)

Global settings for the user interface:

| Option | Description |
|--------|-------------|
| **Kiosk Mode** | Hides all controls for display view |
| **Animations** | Enables/disables UI animations |
| **Show Footer** | Shows/hides the performance display |

---

### Storage

![Storage Tab](images/storage_tab_screenshot_1770149407122.png)

Overview and management of storage space:

#### Statistics
- **Total Recordings** – Total count of all recordings
- **Estimated Size** – Calculated storage consumption in GB
- **Per Camera** – Breakdown by camera

#### Cleanup
Delete old recordings by criteria:

| Option | Description |
|--------|-------------|
| **Camera** | All cameras or select specific ones |
| **Older Than** | Age in days (e.g., "older than 7 days") |
| **Also Delete Analyses** | Removes associated analysis data |

> [!WARNING]
> **Deleted recordings cannot be recovered!**

---

### Analysis

![Analysis Tab](images/analysis_tab_screenshot_1770149345176.png)

Configure AI object detection:

#### Select Objects
Choose which objects to detect:

**Quick Profiles:**
- 👤 **Persons** – People only
- 🐾 **Animals** – Pets (cat, dog, bird)
- 🚗 **Vehicles** – Vehicles (car, bicycle, bus)
- 🏠 **Room Theme** – Living room objects

**Individual Objects:**
- Person, Cat, Dog, Car, Bicycle, Bus, Motorcycle
- Bird, Horse, Sheep, Cow
- and more...

#### Hardware
Select the detection device:
- **Coral USB** – Hardware accelerated (recommended)
- **CPU** – Software fallback

#### Analyze Current Recording
- Checkbox: **Show objects in video**
- Button: **Analyze current recording** – Performs analysis for the current video

#### Analyze All Recordings (Batch)
Analyze multiple recordings at once:

| Option | Description |
|--------|-------------|
| **Time Period** | Maximum age of videos to analyze |
| **Limit** | Maximum number of videos |
| **New Files Only** | Skips already analyzed videos |

---

### Persons

![Persons Tab](images/persons_tab_screenshot_1770149356233.png)

Manage face recognition:

#### Person List
Shows all known persons with:
- **Name** – Editable
- **Embeddings** – Number of stored facial features
- **Preview Images** – Thumbnails of recognized faces

#### Actions per Person
| Icon | Action |
|------|--------|
| ✏️ | Edit name |
| 🗑️ | Delete person |
| ➕ | Add new face sample |

#### Add New Person
Click on **"Add"** to add a new person to the database.

> [!TIP]
> **Training Tip:** For best recognition rates, add 5-10 images per person – from different angles and lighting conditions.

---

### Movement

The movement profile shows where and when persons were detected. There are two views:

#### Chart View

![Movement Profile Chart](images/bewegung_diagramm.png)

Statistical overview:

| Statistic | Meaning |
|-----------|---------|
| **Total** | Total count of all detections |
| **Persons** | Number of recognized persons |
| **Cameras** | Number of active cameras |
| **Active Hours** | Hours with activity |

**Detections per Person:** Colored bar charts show how often each person was detected.

**Detections per Camera:** Shows the distribution of detections across cameras.

**Activity per Person (24h):** Heatmap of activity throughout the day.

#### List View

![Movement Profile List](images/bewegung_liste.png)

Chronological listing of all detections per person:

- **Person Name** – Grouped by recognized person
- **Camera Location** – Where the person was detected
- **Timestamp** – Date and time
- **Confidence** – Recognition accuracy in %

#### Switch View

| Button | View |
|--------|------|
| **Chart** | Statistical analysis with bars and heatmap |
| **List** | Chronological timeline per person |

---

### Performance

![Performance Tab](images/performance_tab_screenshot_1770149379171.png)

Real-time system monitoring:

#### Live System Monitor
| Metric | Description |
|--------|-------------|
| **CPU Usage** | Current processor utilization in % |
| **RAM Usage** | Memory utilization in % |

#### Object Detection (Coral)
| Metric | Description |
|--------|-------------|
| **Status** | Active / Inactive |
| **Coral USB** | Detected EdgeTPU accelerator |
| **Coral Usage** | Proportion of Coral usage (0-100%) |
| **TPU Load** | Current hardware load of the TPU |
| **Inference Time** | Average detection time in ms |
| **Total Inferences** | Total number of performed detections |

#### TPU Test
Click on **"Test Interval"** to perform a test inference and check TPU responsiveness.

#### CPU History
A graph of the last 60 measurements shows CPU history.

---

## Configuration (Integration)

The integration is configured via **Settings → Devices & Services → RTSP Recorder → Configure**.

### Global Settings

![Global Settings](images/einstellungen_global.png)

Basic configuration of the RTSP Recorder:

| Option | Description | Default |
|--------|-------------|---------|
| **Storage Path** | Directory for recordings | `/media/rtsp_recorder/ring_recordings` |
| **Thumbnail Path** | Directory for preview images | `/media/rtsp_recorder/thumbnails` |
| **Video Retention** | Days until automatic deletion | 7 days |
| **Thumbnail Retention** | Days for preview images | 7 days |
| **Cleanup Interval** | Frequency of cleanup | 24 hours |

> [!NOTE]
> If the storage path is not whitelisted, add the following to your `configuration.yaml`:
> ```yaml
> homeassistant:
>   allowlist_external_dirs:
>     - /media
> ```

---

### Adding a Camera

![Add Camera](images/kamera_hinzufuegen.png)

Add RTSP cameras manually that were not automatically detected:

| Field | Description | Example |
|-------|-------------|---------|
| **Camera Name** | Unique name | Garage, Driveway |
| **RTSP URL** | Stream URL of the camera | `rtsp://user:pass@192.168.1.100:554/stream` |
| **Motion Sensor** | Binary sensor that triggers recording | `binary_sensor.motion_garage` |
| **Recording Duration** | Length of recording in seconds | 120 sec |
| **Snapshot Delay** | Wait time before thumbnail creation | 0 sec |
| **Custom Retention** | Overrides global setting (0 = global) | 0 hours |

> [!TIP]
> Enable **"Add another camera"** to set up multiple cameras in sequence.

---

### Offline Analysis Configuration

![Offline Analysis](images/offline_analyse.png)

Configure AI-based video analysis:

#### Basic Settings

| Option | Description |
|--------|-------------|
| **Analysis Active** | Enables offline analysis |
| **Hardware** | Coral USB (recommended) or CPU |

#### Object Filter

Select which objects to detect:
- Person, Car, Bed, Book, Bus, Dining Table
- Bicycle, Remote Control, TV, Bottle, Dog
- Cat, Laptop, Truck, Suitcase, Motorcycle
- Cell Phone, Cup, Couch, Chair, Backpack, Bird
- Umbrella, Plant, Package

#### Analysis Parameters

| Option | Description | Recommended |
|--------|-------------|-------------|
| **Analysis Folder** | Storage location for results | `/media/rtsp_recorder/ring_recordings/_analysis` |
| **Frame Interval** | Seconds between frames | 2 sec |
| **Detector URL** | Address of the Detector add-on | `http://local-rtsp-recorder-detector:5000` |
| **Detection Threshold** | Minimum for object detection | 0.5 |
| **Face Recognition Active** | Enables face detection | ✅ |
| **Face Detection Threshold** | Minimum for face detection | 0.2 |
| **Face Matching Threshold** | Threshold for person assignment | 0.35 |

#### Automation

| Option | Description |
|--------|-------------|
| **Create Person Entities** | Creates binary sensors for recognized persons |
| **Use SQLite Database** | Better performance with many persons |
| **Automation Active** | Analyzes on schedule |
| **Analyze New Videos Immediately** | Analyzes after saving |
| **Mode** | Daily (time) or Interval |

---

## Performance Display

The **footer bar** at the bottom shows real-time data:

| Display | Meaning | Color Codes |
|---------|---------|-------------|
| **CPU** | Processor utilization | 🟢 <50% 🟠 50-80% 🔴 >80% |
| **RAM** | Memory | 🟢 <70% 🟠 70-90% 🔴 >90% |
| **Coral** | TPU status | Active/Inactive |
| **TPU %** | Coral load | 🟢 <5% 🟠 5-25% 🔴 >25% |
| **Inference** | Detection time | ms |

---

## Tips & Best Practices

### Optimal Configuration

> [!TIP]
> **For best performance:**
> - Use a **Coral USB EdgeTPU** for hardware-accelerated detection
> - Set the **Cleanup Interval** to 1 hour for short retention periods
> - Use **Per-Camera Retention** for different retention times

### Improving Face Recognition

1. **Collect multiple samples** – 5-10 different images per person
2. **Various lighting conditions** – Day and night
3. **Various angles** – Frontal and side views
4. **Negative samples** – Add false-positive detections as negatives

### Saving Storage Space

1. **Short retention** – Set `retention_days` to 7-14 days
2. **Automatic cleanup** – Enable automatic cleanup
3. **Targeted analysis** – Only analyze relevant recordings

---

## Troubleshooting

### Common Problems

| Problem | Solution |
|---------|----------|
| **Coral not detected** | Check USB connection, restart add-on |
| **Slow detection** | CPU fallback active → Connect Coral USB |
| **No recordings visible** | Adjust time filter, check camera filter |
| **Face not recognized** | Add more training images |
| **High CPU load** | Keep analysis batches smaller, increase interval |

### Check Logs

Check the Home Assistant logs at:
**Settings → System → Logs**

Filter for `rtsp_recorder` for relevant entries.

### Support

For further issues:
1. Check the [Troubleshooting Documentation](TROUBLESHOOTING.md)
2. Open an issue in the repository

---

> **RTSP Recorder v1.2.2 BETA** – AI-powered video surveillance for Home Assistant
