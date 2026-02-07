# 🚀 RTSP Recorder - Installation Guide

> 🇩🇪 **[Deutsche Version / German Version](INSTALLATION_DE.md)**

**Version:** 1.2.5  
**Last Updated:** February 7, 2026

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Installation via HACS](#2-installation-via-hacs)
3. [Manual Installation](#3-manual-installation)
4. [Detector Add-on Setup](#4-detector-add-on-setup)
5. [Coral USB Setup](#5-coral-usb-setup)
6. [First Configuration](#6-first-configuration)
7. [Dashboard Setup](#7-dashboard-setup)
8. [Verification](#8-verification)

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
- ✅ Ring Doorbell (via ring-mqtt Add-on)
- ✅ Frigate Cameras
- ✅ Generic Cameras (MJPEG, HLS)

---

## 2. Installation via HACS

### Step 1: Add Custom Repository

1. Open **HACS** in the Home Assistant sidebar
2. Click the **⋮** (three-dot menu) in the top right corner
3. Select **Custom repositories**
4. In the popup:
   - **Repository:** `https://github.com/brainAThome/Opening_RTSP-Recorder`
   - **Category:** Select **Integration** from dropdown
5. Click **Add**
6. Close the popup

### Step 2: Install Integration

1. In HACS, click **+ Explore & Download Repositories** (bottom right)
2. Search for "**RTSP Recorder**"
3. Click on the result **"Opening RTSP Recorder"**
4. Click **Download** (bottom right)
5. Select the newest version
6. Click **Download** again to confirm

### Step 3: Restart Home Assistant

**Important: Restart is required!**

1. Go to **Settings** → **System** → **Restart**
2. Click **Restart**
3. Wait 1-2 minutes until HA is fully restarted

### Step 4: Activate Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for "**RTSP Recorder**"
4. Click on it and follow the setup wizard

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

The Detector Add-on enables AI analysis with Coral USB EdgeTPU support.

> ⚠️ **This step is optional but recommended for AI object detection and face recognition!**

### 4.1 Add Repository

1. Go to **Settings** → **Add-ons**
2. Click **Add-on Store** (bottom right)
3. Click the **⋮** (three-dot menu) in the top right
4. Select **Repositories**
5. Add:
   ```
   https://github.com/brainAThome/Opening_RTSP-Recorder
   ```
6. Click **Add** then **Close**

### 4.2 Install Add-on

1. Click **⋮** → **Check for updates** (page will refresh)
2. Scroll down - you'll now see the **"Opening RTSP Recorder"** section
3. Click on **"RTSP Recorder Detector"**
4. Click **Install** and wait (this may take 5-10 minutes)

### 4.3 Configure USB Access (for Coral)

1. After installation, go to the **Configuration** tab
2. If you have Coral USB, ensure it's connected
3. The add-on auto-detects Coral - no special config needed

### 4.4 Start Add-on

1. Click **Start**
2. Enable **Start on boot** (toggle)
3. Enable **Watchdog** (optional, restarts add-on if it crashes)
4. Wait for the add-on to start (check the Log tab)

### 4.5 Find Your Detector URL (CRITICAL!)

> ⚠️ **The Detector URL varies per installation! You MUST find your correct URL!**

1. Go to the **Info** tab of the Detector add-on
2. Find the **Hostname** - it looks like:
   ```
   a861495c-rtsp-recorder-detector
   ```
3. Your Detector URL is:
   ```
   http://[HOSTNAME]:5000
   ```
   Example: `http://a861495c-rtsp-recorder-detector:5000`

**Common Mistakes to Avoid:**
- ❌ `http://local-rtsp-recorder-detector:5000` - This does NOT work!
- ❌ `http://localhost:5000` - This does NOT work from HA!
- ✅ `http://[your-slug]-rtsp-recorder-detector:5000` - This is correct!

### 4.6 Configure Integration with Detector URL

1. Go to **Settings** → **Devices & Services**
2. Find **RTSP Recorder** and click **Configure**
3. Enter the **Detector URL** you found in step 4.5
4. Click **Submit**

---

## 5. Coral USB Setup

### 5.1 Hardware Passthrough (Home Assistant OS)

The Detector add-on automatically detects Coral USB if connected.

1. Plug in the Coral USB Accelerator
2. Restart the Detector add-on
3. Check the Log for:
   ```
   INFO: Coral USB EdgeTPU detected
   INFO: Using EdgeTPU delegate
   ```

### 5.2 Verify Coral is Working

1. Open the Detector add-on **Log** tab
2. Look for "Coral" or "EdgeTPU" in the startup messages
3. In the RTSP Recorder card, go to **Performance** tab to see Coral stats

### 5.3 Troubleshooting Coral

| Problem | Solution |
|---------|----------|
| Coral not detected | Unplug/replug USB, restart add-on |
| Permission denied | Restart entire Home Assistant |
| Slow inference (>500ms) | Coral not working, check logs |

---

## 6. First Configuration

### 6.1 Integration Setup Wizard

When you first add the integration, you'll be guided through:

1. **Basic Settings**
   - Storage Path: `/media/rtsp_recorder/ring_recordings`
   - Thumbnail Path: `/config/www/thumbnails`
   - Detector URL: (from step 4.5)

2. **Add Cameras**
   - Name: e.g., "Wohnzimmer"
   - Motion Sensor: Select from dropdown
   - Camera Entity or RTSP URL

3. **Analysis Settings** (optional)
   - Auto-analyze: Enable/Disable
   - Analysis interval

### 6.2 Recommended Settings

| Setting | Recommended Value | Description |
|---------|-------------------|-------------|
| **Retention Days** | 7 | How long to keep recordings |
| **Recording Duration** | 30 seconds | Length of each recording |
| **Snapshot Delay** | 2 seconds | When to capture thumbnail |
| **Auto-Analyze** | Enabled | Automatically analyze new recordings |

---

## 7. Dashboard Setup

### 7.1 Create a New Dashboard (Recommended)

1. Go to **Settings** → **Dashboards**
2. Click **+ Add Dashboard**
3. Name: "RTSP Recorder"
4. Icon: `mdi:cctv`
5. Click **Create**

### 7.2 Add the RTSP Recorder Card

1. Open your new dashboard
2. Click **✏️** (Edit, top right)
3. Click **+ Add Card**
4. Scroll down and select **"Manual"** (or search "rtsp")
5. Delete any existing content and paste:

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recorder/ring_recordings
thumb_path: /local/thumbnails
```

6. Click **Save**

### 7.3 Set to Full-Screen Panel Mode (IMPORTANT!)

The card looks best in **Panel mode** (full screen):

1. Click **✏️** (Edit mode)
2. Click the **✏️** next to "Unbenannte Ansicht" / "Default View" at the top
3. Find **"View type"** setting
4. Change from "Masonry" to **"Panel (1 card)"**
5. Click **Save**
6. Click **Done** (top right)

Now the RTSP Recorder card fills the entire screen!

### 7.4 Refresh Browser Cache

After setup, force-refresh your browser:
- **Windows/Linux:** `Ctrl + Shift + R`
- **Mac:** `Cmd + Shift + R`

---

## 8. Verification

### 8.1 Check Integration Status

1. Go to **Settings** → **Devices & Services**
2. Find **RTSP Recorder**
3. It should show "Configured" with no errors

### 8.2 Check Detector Connection

1. Open RTSP Recorder card
2. Click **"Menue"** / **"Menu"** tab
3. Check **Performance** section
4. You should see "Coral: ✓" if Coral is detected

### 8.3 Test a Recording

1. Trigger motion on a configured sensor (walk past the camera)
2. You should see:
   - "Recording in progress" in the card footer
   - New recording appears in the timeline after ~30 seconds

### 8.4 Common First-Time Issues

| Issue | Solution |
|-------|----------|
| Card shows "No recordings" | Wait for motion trigger, or check storage path |
| "Detector not available" | Check Detector URL (step 4.5) |
| Card not loading | Clear browser cache (Ctrl+Shift+R) |
| No thumbnails | Check thumb_path points to `/local/thumbnails` |

---

## Next Steps

- 📖 [User Guide](USER_GUIDE.md) - All features explained
- 🧠 [Face Recognition](FACE_RECOGNITION.md) - Train person recognition
- ⚙️ [Configuration](CONFIGURATION.md) - All options
- 🔧 [Troubleshooting](TROUBLESHOOTING.md) - Problem solving

---

*For problems: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
