# 💰 Cloud Subscription Costs vs. Local Recording

> **RTSP Recorder = €0/year** - No subscriptions, no cloud, complete privacy!

## Why Local Recording?

Many popular smart home cameras require **paid cloud subscriptions** to unlock essential features like:
- Video recording and playback
- 24/7 continuous recording
- Extended video history (30-180 days)
- Person/package detection
- Multiple location support

**With RTSP Recorder, you get all of this for FREE:**
- ✅ Local video recording (no cloud required)
- ✅ AI-powered person detection (via Coral TPU)
- ✅ Face recognition with local database
- ✅ Unlimited video history (limited only by storage)
- ✅ Complete privacy - data never leaves your network

---

## Cloud Subscription Costs Comparison (2026)

### Ring (Amazon)

| Plan | Monthly | Yearly | Coverage | Features |
|------|---------|--------|----------|----------|
| **Basic** | €3.99 | €39.99 | 1 device | 180 days history, person alerts |
| **Standard** | €9.99 | €99.99 | All devices, 1 location | + doorbell calls, extended live video |
| **Premium** | €19.99 | **€199.99** | All devices, 1 location | + 24/7 recording, continuous live video |

> ⚠️ **Per location pricing!** Multiple homes = multiple subscriptions

### Google Nest (Home Premium)

| Plan | Monthly | Yearly | Features |
|------|---------|--------|----------|
| **Standard** | ~€6 | ~€60 | 30 days event history |
| **Premium** | ~€12 | ~€120 | 60 days event + 10 days 24/7 |

### Arlo

| Plan | Monthly | Yearly | Features |
|------|---------|--------|----------|
| **Secure** | €2.99 | €29.99 | 1 camera, 30 days |
| **Secure Plus** | €9.99 | €99.99 | Unlimited cameras, 30 days |
| **Safe & Secure Pro** | €14.99 | €149.99 | + 24/7 emergency response |

### Blink (Amazon)

| Plan | Monthly | Yearly | Coverage |
|------|---------|--------|----------|
| **Basic** | €3 | €30 | Per device |
| **Plus** | €10 | €100 | Unlimited devices |

### Wyze

| Plan | Monthly | Yearly | Features |
|------|---------|--------|----------|
| **Cam Plus** | $1.99 | $19.99 | Per camera, person detection |
| **Cam Plus Pro** | $3.99 | $39.99 | + 24/7 recording |

### eufy (Anker)

| Plan | Monthly | Yearly | Features |
|------|---------|--------|----------|
| **None required!** | €0 | €0 | Local storage on HomeBase |

> ✅ eufy is one of the few brands with **local storage by default**

---

## Your Savings with RTSP Recorder

### Single Camera Household

| Scenario | Cloud Cost/Year | With RTSP Recorder | **Annual Savings** |
|----------|-----------------|-------------------|-------------------|
| Ring Basic | €40 | €0 | **€40** |
| Ring Standard | €100 | €0 | **€100** |
| Ring Premium | €200 | €0 | **€200** |

### Multi-Camera Household (3 cameras)

| Scenario | Cloud Cost/Year | With RTSP Recorder | **Annual Savings** |
|----------|-----------------|-------------------|-------------------|
| 3x Ring Basic | €120 | €0 | **€120** |
| Ring Standard | €100 | €0 | **€100** |
| Arlo Secure Plus | €100 | €0 | **€100** |

### Long-Term Savings

| Duration | Ring Premium | With RTSP Recorder | **Total Savings** |
|----------|--------------|-------------------|-------------------|
| 1 year | €200 | €0 | **€200** |
| 3 years | €600 | €0 | **€600** |
| 5 years | €1,000 | €0 | **€1,000** |
| 10 years | €2,000 | €0 | **€2,000** |

---

## Recommended Home Assistant Integrations

To use RTSP Recorder, your cameras need to provide an RTSP stream. Here's how to get RTSP from popular camera systems:

### Native RTSP Support (Recommended)

These cameras support RTSP out of the box:

| Camera System | Home Assistant Integration | Notes |
|---------------|---------------------------|-------|
| **Reolink** | [reolink](https://www.home-assistant.io/integrations/reolink/) | Excellent RTSP support |
| **Tapo (TP-Link)** | [tapo](https://www.home-assistant.io/integrations/tapo/) | Native RTSP |
| **UniFi Protect** | [unifiprotect](https://www.home-assistant.io/integrations/unifiprotect/) | Professional-grade |
| **eufy** | [eufy_security](https://github.com/fuatakgun/eufy_security) | HACS integration |
| **Amcrest** | [amcrest](https://www.home-assistant.io/integrations/amcrest/) | Native RTSP |
| **Dahua** | Manual RTSP URL | Native RTSP |
| **Hikvision** | Manual RTSP URL | Native RTSP |

### RTSP via Bridge/Gateway

These cameras require additional software to provide RTSP:

| Camera System | Solution | Notes |
|---------------|----------|-------|
| **Ring** | [ring-mqtt](https://github.com/tsightler/ring-mqtt) | HA Add-on, provides RTSP gateway |
| **Wyze** | [docker-wyze-bridge](https://github.com/mrlt8/docker-wyze-bridge) | Docker container |
| **Nest** | Not supported | No RTSP available |
| **Blink** | Limited | Experimental solutions only |

---

## Ring Camera Setup Guide

### Step 1: Install ring-mqtt Add-on

1. Go to **Settings → Add-ons → Add-on Store**
2. Search for **ring-mqtt**
3. Click **Install**
4. Configure with your Ring account credentials
5. Start the add-on

### Step 2: Get RTSP Stream URL

After ring-mqtt is running, your cameras will be available at:
```
rtsp://homeassistant.local:8554/ring_camera_name
```

### Step 3: Add to RTSP Recorder

1. Open RTSP Recorder configuration
2. Add a new camera with the RTSP URL from ring-mqtt
3. Configure recording settings
4. Start recording!

> ⚠️ **Important:** The RTSP stream from ring-mqtt still goes through Ring's cloud servers. However, your **recordings are stored locally** on your Home Assistant server, not in Amazon's cloud. This means:
> - ✅ No subscription required for video storage
> - ✅ Unlimited video history
> - ✅ Your recordings stay private
> - ⚠️ Live stream still requires internet (Ring cloud)

---

## Privacy Comparison

| Feature | Cloud Subscription | RTSP Recorder |
|---------|-------------------|---------------|
| **Video Storage** | Cloud (provider's servers) | Local (your server) |
| **Data Access** | Provider + potentially law enforcement | Only you |
| **Internet Required** | Yes, for all features | Only for live stream |
| **Subscription Cost** | €40-200/year | €0 |
| **Video History** | Limited (30-180 days) | Unlimited |
| **Data Privacy** | Subject to provider's policies | Complete control |
| **Face Recognition** | Cloud-based (if available) | Local, private |

---

## Conclusion

RTSP Recorder allows you to:

1. **Save €100-200+ per year** on cloud subscriptions
2. **Keep your video data private** - no cloud storage
3. **Enjoy unlimited video history** - limited only by storage
4. **Use AI features locally** - person detection, face recognition
5. **Maintain complete control** over your surveillance data

**Start saving today - switch to local recording with RTSP Recorder!**

---

*Last updated: February 2026*
*Prices may vary by region. Check provider websites for current pricing.*
