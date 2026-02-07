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

> ✅ **As of v1.2.6:** The dashboard card is automatically installed and registered!
> Clear browser cache after first start: **Ctrl + Shift + R**

<details>
<summary>⚠️ <b>Troubleshooting: "Custom element doesn't exist" Error</b> (click to expand)</summary>

If you see this error after installation:
```
Configuration Error
Custom element doesn't exist: rtsp-recorder-card
```

**Solution 1: Clear browser cache**
- Press **Ctrl + Shift + R** (Windows/Linux) or **Cmd + Shift + R** (Mac)
- Restart Home Assistant

**Solution 2: Manual registration (for versions < 1.2.6)**

The dashboard card must be registered as a Lovelace Resource:

1. Go to **Settings** → **Dashboards**
2. Click the **⋮** (three-dot menu) in the top right
3. Select **Resources**
4. Click **+ Add Resource** (bottom right)
5. Fill in:
   - **URL:** `/local/rtsp-recorder-card.js`
   - **Type:** Select **JavaScript Module**
6. Click **Create**
7. Clear browser cache

</details>

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

> 💡 **Tip for Beginners:** Follow each step exactly. Screenshots in your Home Assistant may look slightly different - that's normal!

### 7.1 Create a New Dashboard

**Why a separate dashboard?** The RTSP Recorder Card needs a lot of space. A dedicated dashboard prevents conflicts with your other cards.

1. Click **Settings** in the **left sidebar** (the gear icon ⚙️)
2. Click **Dashboards**
3. Click **+ Add Dashboard** (bottom right)
4. A popup appears:
   - **Title:** `RTSP Recorder`
   - **Icon:** Click the icon field and search `cctv`, select the camera icon
   - Leave "Show in sidebar" enabled ✓
5. Click **Create**

✅ **Result:** "RTSP Recorder" now appears in your left sidebar with a camera icon.

---

### 7.2 Open Dashboard and Enable Edit Mode

1. Click your new **"RTSP Recorder"** dashboard in the **left sidebar**
2. You'll see an empty page with text like "Empty page starts here"
3. Click the **pencil ✏️** (Edit button) in the top right
   
   > ⚠️ Don't see a pencil? Click the **three dots ⋮** top right → **Edit Dashboard**

4. A blue bar appears at the top - you're now in Edit Mode!

---

### 7.3 IMPORTANT: Set Panel Mode First!

> ⚠️ **Do this BEFORE adding the card!** Otherwise the card will appear too small.

**What is Panel Mode?** Normally Home Assistant shows multiple cards side by side (like tiles). Panel mode shows only ONE card in full screen - perfect for the RTSP Recorder Card!

**How to enable Panel Mode:**

1. You're in Edit Mode (blue bar at top)
2. At the top you'll see the tab **"Default View"** with a small **pencil ✏️** next to it
   
   ```
   ┌─────────────────────────────────────────────────────────────┐
   │  Default View ✏️  │  +                                      │
   └─────────────────────────────────────────────────────────────┘
   ```
   
3. Click this **small pencil ✏️** (NOT the one in the top right!)
4. A popup **"Edit View"** opens
5. Scroll down in the popup until you see **"View Type"**
6. Click the dropdown (probably says "Masonry" or "Sections")
7. Select **"Panel (1 card)"**
8. Click **Save** at the bottom of the popup

✅ **Result:** Panel mode is now active.

---

### 7.4 Add the RTSP Recorder Card

1. You're still in Edit Mode
2. Click **+ Add Card** (bottom right)
3. A popup with many card types appears
4. Scroll **all the way down** in the list
5. Click **"Manual"** (at the very bottom, under "Custom")

   > 💡 Alternative: Type "rtsp" in the search box - if the card is installed correctly, it will appear

6. You'll see a YAML editor with example code
7. **Delete EVERYTHING** in the editor
8. **Copy the following code** and paste it:

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recorder/ring_recordings
thumb_path: /local/thumbnails
```

9. Click **Save** (top right of popup)

✅ **Result:** The RTSP Recorder Card now appears in full screen!

---

### 7.5 Exit Edit Mode

1. Click **Done** in the top right
2. The blue bar disappears
3. You're now viewing your finished RTSP Recorder Dashboard!

---

### 7.6 Clear Browser Cache (IMPORTANT If You Have Problems!)

If the card doesn't look right or shows errors:

**Windows/Linux:**
- Press **Ctrl + Shift + R** (all three keys at once)

**Mac:**
- Press **Cmd + Shift + R**

**On Phone/Tablet:**
- Close the Home Assistant app completely
- Reopen it

---

### 7.7 Common Dashboard Problems

| Problem | What You See | Solution |
|---------|--------------|----------|
| Card is too small/narrow | Card only takes 1/3 of width | Panel mode not active! See step 7.3 |
| "Custom element doesn't exist" | Error message instead of card | **Lovelace Resource missing!** See Step 2.5 above |
| Card shows "No recordings" | Empty timeline | Normal! Wait for first motion event |
| Card loading forever | Only spinning wheel | Check if integration is properly installed |
| White screen | Nothing visible | Check browser console (F12) for JS errors |

> 💡 **The most common error:** "Custom element doesn't exist: rtsp-recorder-card"
> 
> This means the JavaScript file was not registered as a Lovelace Resource.
> **Solution:** Go to Step 2.5 "Register Dashboard Card" and follow the instructions.

---

### 7.8 What It Should Look Like

When everything works, you'll see:
- ✅ The card fills the entire screen
- ✅ Top: Tab bar (Timeline, Live, Analytics, Menu)
- ✅ Middle: Video player or thumbnail grid
- ✅ Bottom: Status bar with recording info

> 🎉 **Done!** Your RTSP Recorder Dashboard is set up!

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
