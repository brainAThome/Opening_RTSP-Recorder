# 🚀 RTSP Recorder - Installation Guide

> 🇩🇪 **[Deutsche Version / German Version](INSTALLATION_DE.md)**

**Version:** 1.2.2  
**Last Updated:** February 7, 2026

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Installation via HACS](#2-installation-via-hacs)
3. [Manual Installation](#3-manual-installation)
4. [Detector Add-on Setup](#4-detector-add-on-setup)
5. [Coral USB Setup](#5-coral-usb-setup)
6. [First Configuration](#6-first-configuration)
7. [Verification](#7-verification)

---

## 1. System Requirements

### Minimum

| Component | Requirement |
|-----------|-------------|
| Home Assistant | 2024.1+ |
| Python | 3.11+ |
| Storage | 50 GB free |
| RAM | 2 GB available |

### Recommended

| Component | Recommendation |
|-----------|----------------|
| Home Assistant | 2024.12+ |
| Storage | 200+ GB SSD |
| RAM | 4+ GB available |
| Hardware | Google Coral USB Accelerator |

### Supported Cameras

- ✅ Any RTSP-capable IP camera
- ✅ Home Assistant Camera Entities
- ✅ Ring Doorbell (via Ring Integration)
- ✅ Frigate Cameras
- ✅ Generic Cameras (MJPEG, HLS)

---

## 2. Installation via HACS

### Step 1: Add Custom Repository

1. Open **HACS** in Home Assistant
2. Click **⋮** (three-dot menu) top right
3. Select **Custom repositories**
4. Add:
   - **Repository:** `https://github.com/brainAThome/Opening_RTSP-Recorder`
   - **Category:** Integration
5. Click **Add**

### Step 2: Install Integration

1. Search in HACS for "**RTSP Recorder**"
2. Click **Download**
3. Select version **1.2.2** (or newest)
4. Confirm with **Download**

### Step 3: Restart Home Assistant

```yaml
# In the UI: Developer Tools → YAML → Restart Home Assistant
# Or in configuration.yaml directory:
ha core restart
```

### Step 4: Activate Integration

1. **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search "**RTSP Recorder**"
4. Follow the setup wizard

---

## 3. Manual Installation

### 3.1 Copy Files

```bash
# Copy integration
cp -r custom_components/rtsp_recorder/ /config/custom_components/

# Copy dashboard card
cp www/rtsp-recorder-card.js /config/www/
```

### 3.2 Register Lovelace Resource

**Option A: UI (Recommended)**

1. Settings → Dashboards → Resources
2. **+ Add Resource**
3. URL: `/local/rtsp-recorder-card.js`
4. Type: **JavaScript Module**

**Option B: YAML**

```yaml
# In configuration.yaml
lovelace:
  mode: yaml
  resources:
    - url: /local/rtsp-recorder-card.js
      type: module
```

### 3.3 Check Directory Structure

```
/config/
├── custom_components/
│   └── rtsp_recorder/
│       ├── __init__.py
│       ├── analysis.py
│       ├── config_flow.py
│       ├── database.py
│       ├── exceptions.py
│       ├── manifest.json
│       ├── migrations.py
│       ├── performance.py
│       ├── rate_limiter.py
│       ├── recorder.py
│       ├── services.py
│       ├── translations/
│       │   ├── de.json
│       │   ├── en.json
│       │   ├── es.json
│       │   ├── fr.json
│       │   └── nl.json
│       └── websocket_handlers.py
└── www/
    └── rtsp-recorder-card.js
```

---

## 4. Detector Add-on Setup

The Detector Add-on enables AI analysis with Coral USB.

### 4.1 Install Add-on

1. Copy the add-on:
   ```bash
   cp -r addons/rtsp-recorder-detector/ /addons/
   ```

2. **Settings** → **Add-ons** → **Add-on Store**

3. Click **⋮** → **Check for updates**

4. Find "**RTSP Recorder Detector**" under "Local Add-ons"

5. Click **Install**

### 4.2 Configure Add-on

```yaml
# Add-on Configuration
port: 5000
log_level: info
model_path: /models
coral_enabled: true
```

### 4.3 Start Add-on

1. Click **Start**
2. Enable **Start on boot**
3. Optional: Enable **Watchdog**

---

## 5. Coral USB Setup

### 5.1 Hardware Passthrough (Home Assistant OS)

1. **Settings** → **System** → **Hardware**
2. Find "Google Coral USB Accelerator"
3. Note the path (e.g., `/dev/bus/usb/001/002`)

### 5.2 Add-on USB Access

In the add-on configuration:

```yaml
# Configuration for Coral USB
devices:
  - /dev/bus/usb
```

### 5.3 Verify Coral

1. Open add-on **Log**
2. Look for:
   ```
   INFO: Coral USB EdgeTPU detected
   INFO: Using EdgeTPU delegate
   ```

### 5.4 Troubleshooting Coral

| Problem | Solution |
|---------|----------|
| Coral not detected | Replug USB, restart HA |
| Permission denied | Check USB passthrough settings |
| Delegate error | Check libedgetpu version |

---

## 6. First Configuration

### 6.1 Integration Setup

After installation:

1. **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search "**RTSP Recorder**"

### 6.2 Basic Settings

| Setting | Recommendation | Description |
|---------|----------------|-------------|
| Storage Path | `/media/rtsp_recorder` | Recording storage location |
| Snapshot Path | `/media/rtsp_recorder/thumbnails` | Thumbnail storage location |
| Retention Days | 7 | Retention period |

### 6.3 Add Cameras

1. In the integration, click **Configure**
2. Select **Manage Cameras**
3. Add your cameras:
   - **Name:** e.g., "Living Room"
   - **Motion Sensor:** `binary_sensor.living_room_motion`
   - **Camera Entity:** `camera.living_room` (optional)
   - **RTSP URL:** `rtsp://user:pass@192.168.1.x/stream`

### 6.4 Enable Analysis

1. In **Options** → **Analysis**
2. **Analysis enabled:** ✅
3. **Detector URL:** `http://local-rtsp-recorder-detector:5000`
4. **Device:** Coral USB (if available)

---

## 7. Verification

### 7.1 Check Integration

```bash
# On the HA server:
grep -i rtsp_recorder /config/home-assistant.log | tail -10
```

Expected output:
```
INFO: Setup of rtsp_recorder completed successfully
```

### 7.2 Check Detector

```bash
# API test
curl http://localhost:5000/info
```

Expected output:
```json
{
  "version": "1.2.2",
  "coral_available": true,
  "models_loaded": true
}
```

### 7.3 Test Recording

1. Trigger motion on a configured sensor
2. Check log for "Recording started"
3. Check storage path for new .mp4 file

### 7.4 Test Dashboard Card

```yaml
# In a dashboard:
type: custom:rtsp-recorder-card
```

---

## Next Steps

- 📖 [User Guide](USER_GUIDE.md) - All features in detail
- 🧠 [Person Training](FACE_RECOGNITION.md) - Set up face recognition
- ⚙️ [Configuration](CONFIGURATION.md) - All options explained
- 🔧 [Troubleshooting](TROUBLESHOOTING.md) - Problem solving

---

*For problems: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
