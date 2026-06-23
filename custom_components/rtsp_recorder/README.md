# Opening RTSP Recorder for Home Assistant

A complete video surveillance solution with AI-powered object detection using Coral USB EdgeTPU.

![Version](https://img.shields.io/badge/version-1.3.4-brightgreen)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![ISO 25010](https://img.shields.io/badge/ISO%2025010-94%2F100-brightgreen)
![ISO 27001](https://img.shields.io/badge/ISO%2027001-88%2F100-brightgreen)
![Type Hints](https://img.shields.io/badge/Type%20Hints-100%25-brightgreen)
![HACS](https://img.shields.io/badge/HACS-Compatible-orange)

📋 **[Audit Report v1.3.1](../../docs/FINAL_AUDIT_REPORT_v1.3.1.md)** - ISO 25010 + ISO 27001 Quality & Security Analysis

## Version Comparison

| Feature | v1.0.9 STABLE | v1.2.0 | v1.3.4 BETA |
|---------|---------------|--------|-------------|
| **Database** | JSON + optional SQLite | ⚡ SQLite-Only | ⚡ SQLite-Only |
| **Recording** | Sequential | ⚡ Parallel | ⚡ Parallel + Remux |
| **Mobile Video** | ❌ Slow loading | ❌ Slow loading | ✅ Instant (faststart) |
| **Video Endpoint** | ❌ None | ❌ None | ✅ HTTP Range/206 |
| **Recording Completion** | Polling/sleep | ⚡ Callback-based | ⚡ Callback + Remux |
| **Time per Recording** | duration + 5-6s | duration + 1-2s | duration + 1-2s |
| **TPU Load Display** | ❌ Not available | ✅ Real-time | ✅ Real-time |
| **Movement Profile** | ❌ Not available | ✅ Recognition history | ✅ Movement Tab |
| **Languages** | 2 (DE, EN) | 5 (DE, EN, ES, FR, NL) | 5 (DE, EN, ES, FR, NL) |
| **Person Entities** | ❌ | ✅ binary_sensor | ✅ binary_sensor |
| **Push Notifications** | ❌ | ✅ | ✅ |
| **Type Hints** | ~60% | 100% | 100% |
| **Face Recognition** | ✅ | ✅ | ✅ |
| **Coral EdgeTPU** | ✅ | ✅ | ✅ |
| **HACS Compatible** | ✅ | ✅ | ✅ |

## What's New in v1.3.4 BETA

### 📱 Mobile Video Fix (v1.3.3)
- **Instant mobile playback**: Videos now load immediately on mobile devices
  - Root cause: RTSP `-c copy` produces fragmented MP4 (fMP4) with 30+ moof/mdat atoms
  - Fix: Automatic post-recording remux to MP4 with moov atom at start (faststart)
  - Remux takes <1 second per file, runs automatically after every recording
- **Video Streaming Endpoint**: `/api/rtsp_recorder/video/{camera}/{filename}`
  - Proper HTTP Range/206 support for seek and progressive playback
  - Content-Length and Accept-Ranges headers for all browsers
  - Fallback to `/media/` path if endpoint unavailable
- **Batch Migration**: 497 existing videos remuxed on deployment

### 🏷️ Opening Branding (v1.3.1)
- **Unified branding** across all 5 languages
- **Person Detail Popup**: Click person names to see all samples
- **Sample Quality Analysis**: Quality scores with outlier detection
- **Push Notifications**: Alerts when trained persons are recognized
- **Debug Mode**: Toggle for technical diagnostic displays

### 🗄️ SQLite-Only Backend
- **Complete Migration**: JSON database removed, SQLite is now the only backend
  - Automatic one-time migration from JSON on first start
  - Faster queries and ACID-compliant storage

### ⚡ Performance & Architecture
- **Parallel Snapshots**: Thumbnails captured DURING recording (saves 3-5s)
- **Callback-based Recording**: Event-driven completion, no polling
- **Faster Timeline**: Recordings appear immediately with live countdown
- **Movement Profile Tab**: Recognition history with timeline and filters
- **Person Entities**: `binary_sensor.rtsp_person_{name}` for automations

### 📊 Metrics & Monitoring
- **TPU Load Display**: Real-time Coral EdgeTPU utilization (color coded)
- **Performance Metrics**: Structured METRIC logging for analysis
- **Recording Progress**: Live display in footer showing active recordings

## Features (All Versions)

### Recording & Storage
- 🎥 **Motion-triggered recording** from RTSP cameras
- 📁 **Automatic retention management** for recordings and snapshots
- ⏱️ **Configurable recording duration** and snapshot delay
- 🗂️ **Per-camera retention settings** override global defaults
- 📷 **Automatic thumbnail generation** for each recording

### AI Detection
- 🔍 **AI object detection** with Coral USB EdgeTPU support (MobileDet)
- 🧠 **CPU fallback mode** when Coral unavailable
- 🙂 **Face detection** with MobileNet V2
- 🎯 **Face embeddings** for person recognition (EfficientNet-EdgeTPU-S)
- 🏃 **MoveNet pose estimation** for head/body keypoint detection
- 🎚️ **Per-camera detection thresholds** (detector, face confidence, face match)
- ⚙️ **Configurable object filter** per camera (person, car, dog, etc.)

### Person Management
- 👤 **Person database** with training workflow
- ✅ **Positive samples** for face matching
- ❌ **Negative samples** to prevent false matches (threshold: 75%)
- 🚦 **Optional person entities** for Home Assistant automations
- 🏷️ **Rename and delete** persons from dashboard

### Person Entities & Automations

When a trained person is recognized, a sensor entity is created automatically:

**Entity ID:** `sensor.rtsp_person_<name>` (e.g., `sensor.rtsp_person_john`)

**Attributes:**
| Attribute | Description | Example |
|-----------|-------------|---------|
| `person_name` | Name of the person | "John" |
| `camera` | Camera where detected | "Living Room" |
| `similarity` | Recognition confidence | 0.87 |
| `last_seen` | ISO timestamp | 2026-02-01T... |
| `video_path` | Path to recording | /media/... |

**State:** `on` (detected) → `off` (after 10 seconds)

#### Automation Examples

**1. Play music when person arrives in living room:**
```yaml
automation:
  - alias: "Person in Living Room - Play Music"
    trigger:
      - platform: state
        entity_id: sensor.rtsp_person_john
        to: "on"
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.rtsp_person_john', 'camera') == 'Living Room' }}"
    action:
      - service: media_player.play_media
        target:
          entity_id: media_player.living_room_speaker
        data:
          media_content_id: "https://example.com/welcome.mp3"
          media_content_type: "music"
```

**2. Notification when person detected at front door:**
```yaml
automation:
  - alias: "Person at Front Door - Notify"
    trigger:
      - platform: state
        entity_id: sensor.rtsp_person_john
        to: "on"
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.rtsp_person_john', 'camera') == 'Front Door' }}"
    action:
      - service: notify.mobile_app
        data:
          message: "John was detected at the front door!"
```

**3. Turn on lights with high confidence:**
```yaml
automation:
  - alias: "Person Detected - Lights On"
    trigger:
      - platform: state
        entity_id: sensor.rtsp_person_john
        to: "on"
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.rtsp_person_john', 'similarity') | float > 0.85 }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway
```

**4. Generic trigger for any recognized person:**
```yaml
automation:
  - alias: "Any Person Detected - Notify"
    trigger:
      - platform: state
        entity_id:
          - sensor.rtsp_person_john
          - sensor.rtsp_person_jane
          - sensor.rtsp_person_max
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: >
            {{ state_attr(trigger.entity_id, 'person_name') }} detected in 
            {{ state_attr(trigger.entity_id, 'camera') }}!
```

### Analysis & Scheduling
- ⏰ **Automated analysis scheduling** (daily time or interval-based)
- 📊 **Batch analysis** for all recordings with filters
- 🔄 **Skip already analyzed** option for efficiency
- 📈 **Live performance monitoring** (CPU, RAM, Coral stats)

### Dashboard
- 🎛️ **Beautiful Lovelace card** with video playback
- 🖼️ **Timeline view** with thumbnails
- 🔴 **Detection overlay** showing bounding boxes
- 👥 **Persons tab** with training workflow
- ⚡ **Real-time detector stats** panel

## Architecture

### System Overview

```mermaid
flowchart TB
    subgraph HA["Home Assistant"]
        subgraph Integration["Custom Integration"]
            INIT["__init__.py<br/>Main Controller + VideoStreamView"]
            CONFIG["config_flow.py<br/>Configuration UI"]
            RECORDER["recorder.py<br/>Recording Engine + Remux"]
            ANALYSIS["analysis.py<br/>Analysis Pipeline"]
            RETENTION["retention.py<br/>Cleanup Manager"]
            SVCPY["services.py<br/>Service Handler + Post-Remux"]
        end
        
        subgraph Dashboard["Lovelace Card"]
            CARD["rtsp-recorder-card.js"]
        end
        
        WS["WebSocket API"]
        SERVICES["HA Services"]
    end
    
    subgraph Addon["Detector Add-on"]
        APP["app.py<br/>FastAPI Server"]
        subgraph Models["AI Models"]
            DETECT["MobileDet<br/>Object Detection"]
            FACE["MobileNet V2<br/>Face Detection"]
            EMBED["EfficientNet-S<br/>Face Embeddings"]
            POSE["MoveNet<br/>Pose Estimation"]
        end
        CORAL["Coral EdgeTPU"]
        CPU["CPU Fallback"]
    end
    
    subgraph Storage["File System"]
        RECORDINGS["/media/rtsp_recordings"]
        THUMBS["/config/www/thumbnails"]
        DB["/config/rtsp_recorder.db"]
        ANALYSISDIR["/media/rtsp_analysis"]
    end
    
    CAM["RTSP Cameras"] --> RECORDER
    MOTION["Motion Sensors"] --> INIT
    
    INIT --> SVCPY
    INIT --> RECORDER
    INIT --> ANALYSIS
    INIT --> RETENTION
    INIT <--> WS
    INIT <--> SERVICES
    
    SVCPY --> RECORDER
    
    CARD <--> WS
    CARD -->|"/api/rtsp_recorder/video/"| INIT
    
    ANALYSIS <-->|HTTP API| APP
    APP --> DETECT
    APP --> FACE
    APP --> EMBED
    APP --> POSE
    
    DETECT --> CORAL
    FACE --> CORAL
    EMBED --> CORAL
    POSE --> CPU
    
    RECORDER --> RECORDINGS
    RECORDER --> THUMBS
    ANALYSIS --> ANALYSISDIR
    ANALYSIS <--> DB
```

### Recording Flow

```mermaid
sequenceDiagram
    participant MS as Motion Sensor
    participant HA as Home Assistant
    participant INIT as __init__.py
    participant REC as recorder.py
    participant CAM as Camera/RTSP
    participant FS as File System
    participant AN as Analysis
    
    MS->>HA: State: ON
    HA->>INIT: Event Trigger
    INIT->>REC: save_recording()
    REC->>CAM: Start Stream
    
    loop Recording Duration
        CAM-->>REC: Video Frames
        REC-->>FS: Write to .mp4
    end
    
    REC->>FS: Save Thumbnail
    REC->>INIT: Recording Complete
    
    alt Auto-Analyze Enabled
        INIT->>AN: analyze_video()
        AN->>FS: Read Video
        AN-->>FS: Save Results JSON
    end
    
    INIT->>HA: Fire Event
```

### Analysis Pipeline

```mermaid
flowchart LR
    subgraph Input
        VIDEO["Video File<br/>.mp4"]
    end
    
    subgraph FrameExtraction["Frame Extraction"]
        EXTRACT["Extract Frames<br/>every N seconds"]
    end
    
    subgraph Detection["Object Detection"]
        DETECT["MobileDet<br/>Coral/CPU"]
        FILTER["Object Filter<br/>person, car, etc."]
    end
    
    subgraph FaceProcessing["Face Processing"]
        FACEDET["Face Detection<br/>MobileNet V2"]
        FACEEMBED["Face Embedding<br/>EfficientNet-S"]
    end
    
    subgraph PersonMatching["Person Matching"]
        LOADDB["Load Person DB"]
        POSITIVE["Check Positive<br/>Samples"]
        NEGATIVE["Check Negative<br/>Samples ≥75%"]
        MATCH["Final Match<br/>Decision"]
    end
    
    subgraph Output
        RESULT["Analysis Result<br/>.json"]
    end
    
    VIDEO --> EXTRACT
    EXTRACT --> DETECT
    DETECT --> FILTER
    FILTER -->|person detected| FACEDET
    FACEDET --> FACEEMBED
    FACEEMBED --> LOADDB
    LOADDB --> POSITIVE
    POSITIVE -->|similarity > threshold| NEGATIVE
    NEGATIVE -->|not excluded| MATCH
    MATCH --> RESULT
    FILTER -->|other objects| RESULT
```

### AI Models Pipeline

```mermaid
flowchart TB
    subgraph Input["Input Image"]
        IMG["Frame from Video<br/>or Camera"]
    end
    
    subgraph Stage1["Stage 1: Object Detection (MobileDet)"]
        MD["MobileDet SSD<br/>320x320 input"]
        MD_OUT["Bounding Boxes<br/>+ Labels + Confidence"]
    end
    
    subgraph Stage2["Stage 2: Person Detection (MobileDet, label=person)"]
        PERSON_FILTER["Filter: label=person"]
        PERSON_BOX["Person Bounding Box"]
    end
    
    subgraph Stage3["Stage 3: Face Detection (MobileNet V2)"]
        FD["MobileNet V2 Face<br/>320x320 input"]
        FD_OUT["Face Boxes<br/>+ Confidence"]
    end
    
    subgraph Stage4["Stage 4: Face Embedding (EfficientNet-EdgeTPU-S)"]
        FCROP["Crop Face<br/>+ Padding"]
        FE["EfficientNet-EdgeTPU-S<br/>224x224 input"]
        FE_OUT["1280-dim Embedding<br/>Vector"]
    end
    
    subgraph Stage5["Stage 5: Pose (Optional, MoveNet)"]
        MN["MoveNet Lightning<br/>192x192 input"]
        MN_OUT["17 Keypoints<br/>nose, eyes, ears..."]
    end
    
    subgraph Matching["Face Matching"]
        DB[("Person Database<br/>Embeddings")]
        COS["Cosine Similarity"]
        POS["Positive Check<br/>threshold: config"]
        NEG["Negative Check<br/>threshold: 0.75"]
        RESULT["Match Result"]
    end
    
    IMG --> MD
    MD --> MD_OUT
    MD_OUT --> PERSON_FILTER
    PERSON_FILTER --> PERSON_BOX
    PERSON_BOX --> FD
    FD --> FD_OUT
    FD_OUT --> FCROP
    FCROP --> FE
    FE --> FE_OUT
    
    IMG --> MN
    MN --> MN_OUT
    
    FE_OUT --> COS
    DB --> COS
    COS --> POS
    POS --> NEG
    NEG --> RESULT
    
    style MD fill:#e1f5fe
    style PERSON_FILTER fill:#b3e5fc
    style FD fill:#e8f5e9
    style FE fill:#fff3e0
    style MN fill:#fce4ec
```

### Module Interaction

```mermaid
flowchart TB
    subgraph ConfigFlow["config_flow.py"]
        CF_INIT["Initial Setup"]
        CF_OPT["Options Flow"]
        CF_CAM["Camera Config"]
    end
    
    subgraph Init["__init__.py"]
        SETUP["async_setup_entry()"]
        SERVICES["Service Handlers"]
        WS["WebSocket Handlers"]
        ANALYZE["_analyze_video()"]
        BATCH["_analyze_batch()"]
        SCHEDULE["Scheduler"]
    end
    
    subgraph Recorder["recorder.py"]
        SAVE["save_recording()"]
        STREAM["FFmpeg Stream"]
        THUMB["Thumbnail"]
    end
    
    subgraph Analysis["analysis.py"]
        DEVICES["detect_devices()"]
        ANALYZE_VID["analyze_video()"]
        FACE_MATCH["_match_face()"]
        NEG_CHECK["_check_negative()"]
    end
    
    subgraph Retention["retention.py"]
        CLEANUP["cleanup_old_files()"]
        PER_CAM["per_camera_retention()"]
    end
    
    CF_INIT --> SETUP
    CF_OPT --> SETUP
    CF_CAM --> SETUP
    
    SETUP --> SERVICES
    SETUP --> WS
    SETUP --> SCHEDULE
    
    SERVICES --> SAVE
    SERVICES --> ANALYZE
    SERVICES --> BATCH
    SERVICES --> CLEANUP
    
    SCHEDULE --> BATCH
    SCHEDULE --> CLEANUP
    
    SAVE --> STREAM
    SAVE --> THUMB
    SAVE --> ANALYZE
    
    ANALYZE --> ANALYZE_VID
    BATCH --> ANALYZE_VID
    
    ANALYZE_VID --> DEVICES
    ANALYZE_VID --> FACE_MATCH
    FACE_MATCH --> NEG_CHECK
    
    CLEANUP --> PER_CAM
```

### Person Matching Logic

```mermaid
flowchart TB
    START["New Face Embedding"]
    
    subgraph LoadDB["Load Database"]
        LOAD["Load people.json"]
        PEOPLE["Person List"]
    end
    
    subgraph PositiveMatch["Positive Sample Check"]
        FOR_P["For each Person"]
        FOR_E["For each Embedding"]
        COS_P["Cosine Similarity"]
        THRESH_P{"similarity ><br/>face_threshold?"}
    end
    
    subgraph NegativeCheck["Negative Sample Check"]
        HAS_NEG{"Has Negative<br/>Samples?"}
        FOR_N["For each Negative"]
        COS_N["Cosine Similarity"]
        THRESH_N{"similarity ><br/>0.75?"}
    end
    
    subgraph Result["Match Result"]
        MATCH["✅ MATCH<br/>person_id"]
        REJECT["❌ REJECTED<br/>negative match"]
        UNKNOWN["❓ UNKNOWN<br/>no match"]
    end
    
    START --> LOAD
    LOAD --> PEOPLE
    PEOPLE --> FOR_P
    FOR_P --> FOR_E
    FOR_E --> COS_P
    COS_P --> THRESH_P
    
    THRESH_P -->|Yes| HAS_NEG
    THRESH_P -->|No| FOR_P
    
    HAS_NEG -->|No| MATCH
    HAS_NEG -->|Yes| FOR_N
    FOR_N --> COS_N
    COS_N --> THRESH_N
    
    THRESH_N -->|Yes| REJECT
    THRESH_N -->|No| FOR_N
    FOR_N -->|all checked| MATCH
    
    FOR_P -->|no matches| UNKNOWN
    
    style MATCH fill:#c8e6c9
    style REJECT fill:#ffcdd2
    style UNKNOWN fill:#fff9c4
```

## Components

### 1. Custom Integration (`/custom_components/rtsp_recorder/`)

**20+ Python Modules (~12,000 LOC):**

| Module | Description | LOC |
|--------|-------------|-----|
| `__init__.py` | Main controller, service registration, VideoStreamView | ~1,100 |
| `config_flow.py` | Configuration UI wizard | ~1,200 |
| `analysis.py` | AI analysis pipeline | ~1,400 |
| `websocket_handlers.py` | Real-time WebSocket API (20+ commands) | ~1,100 |
| `services.py` | HA service implementations + post-recording remux | ~1,000 |
| `database.py` | SQLite database operations | ~750 |
| `people_db.py` | Person/face database management | ~500 |
| `recorder.py` | FFmpeg recording engine + remux function | ~400 |
| `retention.py` | Cleanup & retention manager | ~140 |
| `helpers.py` | Utility functions | ~350 |
| `face_matching.py` | Face embedding comparison | ~280 |
| `analysis_helpers.py` | Analysis utility functions | ~220 |
| `rate_limiter.py` | DoS protection via token bucket (module present; **inactive** in v1.4.0, opt-in planned) | ~100 |
| `exceptions.py` | 20+ custom exception types | ~150 |
| `performance.py` | Operations metrics | ~120 |
| `migrations.py` | Database schema versioning | ~80 |
| `const.py` | Constants & defaults | ~70 |
| `strings.json` | UI strings definition (5 languages) | - |
| `services.yaml` | Service definitions | - |
| `manifest.json` | Integration manifest | - |

The main Home Assistant integration that handles:
- Recording management with motion triggers
- Post-recording MP4 remux for mobile compatibility (faststart)
- Video streaming endpoint with HTTP Range/206 support
- Per-camera configuration (retention, objects, thresholds)
- Analysis job scheduling (auto, batch, manual)
- Face matching with person database (positive & negative samples)
- Person entities (`binary_sensor.rtsp_person_{name}`) for automations
- Push notifications on person recognition
- WebSocket API for the dashboard (20+ commands)
- Service calls for external automations
- Movement profile tracking

### 2. Dashboard Card (`/www/rtsp-recorder-card.js`)
A feature-rich Lovelace card providing:
- Video playback with custom streaming endpoint + fallback
- Camera selection and filtering
- Performance monitoring panel (CPU, RAM, Coral)
- Analysis configuration UI
- Recording management (download, delete)
- Persons tab with detail popup, training workflow, and negative samples
- Movement profile tab with recognition history
- Detection overlay with bounding boxes
- Opening branding with debug mode toggle

### 3. Detector Add-on (`/addons/rtsp-recorder-detector/`)
A standalone add-on for object detection:
- Coral USB EdgeTPU support (Frigate-compatible models)
- CPU fallback when Coral unavailable
- MobileDet for object detection
- MobileNet V2 for face detection
- EfficientNet-EdgeTPU-S for face embeddings
- MoveNet for pose/head keypoint detection
- Cached interpreters for optimal performance
- REST API with health, metrics, and reset endpoints

## SQLite Database

The integration uses SQLite for persistent storage of person data and face embeddings.

### Database Schema

```mermaid
erDiagram
    schema_version {
        int version PK
    }
    
    people {
        text id PK
        text name
        text created_at
        text updated_at
    }
    
    face_embeddings {
        int id PK
        text person_id FK
        blob embedding
        text source_file
        text created_at
    }
    
    ignored_embeddings {
        int id PK
        text person_id FK
        blob embedding
        text source_file
        text created_at
    }
    
    recognition_history {
        int id PK
        text person_id FK
        text camera_id
        real confidence
        text source_file
        text recognized_at
    }
    
    people ||--o{ face_embeddings : "has positive"
    people ||--o{ ignored_embeddings : "has negative"
    people ||--o{ recognition_history : "recognized as"
```

### Tables

| Table | Purpose | Indexes |
|-------|---------|--------|
| `schema_version` | Database migration tracking | - |
| `people` | Person records (id, name, timestamps) | - |
| `face_embeddings` | Positive face samples (1280-dim vectors) | `idx_face_person` |
| `ignored_embeddings` | Negative samples for exclusion | `idx_ignored_person` |
| `recognition_history` | Recognition event log | `idx_history_person`, `idx_history_camera` |

### Configuration
- **Mode**: WAL (Write-Ahead Logging) for concurrent access
- **Location**: `/config/rtsp_recorder.db`
- **Backup**: Automatic via SQLite WAL checkpointing

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

### Alternative: HACS Installation

This integration is HACS-compatible:

1. Open HACS → ⋮ Menu → **Custom repositories**
2. Add URL: `https://github.com/brainAThome/Opening_RTSP-Recorder`
3. Category: **Integration**
4. Click **Add** → Install
5. Restart Home Assistant

## Translations

The integration supports multiple languages:

| Language | File | Status |
|----------|------|--------|
| 🇩🇪 German | `translations/de.json` | ✅ Complete |
| 🇬🇧 English | `translations/en.json` | ✅ Complete |
| 🇪🇸 Spanish | `translations/es.json` | ✅ Complete |
| 🇫🇷 French | `translations/fr.json` | ✅ Complete |
| 🇳🇱 Dutch | `translations/nl.json` | ✅ Complete |

Language is automatically selected based on your Home Assistant locale settings.

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

### Card Features
- **Recordings Tab**: Browse, filter, play, download, delete recordings
- **Analysis Tab**: Configure auto-analysis, run batch analysis, view stats
- **Persons Tab**: Manage person database, add/remove samples, train faces
- **Performance Tab**: Live CPU, RAM, Coral metrics

## API Endpoints

### Detector Add-on

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (coral status, uptime) |
| `/info` | GET | Device info (Coral status, versions, models) |
| `/metrics` | GET | Performance metrics (inference times, counts) |
| `/detect` | POST | Run object detection on image |
| `/faces` | POST | Face detection + embeddings extraction |
| `/embed_face` | POST | Extract embedding from cropped face |
| `/faces_from_person` | POST | Detect faces in full person bounding box |
| `/faces_ring` | POST | Multi-face detection with ring buffer |
| `/head_movenet` | POST | MoveNet pose estimation for head detection |
| `/face_status` | GET | Face model status and configuration |
| `/face_reset` | POST | Reset face model interpreter |
| `/tpu_reset` | POST | Reset Coral TPU interpreter |

### Home Assistant Services

| Service | Description |
|---------|-------------|
| `rtsp_recorder.save_recording` | Record a camera (auto-naming) |
| `rtsp_recorder.delete_recording` | Delete a single recording |
| `rtsp_recorder.delete_all_recordings` | Bulk delete with filters (camera, age) |
| `rtsp_recorder.analyze_recording` | Analyze a single recording |
| `rtsp_recorder.analyze_all_recordings` | Batch analyze with filters |

### WebSocket Commands

| Command | Description |
|---------|-------------|
| `rtsp_recorder/get_analysis_overview` | Get analysis history and stats |
| `rtsp_recorder/get_analysis_result` | Get detection results for video |
| `rtsp_recorder/get_detector_stats` | Get live detector performance |
| `rtsp_recorder/get_analysis_config` | Get schedule configuration |
| `rtsp_recorder/set_analysis_config` | Update schedule configuration |
| `rtsp_recorder/set_camera_objects` | Update camera object filter |
| `rtsp_recorder/test_inference` | Run test detection |
| `rtsp_recorder/get_people` | Get person database |
| `rtsp_recorder/add_person` | Create new person |
| `rtsp_recorder/rename_person` | Rename person |
| `rtsp_recorder/delete_person` | Delete person |
| `rtsp_recorder/add_person_embedding` | Add positive sample to person |
| `rtsp_recorder/add_negative_sample` | Add negative sample to person |
| `rtsp_recorder/remove_person_embedding` | Remove a positive sample |
| `rtsp_recorder/remove_negative_sample` | Remove a negative sample |
| `rtsp_recorder/get_person_detail` | Get person detail with all samples |
| `rtsp_recorder/get_movement_data` | Get movement profile data |
| `rtsp_recorder/toggle_debug` | Toggle debug mode |
| `rtsp_recorder/get_camera_thresholds` | Get per-camera thresholds |
| `rtsp_recorder/set_camera_thresholds` | Set per-camera thresholds |

## Troubleshooting

### Coral USB not detected
1. Check USB connection and passthrough
2. Verify with `lsusb` - should show "Global Unichip Corp."
3. Ensure add-on has USB device access
4. Try `/tpu_reset` endpoint to reinitialize

### High inference times
1. Ensure Coral USB is detected (`/info` endpoint)
2. Check interpreter caching is working (`/metrics`)
3. Verify libedgetpu-max is installed
4. Check `/face_status` for face model issues

### Recording not starting
1. Check motion sensor entity ID
2. Verify camera entity or RTSP URL
3. Check storage path permissions
4. Ensure retention settings allow new files

### Face matching issues
1. Add more positive samples (3-5 recommended)
2. Use negative samples to exclude false matches
3. Adjust per-camera face thresholds
4. Check face confidence threshold in config

## Version History

See [CHANGELOG.md](../../CHANGELOG.md) for detailed release notes.

### v1.3.4 BETA - February 2026
- 📱 Mobile video fix confirmed working
- Version bump after production verification

### v1.3.3 BETA - February 2026
- 📱 **Mobile Video Fix**: fMP4 → MP4 remux with faststart
- 🌐 **Video Streaming Endpoint**: HTTP Range/206 support
- 🔧 **Post-Recording Remux**: Automatic in services.py after every recording
- 📦 **Batch Migration**: 497 existing videos converted

### v1.3.2 BETA - February 2026
- 🔍 Diagnostic version for mobile video investigation

### v1.3.1 BETA - February 2026
- 🏷️ Opening Branding mit einheitlichem Design
- 👤 Person Detail Popup mit Sample-Übersicht
- 📊 Sample Quality Analysis mit Outlier-Erkennung
- 📲 Push Notifications bei Personenerkennung

### v1.0.9 STABLE - February 2026
- 🗄️ SQLite database with WAL mode
- 🌐 Multi-language support (DE, EN)
- 📦 HACS compatibility
- ✅ ISO 25010: 93.8% | ISO 27001: 91.2%

## Audit Report

See [FINAL_AUDIT_REPORT_v1.3.1.md](../../docs/FINAL_AUDIT_REPORT_v1.3.1.md) for the comprehensive ISO 25010 + ISO 27001 audit report.

### Audit Summary v1.3.1

| Category | Score | Status |
|----------|-------|--------|
| **ISO 25010** (Software Quality) | 94/100 | ✅ Excellent |
| **ISO 27001** (Information Security) | 88/100 | ✅ Good |
| **Overall Score** | 91/100 | ✅ EXCELLENT |
| Critical Findings | 0 | ✅ |
| High Findings | 0 | ✅ |
| Medium Findings | 0 | ✅ |

## License

MIT License - See LICENSE file for details.

## Credits

- Built for Home Assistant
- Coral USB support inspired by Frigate NVR
- Uses TensorFlow Lite Runtime
- Models from Google Coral test data

