# 🧠 RTSP Recorder - Face Recognition

> 🇩🇪 **[Deutsche Version / German Version](FACE_RECOGNITION_DE.md)**

**Version:** 1.2.2  
**Last Updated:** February 7, 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Creating People](#3-creating-people)
4. [Training with Positive Samples](#4-training-with-positive-samples)
5. [Negative Samples](#5-negative-samples)
6. [Person Detail Popup](#6-person-detail-popup)
7. [Adjusting Thresholds](#7-adjusting-thresholds)
8. [Person Entities for Automations](#8-person-entities-for-automations)
9. [Best Practices](#9-best-practices)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

Face recognition in RTSP Recorder enables:

- **Identify known persons** in recordings
- **Automatic notifications** for specific persons
- **Activity history** of who was where and when
- **Home Assistant automations** based on persons

### How It Works

```
Video Frame → Face Detection → Embedding Extraction → Matching → Person ID
     ↓              ↓                   ↓                ↓
  MobileNet     512-dim Vector    Cosine Similarity   Threshold
```

### Models

| Model | Purpose | Hardware |
|-------|---------|----------|
| MobileNet V2 | Face detection | Coral/CPU |
| EfficientNet-EdgeTPU-S | Embedding extraction | Coral/CPU |

---

## 2. Prerequisites

### Hardware

- ✅ Google Coral USB (recommended) for fast inference
- ⚠️ CPU-only possible, but 10x slower

### Software

- RTSP Recorder v1.0.7+ 
- Detector add-on with face models
- SQLite enabled (recommended for history)

### Check Settings

In integration options:

```yaml
analysis_face_enabled: true
analysis_face_confidence: 0.2      # Face detection threshold
analysis_face_match_threshold: 0.35 # Matching threshold
```

---

## 3. Creating People

### Via Dashboard

1. Open **RTSP Recorder Card**
2. Go to tab **👥 People**
3. Click **➕ New Person**
4. Enter a **name**
5. Confirm with **Create**

### Via Service Call

```yaml
service: rtsp_recorder.create_person
data:
  name: "John Doe"
```

### Via WebSocket API

```javascript
hass.callWS({
  type: 'rtsp_recorder/people_action',
  action: 'create',
  name: 'John Doe'
});
```

---

## 4. Training with Positive Samples

### Step 1: Perform Analysis

1. Record a video where the person is clearly visible
2. Perform **analysis** (manually or automatically)
3. Wait for completion

### Step 2: Assign Faces

1. Open the analyzed video in the dashboard
2. Click on **Detection Overlay**
3. You'll see detected faces with **"Unknown"**
4. Click on a face
5. Select **"Add to Person"**
6. Choose the person from the list

### Step 3: Add Multiple Samples

**Recommendation:** 5-10 samples per person for good recognition

| Sample Type | Importance |
|-------------|------------|
| Frontal, good light | ⭐⭐⭐⭐⭐ |
| Slightly to the side | ⭐⭐⭐⭐ |
| Different lighting | ⭐⭐⭐⭐ |
| With glasses / without | ⭐⭐⭐ |
| Different distances | ⭐⭐⭐ |

### Step 4: Verify Training

After adding samples:

1. Go to **People** → Select person
2. Check **sample count**
3. Run a new analysis
4. The person should now be recognized

---

## 5. Negative Samples

### What Are Negative Samples?

Negative samples are faces that do **NOT** belong to a person, but were incorrectly assigned.

### When to Use?

- Reduce false-positive recognitions
- Distinguish similar-looking persons
- Exclude pets or pictures

### Add Negative Sample

1. On an incorrect recognition:
2. Click on the wrongly recognized face
3. Select **"Mark as negative sample"**
4. Choose the person it does NOT belong to

### Threshold

If more than **75%** of a person's embeddings are marked as negative, matching is blocked.

---

## 6. Person Detail Popup

Click on a person name in the People tab to open the detail popup.

### What Is Shown?

| Area | Description |
|------|-------------|
| **Positive Samples** | All face images assigned to this person |
| **Negative Samples** | Images that do NOT show this person (corrected misrecognitions) |
| **Detections** | How often this person was detected in total |
| **Last Seen** | Date, time and camera of last detection |

### Manage Samples

In the popup you can:

1. **View all samples** with creation date
2. **Delete individual samples** by clicking the red ✕
3. **Check statistics** for quality control

### Open Popup

1. Go to **👥 People** tab
2. Click on the **blue, underlined name** of a person
3. The popup opens with all details

### When to Delete Samples?

- **Delete positive**: If a wrong image was assigned
- **Delete negative**: If an image was incorrectly marked as "not this person"

---

## 7. Adjusting Thresholds

### Face Confidence (Face Detection)

```yaml
analysis_face_confidence: 0.2  # Default
```

| Value | Effect |
|-------|--------|
| 0.1 | More faces detected, more false positives |
| 0.2 | **Recommended** - Good balance |
| 0.3 | Fewer faces, higher quality |
| 0.5 | Only very clear faces |

### Face Match Threshold (Matching)

```yaml
analysis_face_match_threshold: 0.35  # Default
```

| Value | Effect |
|-------|--------|
| 0.25 | Strict - Fewer matches, fewer errors |
| 0.35 | **Recommended** - Good balance |
| 0.45 | Loose - More matches, more false positives |
| 0.55 | Very loose - High error rate |

### Per-Camera Thresholds

In the options you can adjust per camera:

```yaml
detector_confidence_LivingRoom: 0.6  # Higher for well-lit rooms
detector_confidence_Hallway: 0.4      # Lower for difficult conditions
```

---

## 8. Person Entities for Automations

Create automatic Home Assistant entities for detected persons.

### Enable

1. Go to **Settings** → **Devices & Services** → **RTSP Recorder**
2. Click **Configure**
3. Enable **Create Person Entities** ✅

### Created Entities

For each person, a binary sensor is automatically created:

```yaml
binary_sensor.rtsp_person_john_doe:
  state: "on"  # When recently detected (last 5 minutes)
  attributes:
    last_seen: "2026-02-03T14:30:00"
    last_camera: "Living Room"
    confidence: 0.87
    total_sightings: 42
```

### Create Automations

**Example 1: Notification when person detected**

```yaml
automation:
  - alias: "John detected - Notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_john_doe
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "👤 Person detected"
          message: "John was seen at {{ trigger.to_state.attributes.last_camera }}"
          data:
            image: "/local/thumbnails/{{ trigger.to_state.attributes.last_camera }}/latest.jpg"
```

**Example 2: Turn on light on arrival**

```yaml
automation:
  - alias: "Welcome home"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_john_doe
        to: "on"
    condition:
      - condition: state
        entity_id: sun.sun
        state: "below_horizon"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway
```

**Example 3: Unknown person detected**

```yaml
automation:
  - alias: "Unknown person alarm"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_unknown
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "⚠️ Unknown Person"
          message: "Unknown person detected at {{ trigger.to_state.attributes.last_camera }}"
          data:
            tag: "unknown_person"
            importance: high
```

### Detection Timeout

- Person entity goes to `off` after **5 minutes** without new detection
- On renewed detection it switches back to `on`

### Entity Naming

| Person Name | Entity ID |
|-------------|-----------|
| John Doe | `binary_sensor.rtsp_person_john_doe` |
| John | `binary_sensor.rtsp_person_john` |
| Unknown | `binary_sensor.rtsp_person_unknown` |

---

## 9. Best Practices

### ✅ Do's

| Recommendation | Reason |
|----------------|--------|
| 5-10 samples per person | Better accuracy |
| Different angles | More robust recognition |
| Prefer good lighting | Higher quality |
| Use negative samples | Fewer false positives |
| Check Person Detail Popup | Quality control of samples |
| Person entities for automations | Smart home integration |

### ❌ Don'ts

| Avoid | Reason |
|-------|--------|
| Only 1-2 samples | Unreliable recognition |
| Blurry images as sample | Poor embeddings |
| Too low thresholds | Many misrecognitions |
| Too many persons (>50) | Performance impact |
| Never check samples | Bad training data accumulates |

### Optimal Camera Settings

```
Resolution: 1080p (min. 720p)
Framerate: 15+ fps
Codec: H.264
Lighting: Good face illumination
Angle: Frontal to 45° to camera
```

---

## 10. Troubleshooting

### Problem: No Faces Detected

**Causes:**
1. Face detection disabled
2. Confidence too high
3. Poor video quality

**Solution:**
```yaml
# Check settings
analysis_face_enabled: true
analysis_face_confidence: 0.2  # Lower if needed
```

### Problem: Wrong Person Recognized

**Causes:**
1. Too few samples
2. Match threshold too high
3. Similar-looking persons

**Solution:**
1. Add more samples
2. Negative samples for mix-ups
3. Lower threshold: `0.35 → 0.30`

### Problem: Person No Longer Recognized

**Causes:**
1. Appearance changed (beard, glasses, hairstyle)
2. Different lighting
3. Different camera angle

**Solution:**
1. Add new samples with current appearance
2. Keep old samples (for variation)

### Problem: Too Many False Positives

**Causes:**
1. Match threshold too high
2. Too few negative samples
3. Pictures/posters are recognized

**Solution:**
1. Lower threshold: `0.35 → 0.30`
2. Mark false positives as negative samples
3. Exclude picture/poster areas from detection

### Check Logs

```bash
# On HA server
grep -i "face\|person\|embedding" /config/home-assistant.log | tail -50
```

---

## Advanced: Embedding Quality

### Get Embedding Stats

```yaml
service: rtsp_recorder.get_person_stats
data:
  person_id: "abc123"
```

Response:
```json
{
  "total_embeddings": 8,
  "positive_samples": 7,
  "negative_samples": 1,
  "average_confidence": 0.82,
  "last_seen": "2026-02-02T14:30:00"
}
```

### SQLite Queries

```sql
-- Recognition history
SELECT * FROM recognition_history 
WHERE person_id = 'abc123' 
ORDER BY timestamp DESC 
LIMIT 10;

-- Statistics per person
SELECT person_id, COUNT(*) as sightings 
FROM recognition_history 
GROUP BY person_id;
```

---

## See Also

- 📖 [User Guide](USER_GUIDE.md)
- ⚙️ [Configuration](CONFIGURATION.md)
- 🔧 [Troubleshooting](TROUBLESHOOTING.md)

---

*For problems: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
