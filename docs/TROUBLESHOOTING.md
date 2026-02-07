# 🔧 RTSP Recorder - Troubleshooting

> 🇩🇪 **[Deutsche Version / German Version](TROUBLESHOOTING_DE.md)**

**Version:** 1.2.2  
**Last Updated:** February 7, 2026

---

## Table of Contents

1. [Quick Diagnosis](#1-quick-diagnosis)
2. [Installation & Setup](#2-installation--setup)
3. [Recordings](#3-recordings)
4. [Analysis & Detection](#4-analysis--detection)
5. [Coral USB / TPU](#5-coral-usb--tpu)
6. [Face Recognition](#6-face-recognition)
7. [Dashboard Card](#7-dashboard-card)
8. [Performance](#8-performance)
9. [Log Analysis](#9-log-analysis)
10. [Common Error Messages](#10-common-error-messages)

---

## 1. Quick Diagnosis

### System Check Commands

```bash
# Integration loaded?
grep -i "rtsp_recorder" /config/home-assistant.log | tail -10

# Detector reachable?
curl http://localhost:5000/info

# Recordings present?
ls -la /media/rtsp_recorder/ring_recordings/*/

# Coral detected?
curl http://localhost:5000/info | grep coral
```

### Status Checklist

| Check | Command | Expected |
|-------|---------|----------|
| HA running | `ha core check` | "Command completed" |
| Integration | `grep rtsp_recorder /config/.storage/core.config_entries` | Entry present |
| Detector | `curl localhost:5000/info` | JSON response |
| Coral | Detector /info | `"coral_available": true` |
| Storage | `df -h /media` | >10% free |

---

## 2. Installation & Setup

### Problem: Integration Not Found

**Symptom:** "rtsp_recorder" doesn't appear in integrations

**Causes & Solutions:**

1. **Files missing**
   ```bash
   ls /config/custom_components/rtsp_recorder/
   # Must contain: __init__.py, manifest.json, etc.
   ```

2. **Manifest invalid**
   ```bash
   python3 -c "import json; json.load(open('/config/custom_components/rtsp_recorder/manifest.json'))"
   ```

3. **Cache problem**
   - Fully restart HA (not just reload)
   - Clear browser cache (Ctrl+Shift+R)

### Problem: Integration Won't Load

**Symptom:** Error during setup

**Check log:**
```bash
grep -i "error.*rtsp" /config/home-assistant.log | tail -20
```

**Common causes:**

| Error | Solution |
|-------|----------|
| ImportError | Check Python dependencies |
| FileNotFoundError | Check paths |
| PermissionError | Check permissions: `chmod -R 755 /config/custom_components/rtsp_recorder` |

---

## 3. Recordings

### Problem: No Recordings on Motion

**Diagnosis:**

1. **Check motion sensor**
   ```yaml
   # In Developer Tools → States
   # Check: binary_sensor.xxx_motion switches to "on"?
   ```

2. **Check event trigger**
   ```bash
   grep -i "motion.*trigger\|recording.*start" /config/home-assistant.log | tail -10
   ```

3. **Camera configuration**
   - Is the camera configured in options?
   - Is the correct motion sensor assigned?

**Solutions:**

| Problem | Solution |
|---------|----------|
| Wrong sensor | Assign correct binary_sensor |
| No RTSP | Check RTSP URL |
| FFmpeg error | Check log, codec issues |

### Problem: Recording Breaks Off

**Symptom:** Recordings are too short or incomplete

**Causes:**

1. **RTSP stream unstable**
   ```bash
   # Test with ffprobe
   ffprobe rtsp://user:pass@ip/stream
   ```

2. **Timeout too short**
   - Check network latency
   - FFmpeg TCP mode already active (default)

3. **Storage full**
   ```bash
   df -h /media
   ```

### Problem: No Thumbnails

**Diagnosis:**
```bash
ls /media/rtsp_recorder/thumbnails/*/
```

**Solutions:**

| Cause | Solution |
|-------|----------|
| Path wrong | Check snapshot_path |
| No permissions | `chmod 755 /media/rtsp_recorder/thumbnails` |
| FFmpeg error | Check codec compatibility |

---

## 4. Analysis & Detection

### Problem: Analysis Won't Start

**Diagnosis:**
```bash
# Detector reachable?
curl -X POST http://localhost:5000/detect \
  -F "image=@test.jpg" 2>&1 | head -5
```

**Solutions:**

| Problem | Solution |
|---------|----------|
| Detector offline | Start add-on |
| URL wrong | Check `analysis_detector_url` |
| Port blocked | Check firewall/Docker network |

### Problem: No Objects Detected

**Causes:**

1. **Confidence too high**
   ```yaml
   # Lower to 0.3 or 0.4
   analysis_detector_confidence: 0.4
   ```

2. **Object not in list**
   ```yaml
   analysis_objects:
     - person
     - car
     - dog  # Add what's missing
   ```

3. **Video quality too low**
   - At least 720p
   - Sufficient lighting

### Problem: Analysis Slow

**CPU mode:**
- Normal: ~500ms/frame
- With Coral: ~50ms/frame

**Solution:** Set up Coral USB

```yaml
analysis_device: coral_usb
```

---

## 5. Coral USB / TPU

### Problem: Coral Not Detected

**Diagnosis:**
```bash
# Check USB devices
lsusb | grep -i google

# Detector log
docker logs addon_local_rtsp_recorder_detector | grep -i coral
```

**Solutions:**

| Problem | Solution |
|---------|----------|
| USB not visible | Check physically, try different port |
| No passthrough | Add-on configuration: `devices: ["/dev/bus/usb"]` |
| Permission denied | Check udev rules |

### Problem: Coral Error "Delegate error"

**Cause:** libedgetpu version incompatible

**Solution:**
```bash
# In add-on container
pip install --upgrade pycoral
```

### Problem: TPU Load Always 0%

**Cause:** No inferences on Coral

**Check:**
```bash
curl http://localhost:5000/info
# "device": "coral_usb" should be displayed
```

---

## 6. Face Recognition

### Problem: No Faces Detected

**Diagnosis:**
1. Face Detection enabled?
   ```yaml
   analysis_face_enabled: true
   ```

2. Confidence too high?
   ```yaml
   analysis_face_confidence: 0.2  # Lower
   ```

3. Face too small in image?
   - At least 50x50 pixels

### Problem: Wrong Person Recognized

**Solutions:**

1. **Lower match threshold**
   ```yaml
   analysis_face_match_threshold: 0.30  # instead of 0.35
   ```

2. **Add negative samples**
   - Mark wrong matches as negative

3. **More training samples**
   - 5-10 different samples per person

### Problem: Person No Longer Recognized

**Cause:** Appearance changed

**Solution:** Add new samples with current appearance

---

## 7. Dashboard Card

### Problem: Card Not Visible

**Diagnosis:**

1. **Resource registered?**
   - Settings → Dashboards → Resources
   - URL: `/local/rtsp-recorder-card.js`

2. **File present?**
   ```bash
   ls -la /config/www/rtsp-recorder-card.js
   ```

3. **Browser cache**
   - Ctrl+Shift+R (Hard Refresh)
   - Test incognito mode

### Problem: Card Shows Error

**"Custom element doesn't exist":**
```yaml
# Re-add resource
type: module
url: /local/rtsp-recorder-card.js?v=1.2.2  # Version parameter
```

### Problem: Videos Won't Load

**Causes:**

| Problem | Solution |
|---------|----------|
| Path wrong | Check storage_path |
| No permissions | `chmod -R 755 /media/rtsp_recorder` |
| CORS error | HA proxy settings |

---

## 8. Performance

### Problem: HA Becomes Slow

**Diagnosis:**
```bash
# CPU load
top -bn1 | head -20

# Memory
free -h

# Disk I/O
iostat -x 1 5
```

**Solutions:**

| Cause | Solution |
|-------|----------|
| Too many recordings | Reduce retention |
| Analysis too frequent | Increase frame_interval |
| SQLite not active | `use_sqlite: true` |

### Problem: Storage Full

**Diagnosis:**
```bash
du -sh /media/rtsp_recorder/*
```

**Solutions:**
1. Reduce retention
2. Manually delete old recordings
3. Expand storage

### Blocking Call Warnings

**Symptom:**
```
Detected blocking call to open... inside the event loop
```

**Explanation:** These warnings are known and non-critical. They affect file I/O operations that are executed synchronously.

**Status:** Low priority - functionality not affected

---

## 9. Log Analysis

### Important Log Lines

```bash
# Successful recording
grep "Recording saved" /config/home-assistant.log

# Analysis results
grep "Analysis complete\|detected" /config/home-assistant.log

# Errors
grep -i "error.*rtsp" /config/home-assistant.log

# Metrics
grep "METRIC" /config/home-assistant.log
```

### Enable Debug Mode

```yaml
# In configuration.yaml
logger:
  default: info
  logs:
    custom_components.rtsp_recorder: debug
    custom_components.rtsp_recorder.analysis: debug
    custom_components.rtsp_recorder.recorder: debug
```

### Log Rotation

```bash
# Clean old logs
truncate -s 0 /config/home-assistant.log
```

---

## 10. Common Error Messages

### "Connection refused to detector"

```
Error connecting to http://local-rtsp-recorder-detector:5000
```

**Solution:**
1. Start add-on
2. Check URL (local vs. Docker network)

### "FFmpeg process failed"

```
FFmpeg exited with code 1
```

**Solutions:**
1. Check RTSP URL
2. Test network connectivity
3. Check camera credentials

### "Permission denied: /media/..."

```
PermissionError: [Errno 13] Permission denied
```

**Solution:**
```bash
chmod -R 755 /media/rtsp_recorder
chown -R root:root /media/rtsp_recorder
```

### "Database is locked"

```
sqlite3.OperationalError: database is locked
```

**Solution:**
1. Restart HA
2. Check WAL mode (default)

### "No module named 'xxx'"

```
ModuleNotFoundError: No module named 'cv2'
```

**Solution:** Dependencies are included in the add-on, not in HA directly.

---

## Support

### Gather Information

Before creating an issue:

```bash
# System info
cat /config/custom_components/rtsp_recorder/manifest.json | grep version

# Recent errors
grep -i error /config/home-assistant.log | tail -50 > error_log.txt

# Configuration (without passwords!)
cat /config/.storage/core.config_entries | grep -A 100 rtsp_recorder
```

### Create Issue

[GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)

Please include:
1. RTSP Recorder version
2. Home Assistant version
3. Error message (complete)
4. Steps to reproduce
5. Relevant logs

---

## See Also

- 📖 [User Guide](USER_GUIDE.md)
- ⚙️ [Configuration](CONFIGURATION.md)
- 🚀 [Installation](INSTALLATION.md)

---

*For problems: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
