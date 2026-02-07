# Ring Camera - Amazon Data Flow Analysis

**Date:** February 6, 2026  
**Status:** Documented  
**Project:** RTSP Recorder - Local Recording Without Cloud Dependency

---

## 📋 Overview

This documentation describes how Ring cameras send data to Amazon, what data flows, and how we attempted to control the data flow.

---

## ⚠️ IMPORTANT: Ring Premium Subscription

| Subscription Status | Video Storage in Cloud | Action Required |
|---------------------|------------------------|-----------------|
| **No Premium** | ❌ No videos stored | Snapshots only on app/web access |
| **With Premium** | ✅ All videos stored | **Video storage must be manually disabled!** |

### Disable Video Storage (with Premium Subscription)

1. Open Ring App → Select device
2. Device Settings → Video Settings
3. **"Video Recording"** or **"Save Video"** → **OFF**
4. Alternative: Ring Dashboard (ring.com) → Devices → Settings

> ⚠️ **Without this setting, ALL motion videos are stored in the Amazon Cloud with Premium subscription!**

---

## 🔄 Data Flow Diagram

```
                              ┌─────────────────────────────────────┐
                              │         RING CAMERA                 │
                              │         (Front Door)                │
                              └──────────────┬──────────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     │                       │                       │
                     ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │   RING APP       │    │   RING WEBSITE   │    │   RTSP STREAM    │
          │   opens          │    │   ring.com       │    │   (local)        │
          └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                   │                       │                       │
                   ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  Snapshot is     │    │  Snapshot is     │    │  No data         │
          │  fetched from    │    │  fetched from    │    │  transfer to     │
          │  camera          │    │  camera          │    │  Amazon          │
          └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                   │                       │                       │
                   ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  Via ring.com    │    │  Via Amazon      │    │  Local           │
          │  API             │    │  CDN (direct)    │    │  Storage         │
          └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                   │                       │                       │
                   ▼                       ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  ✅ BLOCKABLE    │    │  ❌ NOT          │    │  ✅ COMPLETELY   │
          │  with Pi-hole    │    │  BLOCKABLE       │    │  LOCAL           │
          │  (ring.com)      │    │  (amazonaws.com) │    │  (Home Assistant)│
          └──────────────────┘    └──────────────────┘    └──────────────────┘
```

### Legend

| Path | Description | Blockable? |
|------|-------------|------------|
| **Ring App** | App requests snapshot via ring.com API | ✅ Yes (Pi-hole blocks ring.com) |
| **Ring Website** | Browser requests snapshot via Amazon CDN | ❌ No (amazonaws.com not blockable) |
| **RTSP Stream** | Local video stream without cloud | ✅ Not needed (no cloud traffic) |

---

## 📊 What Data Flows to Amazon?

### Data Types and Triggers

| Data Type | Trigger | Destination | Blockable | Note |
|-----------|---------|-------------|-----------|------|
| **Live Snapshots (App)** | Open Ring App | Amazon Cloud | ✅ Yes (Pi-hole) | Camera is queried via ring.com API |
| **Live Snapshots (Web)** | Open ring.com | Amazon Cloud | ❌ No | Camera is queried via Amazon CDN |
| **Event Snapshots** | Motion detected | Amazon Cloud | ✅ Yes (Pi-hole) | Only thumbnail, no video |
| **Video Clips** | Only with Premium | Amazon Cloud | ✅ Yes (Pi-hole) | **Without Premium: No videos stored!** |
| **Telemetry** | Continuous | Amazon Analytics | ✅ Partial | Device status, battery level etc. |

### ⚠️ Important: Video Storage

```
┌─────────────────────────────────────────────────────────────────┐
│                    VIDEO STORAGE IN CLOUD                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  WITHOUT Premium subscription:                                  │
│  ├── No videos are stored in cloud                             │
│  ├── Only live snapshots when opening app/web                  │
│  └── Event notifications without video clip                    │
│                                                                 │
│  WITH Premium subscription (Protect Plan):                     │
│  ├── ALL motion videos are stored                              │
│  ├── 30-60 days cloud storage                                  │
│  └── ⚠️ MUST BE MANUALLY DISABLED!                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Explanation

#### 1. Live Snapshots via Ring App (BLOCKABLE ✅)

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Ring App    │────▶│  ring.com       │────▶│  Ring Camera     │
│  opened      │     │  API Request    │     │  sends snapshot  │
└──────────────┘     └─────────────────┘     └──────────────────┘
                              │
                              │ Pi-hole blocks ring.com
                              ▼
                     ┌─────────────────┐
                     │  🚫 BLOCKED     │
                     │  No Snapshot    │
                     │  to Amazon      │
                     └─────────────────┘
```

**Behavior:**
- App sends request to ring.com API
- ring.com contacts the camera
- Camera sends snapshot back
- **Pi-hole blocks ring.com → No snapshot possible**

#### 2. Live Snapshots via Website (NOT BLOCKABLE ❌)

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Browser     │────▶│  ring.com       │────▶│  Ring Camera     │
│  opens       │     │  Website        │     │  sends snapshot  │
│  ring.com    │     │                 │     │                  │
└──────────────┘     └─────────────────┘     └──────────────────┘
                              │
                              │ Snapshot retrieval via Amazon CDN
                              ▼
                     ┌─────────────────────────────────────┐
                     │  amazonaws.com / cloudfront.net     │
                     │  ❌ Not blockable without breaking  │
                     │  other Amazon services              │
                     └─────────────────────────────────────┘
```

**Problem:**
- The website fetches snapshots via Amazon infrastructure
- The same domains are used for Amazon Shopping, Prime Video, AWS etc.
- **Blocking would break all Amazon services**
- The camera delivers the snapshot directly to Amazon CDN

---

## 🛡️ Pi-hole Blocking Results

### Blocked Domains (successful)

| Domain | Purpose | Effect when blocked |
|--------|---------|---------------------|
| `*.ring.com` | Ring Cloud API | ✅ App doesn't work |
| `app-snips.ring.com` | Snapshot uploads | ✅ No snapshots to cloud |
| `prod-snips.ring.com` | Production snapshots | ✅ No snapshots to cloud |
| `fw.ring.com` | Firmware updates | ⚠️ No more updates |
| `api.ring.com` | Main API | ✅ App completely blocked |
| `oauth.ring.com` | Authentication | ✅ Login not possible |
| `nw.ring.com` | Network services | ✅ No cloud access |

### Non-blockable Domains

| Domain | Reason | Problem |
|--------|--------|---------|
| `*.amazonaws.com` | AWS Services | Would break many other services |
| `*.cloudfront.net` | Amazon CDN | Used by many websites |
| `*.amazon.com` | Amazon general | Would block shopping etc. |

### Pi-hole Configuration

```
# /etc/pihole/custom.list or via Admin Interface

# Block Ring completely
0.0.0.0 ring.com
0.0.0.0 app-snips.ring.com
0.0.0.0 prod-snips.ring.com
0.0.0.0 api.ring.com
0.0.0.0 oauth.ring.com
0.0.0.0 fw.ring.com
0.0.0.0 nw.ring.com
0.0.0.0 account.ring.com
0.0.0.0 app.ring.com
0.0.0.0 pki.ring.com
0.0.0.0 rings.solutions
0.0.0.0 *.rings.solutions
```

---

## 📈 Data Flow Scenarios

### Scenario 1: Normal Usage (without Blocking)

```
┌────────────────────────────────────────────────────────────────┐
│                    WITHOUT PI-HOLE BLOCKING                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Open app ────────▶ Snapshot to Amazon ──────▶ 📤 SENT     │
│                                                                │
│  2. Motion ──────────▶ Event to Amazon ─────────▶ 📤 SENT     │
│                                                                │
│  3. Retrieve video ──▶ Stream from Amazon ──────▶ 📤 SENT     │
│                                                                │
│  4. Website ─────────▶ Snapshot via CDN ────────▶ 📤 SENT     │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Scenario 2: With Pi-hole Blocking (Ring Domains)

```
┌────────────────────────────────────────────────────────────────┐
│                    WITH PI-HOLE BLOCKING                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Open app ────────▶ DNS blocked ─────────────▶ 🚫 BLOCKED  │
│                                                                │
│  2. Motion ──────────▶ API not reachable ───────▶ 🚫 BLOCKED  │
│                                                                │
│  3. Retrieve video ──▶ Cloud not reachable ─────▶ 🚫 BLOCKED  │
│                                                                │
│  4. Website ─────────▶ CDN not blockable ───────▶ 📤 SENT     │
│                           (amazonaws.com)                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Scenario 3: RTSP Recorder (completely local)

```
┌────────────────────────────────────────────────────────────────┐
│                    WITH RTSP RECORDER                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Ring Camera ─────────────────────────────────────────────────│
│       │                                                        │
│       │ RTSP Stream (local, Port 8554)                        │
│       ▼                                                        │
│  ┌─────────────────┐                                          │
│  │ Home Assistant  │                                          │
│  │ RTSP Recorder   │ ◀── No cloud connection needed           │
│  └─────────────────┘                                          │
│       │                                                        │
│       │ Local storage                                         │
│       ▼                                                        │
│  ┌─────────────────┐                                          │
│  │ /media/rtsp/    │ ◀── All data stays local                 │
│  │ recordings/     │                                          │
│  └─────────────────┘                                          │
│                                                                │
│  📍 Sent to Amazon: NOTHING (0 Bytes)                         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Technical Details

### Ring Snapshot Mechanism

```python
# Simplified representation of Ring snapshot process

class RingCamera:
    def on_app_opened(self):
        """Triggered when Ring App is opened"""
        # 1. Ring App sends API request to ring.com
        # 2. Ring Cloud sends request to camera
        # 3. Camera captures current frame
        # 4. Frame is uploaded to Amazon Cloud
        # 5. App displays snapshot
        
        snapshot = self.capture_current_frame()
        self.upload_to_cloud(snapshot)  # <-- THIS is what we want to prevent
        
    def on_motion_detected(self):
        """Triggered on motion detection"""
        # Event is sent to Ring Cloud
        # Cloud decides whether to start recording
        
        event = self.create_motion_event()
        self.send_to_cloud(event)  # <-- This is also blocked
```

### RTSP Stream (local)

```python
# RTSP Recorder - Local Alternative

class RTSPRecorder:
    def on_motion_detected(self):
        """Local motion detection"""
        # 1. Motion sensor triggers (binary_sensor)
        # 2. RTSP stream is recorded locally
        # 3. No cloud connection needed
        
        self.start_local_recording()  # <-- Completely local
        
    def get_rtsp_url(self):
        """Local RTSP Stream"""
        # Ring cameras offer RTSP via ring-mqtt
        return "rtsp://192.168.178.x:8554/ring_front_door"
```

---

## 📋 Summary

### Premium Subscription Status

| Subscription | Video Storage | Snapshots on App | Snapshots on Website |
|--------------|---------------|------------------|----------------------|
| **Without Premium** | ❌ No videos in cloud | ✅ Yes (blockable) | ✅ Yes (not blockable) |
| **With Premium** | ⚠️ ALL videos in cloud | ✅ Yes (blockable) | ✅ Yes (not blockable) |

> ⚠️ **With Premium subscription: Disable video storage manually!**

### App vs Website - The Crucial Difference

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  RING APP (blockable with Pi-hole)                             │
│  ├── Fetches snapshots via ring.com API                        │
│  ├── Pi-hole blocks ring.com → No snapshot                     │
│  └── ✅ RECOMMENDED: Don't use Ring App                        │
│                                                                 │
│  RING WEBSITE (NOT blockable)                                  │
│  ├── Fetches snapshots via Amazon CDN                          │
│  ├── amazonaws.com not blockable                               │
│  └── ❌ When using website: Snapshot flows to Amazon           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### What Gets Blocked (with Pi-hole)

| Action | Status | Result |
|--------|--------|--------|
| Open Ring App | 🚫 Blocked | App shows error, **no snapshot** |
| Motion events | 🚫 Blocked | No push notifications |
| Cloud video retrieval | 🚫 Blocked | No cloud playback |
| Firmware updates | 🚫 Blocked | Camera stays on old version |

### What CANNOT Be Blocked

| Action | Status | Reason |
|--------|--------|--------|
| Open ring.com website | ⚠️ Not blockable | Uses Amazon CDN (amazonaws.com) |
| Snapshots via website | ⚠️ Not blockable | Camera delivers directly to Amazon CDN |

### Recommendation: RTSP Recorder

| Aspect | Ring Cloud | RTSP Recorder |
|--------|------------|---------------|
| Data to Amazon | ✅ Yes (when using app/web) | ❌ No (completely local) |
| Video storage | Only with Premium (cloud) | ✅ Local (unlimited) |
| Pi-hole blocking | ⚠️ Only for app, not web | Not needed |
| Privacy | ❌ Questionable | ✅ Complete |
| Internet outage | ❌ No function | ✅ Still active |

---

## 🎯 Conclusion

### Key Findings

1. **Without Premium:** Ring stores **no videos** in the cloud - only snapshots when using app/web
2. **With Premium:** All videos are stored → **Disable video storage manually!**
3. **Ring App blockable:** Pi-hole blocks ring.com → No snapshots when opening app
4. **Ring Website NOT blockable:** Snapshots are fetched via Amazon CDN
5. **RTSP Recorder:** Completely local recording without any cloud traffic

### Recommended Configuration

```
┌─────────────────────────────────────────────────────────────────┐
│                    RECOMMENDED CONFIGURATION                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. ✅ Install RTSP Recorder (local recordings)                │
│                                                                 │
│  2. ✅ Pi-hole: Block ring.com (prevents app snapshots)        │
│                                                                 │
│  3. ⚠️ Do NOT open Ring website (ring.com) in browser          │
│     → Snapshots will be sent to Amazon otherwise               │
│                                                                 │
│  4. ⚠️ With Premium: Disable video storage in Ring App         │
│                                                                 │
│  5. ✅ Use Home Assistant for notifications instead of Ring App│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📚 Further Documentation

- [RTSP Recorder README](../README.md)
- [HANDOVER_v1.2.2.md](../HANDOVER_v1.2.2.md)
- [AGENT_PROMPT_v1.2.2.md](../AGENT_PROMPT_v1.2.2.md)
- [German Version / Deutsche Version](RING_AMAZON_DATAFLOW_DE.md)

---

**Created:** February 7, 2026  
**Author:** RTSP Recorder Project
