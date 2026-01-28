# RTSP Recorder for Home Assistant

A complete video surveillance solution with AI-powered object detection using Coral USB EdgeTPU.

![Version](https://img.shields.io/badge/version-1.0.6%20BETA-orange)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- 🎥 **Motion-triggered recording** from RTSP cameras
- 🔍 **AI object detection** with Coral USB EdgeTPU support
- 📊 **Live performance monitoring** (CPU, RAM, Coral stats)
- ⏰ **Automated analysis scheduling** (daily or interval-based)
- 🎛️ **Beautiful dashboard card** with video playback
- 📁 **Automatic retention management** for recordings
- 🔴 **Real-time overlay** showing detected objects

## Components

### 1. Custom Integration (`/custom_components/rtsp_recorder/`)
The main Home Assistant integration that handles:
- Recording management
- Motion sensor triggers
- Analysis job scheduling
- WebSocket API for the dashboard

### 2. Dashboard Card (`/www/rtsp-recorder-card.js`)
A feature-rich Lovelace card providing:
- Video playback with timeline
- Camera selection and filtering
- Performance monitoring panel
- Analysis configuration
- Recording management (download, delete)

### 3. Detector Add-on (`/addons/rtsp-recorder-detector/`)
A standalone add-on for object detection:
- Coral USB EdgeTPU support (Frigate-compatible)
- CPU fallback when Coral unavailable
- Cached interpreters for optimal performance
- REST API for detection requests

## Installation

### Step 1: Install the Integration
Copy the `custom_components/rtsp_recorder` folder to your Home Assistant config directory.

### Step 2: Install the Dashboard Card
Copy `www/rtsp-recorder-card.js` to `/config/www/`.

Add to your Lovelace resources:
```yaml
resources:
  - url: /local/rtsp-recorder-card.js
    type: module
```

### Step 3: Install the Detector Add-on (Optional)
For AI object detection with Coral USB:

1. Copy the `addons/rtsp-recorder-detector` folder to `/addons/`
2. Go to Settings → Add-ons → Add-on Store → ⋮ → Repositories
3. The add-on should appear after refresh
4. Install and start the add-on

### Step 4: Configure the Integration
1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "RTSP Recorder"
4. Follow the configuration wizard

## Coral USB EdgeTPU Support

This integration supports Google Coral USB EdgeTPU for hardware-accelerated object detection.

### Requirements
- Google Coral USB Accelerator
- USB passthrough configured in your Home Assistant setup

### Performance
With Coral USB:
- ~40-70ms inference time
- Hardware-accelerated detection
- No CPU overhead

Without Coral (CPU fallback):
- ~500-800ms inference time
- Higher CPU usage

## Dashboard Card Configuration

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recordings
thumb_path: /local/thumbnails
```

## API Endpoints

### Detector Add-on

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/info` | GET | Device info (Coral status, versions) |
| `/detect` | POST | Run object detection on image |

### WebSocket Commands

| Command | Description |
|---------|-------------|
| `rtsp_recorder/get_analysis_overview` | Get analysis history and stats |
| `rtsp_recorder/get_analysis_result` | Get detection results for video |
| `rtsp_recorder/get_detector_stats` | Get live detector performance |
| `rtsp_recorder/get_analysis_config` | Get schedule configuration |
| `rtsp_recorder/set_analysis_config` | Update schedule configuration |
| `rtsp_recorder/test_inference` | Run test detection |

## Troubleshooting

### Coral USB not detected
1. Check USB connection and passthrough
2. Verify with `lsusb` - should show "Global Unichip Corp."
3. Ensure add-on has USB device access

### High inference times
1. Ensure Coral USB is detected (`/info` endpoint)
2. Check interpreter caching is working
3. Verify libedgetpu-max is installed

### Recording not starting
1. Check motion sensor entity ID
2. Verify camera entity or RTSP URL
3. Check storage path permissions

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed release notes.

## Audit Report

See [AUDIT_REPORT_v1.0.6.md](AUDIT_REPORT_v1.0.6.md) for the full v1.0.6 audit report.

## License

MIT License - See LICENSE file for details.

## Credits

- Built for Home Assistant
- Coral USB support inspired by Frigate NVR
- Uses TensorFlow Lite Runtime
- Models from Google Coral test data

