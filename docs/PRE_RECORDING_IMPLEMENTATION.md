# Pre-Recording Implementation Plan

## RTSP Recorder v1.2.0 Feature Specification

**Feature:** Configurable Pre-Recording  
**Status:** Planning Phase  
**Estimated Effort:** 12-16 hours  
**Priority:** High  
**Risk Level:** Medium  

---

## 📋 Executive Summary

Pre-Recording ermöglicht das Aufzeichnen von Video-Frames **vor** dem eigentlichen Motion-Event. Dies löst das Problem, dass bei event-triggered Recording die ersten 1-3 Sekunden verloren gehen (FFmpeg Startup + RTSP Handshake Zeit).

### Problem Statement

```
Aktuell:
═══════════════════════════════════════════════════════════════
        ↓ Motion Event
        │
        ├──┤ FFmpeg Start (0.5-1s)
        │  ├──┤ RTSP Handshake (0.5-1.5s)
        │  │  ├─────────────────────────────────────────────┤
        │  │  │         Aufnahme beginnt HIER               │
        ↓  ↓  ↓                                             ↓
────────────────────────────────────────────────────────────────
   ▓▓▓▓▓▓▓▓ VERLOREN (1-3 Sekunden)

Mit Pre-Recording:
═══════════════════════════════════════════════════════════════
   [═══ Buffer ═══]↓ Motion Event
                   │
                   ├─────────────────────────────────────────┤
   ├───────────────┼─────────────────────────────────────────┤
   │  Pre-Record   │         Live Recording                  │
   │  (5-10 Sek)   │                                         │
   ↓               ↓                                         ↓
────────────────────────────────────────────────────────────────
   NICHTS VERLOREN - Komplette Szene aufgezeichnet
```

---

## 🏗️ Architecture Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     RTSP Recorder v1.2.0                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │   Camera 1   │───▶│  PreRecordBuffer (optional)          │  │
│  │   RTSP URL   │    │  ┌────────────────────────────────┐  │  │
│  └──────────────┘    │  │  HLS Segment Ring Buffer       │  │  │
│                      │  │  [seg001][seg002][seg003]...   │  │  │
│  ┌──────────────┐    │  └────────────────────────────────┘  │  │
│  │   Camera 2   │───▶│                                      │  │
│  │   RTSP URL   │    │  Continuously writes 2-sec segments  │  │
│  └──────────────┘    │  Keeps last N segments (configurable)│  │
│                      └──────────────────────────────────────┘  │
│         ...                          │                          │
│                                      ▼                          │
│                      ┌──────────────────────────────────────┐  │
│                      │        Motion Event Trigger          │  │
│                      └──────────────────────────────────────┘  │
│                                      │                          │
│                                      ▼                          │
│                      ┌──────────────────────────────────────┐  │
│                      │      PreRecordManager                │  │
│                      │  1. Pause buffer writing             │  │
│                      │  2. Copy existing segments           │  │
│                      │  3. Start live recording             │  │
│                      │  4. Concat pre + live                │  │
│                      │  5. Resume buffer writing            │  │
│                      └──────────────────────────────────────┘  │
│                                      │                          │
│                                      ▼                          │
│                      ┌──────────────────────────────────────┐  │
│                      │     Final MP4 with Pre-Recording     │  │
│                      └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        __init__.py                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ async_setup_entry()                                      │   │
│  │   - Initialize PreRecordManager for configured cameras   │   │
│  │   - Start buffer processes                               │   │
│  │   - Register cleanup handlers                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ handle_save_recording()                                  │   │
│  │   - Check if camera has pre-record enabled               │   │
│  │   - If yes: call PreRecordManager.record_with_prebuffer()│   │
│  │   - If no:  call async_record_stream() (existing)        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      pre_record.py (NEW)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ class PreRecordBuffer                                    │   │
│  │   - __init__(rtsp_url, camera_name, buffer_seconds)      │   │
│  │   - async start() -> Start FFmpeg HLS process            │   │
│  │   - async stop() -> Stop FFmpeg, cleanup                 │   │
│  │   - async get_segments() -> Return current segment files │   │
│  │   - async health_check() -> Verify buffer is running     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ class PreRecordManager                                   │   │
│  │   - __init__(hass, config)                               │   │
│  │   - async initialize() -> Start all buffers              │   │
│  │   - async shutdown() -> Stop all buffers                 │   │
│  │   - async record_with_prebuffer(camera, duration, path)  │   │
│  │   - async _concat_segments(segments, live, output)       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        recorder.py                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ async_record_stream() - EXISTING (no changes needed)     │   │
│  │   - Used by PreRecordManager for live portion            │   │
│  │   - Also used directly when pre-record disabled          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 File Changes Required

### New Files

| File | Purpose | LOC Estimate |
|------|---------|--------------|
| `pre_record.py` | PreRecordBuffer & PreRecordManager classes | 250-300 |

### Modified Files

| File | Changes | LOC Delta |
|------|---------|-----------|
| `const.py` | New constants for pre-recording | +15 |
| `config_flow.py` | New config options per camera | +30 |
| `__init__.py` | Initialize PreRecordManager, modify save_recording | +50 |
| `strings.json` | UI labels for pre-record options | +10 |
| `translations/de.json` | German translations | +10 |
| `translations/en.json` | English translations | +10 |

**Total New Code:** ~375 LOC

---

## 🔧 Implementation Details

### Phase 1: Constants & Configuration (2 hours)

#### 1.1 const.py additions

```python
# Pre-Recording Configuration
DEFAULT_PRE_RECORD_SECONDS = 0  # Disabled by default
MIN_PRE_RECORD_SECONDS = 0
MAX_PRE_RECORD_SECONDS = 30
PRE_RECORD_SEGMENT_DURATION = 2  # HLS segment length in seconds
PRE_RECORD_BUFFER_DIR = "/tmp/rtsp_prerecord"

# Pre-Recording resource limits
PRE_RECORD_MAX_CAMERAS = 10  # Max cameras with pre-record enabled
PRE_RECORD_HEALTH_CHECK_INTERVAL = 60  # Seconds between health checks
PRE_RECORD_RESTART_DELAY = 5  # Seconds to wait before restart on failure
```

#### 1.2 config_flow.py additions

```python
# In CAMERA_SCHEMA:
vol.Optional(CONF_PRE_RECORD_SECONDS, default=DEFAULT_PRE_RECORD_SECONDS): vol.All(
    vol.Coerce(int),
    vol.Range(min=MIN_PRE_RECORD_SECONDS, max=MAX_PRE_RECORD_SECONDS)
),

# In options flow step:
data_schema = vol.Schema({
    # ... existing options ...
    vol.Optional(
        CONF_PRE_RECORD_SECONDS,
        default=current_config.get(CONF_PRE_RECORD_SECONDS, 0)
    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
})
```

### Phase 2: PreRecordBuffer Class (4 hours)

#### 2.1 Core Buffer Implementation

```python
class PreRecordBuffer:
    """Manages continuous HLS segment buffer for a single camera."""
    
    def __init__(
        self,
        rtsp_url: str,
        camera_name: str,
        buffer_seconds: int = 10,
        segment_duration: int = 2
    ):
        self.rtsp_url = rtsp_url
        self.camera_name = self._sanitize_name(camera_name)
        self.buffer_seconds = buffer_seconds
        self.segment_duration = segment_duration
        self.segments_dir = Path(PRE_RECORD_BUFFER_DIR) / self.camera_name
        
        # Calculate how many segments to keep
        self.max_segments = (buffer_seconds // segment_duration) + 2
        
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._start_time: datetime | None = None
    
    async def start(self) -> bool:
        """Start the continuous HLS recording process."""
        async with self._lock:
            if self._running:
                return True
            
            # Create segments directory
            self.segments_dir.mkdir(parents=True, exist_ok=True)
            
            # Clean old segments
            await self._cleanup_segments()
            
            # Build FFmpeg command
            cmd = self._build_ffmpeg_command()
            
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE
                )
                self._running = True
                self._start_time = datetime.now()
                
                # Start background monitor
                asyncio.create_task(self._monitor_process())
                
                return True
            except Exception as e:
                _LOGGER.error(f"Failed to start pre-record buffer for {self.camera_name}: {e}")
                return False
    
    def _build_ffmpeg_command(self) -> list[str]:
        """Build FFmpeg HLS command."""
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-timeout", "5000000",
            "-i", self.rtsp_url,
            "-c", "copy",
            "-f", "hls",
            "-hls_time", str(self.segment_duration),
            "-hls_list_size", str(self.max_segments),
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", str(self.segments_dir / "seg%05d.ts"),
            str(self.segments_dir / "playlist.m3u8")
        ]
    
    async def get_segments(self, max_seconds: int | None = None) -> list[Path]:
        """Get current segment files, optionally limited to last N seconds."""
        segments = sorted(self.segments_dir.glob("seg*.ts"), key=lambda p: p.stat().st_mtime)
        
        if max_seconds and segments:
            # Calculate how many segments we need
            needed = (max_seconds // self.segment_duration) + 1
            segments = segments[-needed:]
        
        return segments
    
    async def stop(self) -> None:
        """Stop the buffer process and cleanup."""
        async with self._lock:
            self._running = False
            if self._process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                except Exception:
                    pass
                self._process = None
            
            await self._cleanup_segments()
```

### Phase 3: PreRecordManager Class (4 hours)

#### 3.1 Manager Implementation

```python
class PreRecordManager:
    """Manages pre-record buffers for all configured cameras."""
    
    def __init__(self, hass: HomeAssistant, config: dict):
        self.hass = hass
        self.config = config
        self.buffers: dict[str, PreRecordBuffer] = {}
        self._initialized = False
        self._health_task: asyncio.Task | None = None
    
    async def initialize(self) -> None:
        """Initialize pre-record buffers for configured cameras."""
        cameras = self.config.get("cameras", {})
        
        for cam_name, cam_config in cameras.items():
            pre_seconds = cam_config.get("pre_record_seconds", 0)
            
            if pre_seconds > 0:
                rtsp_url = cam_config.get("rtsp_url")
                if not rtsp_url:
                    continue
                
                buffer = PreRecordBuffer(
                    rtsp_url=rtsp_url,
                    camera_name=cam_name,
                    buffer_seconds=pre_seconds + 5  # Extra margin
                )
                
                if await buffer.start():
                    self.buffers[cam_name] = buffer
                    _LOGGER.info(f"Pre-record buffer started for {cam_name} ({pre_seconds}s)")
        
        # Start health check task
        self._health_task = asyncio.create_task(self._health_check_loop())
        self._initialized = True
    
    async def record_with_prebuffer(
        self,
        camera_name: str,
        duration: int,
        output_path: str,
        pre_seconds: int | None = None
    ) -> bool:
        """Record with pre-buffer included."""
        buffer = self.buffers.get(camera_name)
        
        if not buffer or not buffer.is_running:
            # Fallback to normal recording
            return await async_record_stream(...)
        
        try:
            # 1. Get pre-record segments
            segments = await buffer.get_segments(max_seconds=pre_seconds)
            
            if not segments:
                _LOGGER.warning(f"No pre-record segments for {camera_name}")
                return await async_record_stream(...)
            
            # 2. Start live recording
            live_path = output_path.replace('.mp4', '_live.tmp.mp4')
            live_success = await async_record_stream(
                rtsp_url=buffer.rtsp_url,
                output_path=live_path,
                duration=duration
            )
            
            if not live_success:
                return False
            
            # 3. Concatenate pre + live
            success = await self._concat_segments(segments, live_path, output_path)
            
            # 4. Cleanup temp file
            Path(live_path).unlink(missing_ok=True)
            
            return success
            
        except Exception as e:
            _LOGGER.error(f"Pre-record failed for {camera_name}: {e}")
            return False
    
    async def _concat_segments(
        self,
        segments: list[Path],
        live_path: str,
        output_path: str
    ) -> bool:
        """Concatenate HLS segments with live recording."""
        # Create concat list file
        concat_file = Path(output_path).parent / f".concat_{uuid.uuid4().hex}.txt"
        
        try:
            with open(concat_file, 'w') as f:
                for seg in segments:
                    f.write(f"file '{seg}'\n")
                f.write(f"file '{live_path}'\n")
            
            # FFmpeg concat
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            
            return process.returncode == 0
            
        finally:
            concat_file.unlink(missing_ok=True)
    
    async def shutdown(self) -> None:
        """Stop all buffers and cleanup."""
        if self._health_task:
            self._health_task.cancel()
        
        for buffer in self.buffers.values():
            await buffer.stop()
        
        self.buffers.clear()
        self._initialized = False
```

### Phase 4: Integration (__init__.py) (2 hours)

```python
# In async_setup_entry():
pre_record_manager: PreRecordManager | None = None

# Check if any camera has pre-recording enabled
cameras = hass.data[DOMAIN][entry.entry_id].get("cameras", {})
has_pre_record = any(
    cam.get("pre_record_seconds", 0) > 0 
    for cam in cameras.values()
)

if has_pre_record:
    from .pre_record import PreRecordManager
    pre_record_manager = PreRecordManager(hass, config)
    await pre_record_manager.initialize()
    hass.data[DOMAIN][entry.entry_id]["pre_record_manager"] = pre_record_manager

# In async_unload_entry():
if "pre_record_manager" in hass.data[DOMAIN][entry.entry_id]:
    await hass.data[DOMAIN][entry.entry_id]["pre_record_manager"].shutdown()

# Modify handle_save_recording():
async def handle_save_recording(camera_name, duration, ...):
    pre_record_manager = hass.data[DOMAIN][entry.entry_id].get("pre_record_manager")
    camera_config = cameras.get(camera_name, {})
    pre_seconds = camera_config.get("pre_record_seconds", 0)
    
    if pre_record_manager and pre_seconds > 0:
        # Use pre-recording
        success = await pre_record_manager.record_with_prebuffer(
            camera_name=camera_name,
            duration=duration,
            output_path=output_path,
            pre_seconds=pre_seconds
        )
    else:
        # Normal recording (existing code)
        success = await async_record_stream(...)
```

---

## 📊 Configuration Schema

### Per-Camera Configuration

```yaml
# Example configuration.yaml
rtsp_recorder:
  cameras:
    wohnzimmer:
      rtsp_url: "rtsp://192.168.1.100:554/stream"
      pre_record_seconds: 5  # NEW: 0-30 seconds
      record_duration: 30
      # ... other options
    
    flur:
      rtsp_url: "rtsp://192.168.1.101:554/stream"
      pre_record_seconds: 10  # Different per camera
      record_duration: 20
    
    garage:
      rtsp_url: "rtsp://192.168.1.102:554/stream"
      pre_record_seconds: 0  # Disabled (default)
      record_duration: 60
```

### UI Configuration (Options Flow)

```
┌────────────────────────────────────────────────────────────┐
│                    Camera: Wohnzimmer                       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  RTSP URL:        rtsp://192.168.1.100:554/stream         │
│                                                            │
│  Record Duration: [30        ] seconds                     │
│                                                            │
│  ┌────────────────────────────────────────────────────┐   │
│  │ 🎬 Pre-Recording                                    │   │
│  ├────────────────────────────────────────────────────┤   │
│  │                                                     │   │
│  │  Pre-Record Seconds: [5         ] (0-30)           │   │
│  │                                                     │   │
│  │  ℹ️ Records N seconds BEFORE motion is detected.   │   │
│  │     Set to 0 to disable pre-recording.             │   │
│  │                                                     │   │
│  │  ⚠️ Requires continuous buffering (more CPU/RAM)   │   │
│  │                                                     │   │
│  └────────────────────────────────────────────────────┘   │
│                                                            │
│                              [Save]  [Cancel]              │
└────────────────────────────────────────────────────────────┘
```

---

## 🧪 Testing Strategy

### Unit Tests

| Test | Description |
|------|-------------|
| `test_buffer_start_stop` | Verify buffer starts and stops cleanly |
| `test_segment_creation` | Verify HLS segments are created |
| `test_segment_rotation` | Verify old segments are deleted |
| `test_concat_output` | Verify concatenation produces valid MP4 |
| `test_health_check` | Verify buffer restart on failure |
| `test_config_validation` | Verify config schema validation |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_motion_with_prerecord` | Full flow: motion → pre+live → output |
| `test_multiple_cameras` | Multiple cameras with different settings |
| `test_disable_enable` | Enable/disable pre-record via config |
| `test_fallback_on_failure` | Falls back to normal recording on error |

### Manual Tests

1. **Basic Function:** Trigger motion, verify output includes pre-record footage
2. **Timing Accuracy:** Verify pre-record duration matches configuration
3. **Resource Usage:** Monitor CPU/RAM with multiple cameras
4. **Long-Running:** Run for 24+ hours, check for memory leaks
5. **Network Issues:** Test behavior when RTSP stream temporarily fails

---

## 📈 Resource Impact Analysis

### Per Camera (Pre-Recording Enabled)

| Resource | Idle | During Recording | Notes |
|----------|------|------------------|-------|
| CPU | 2-5% | 5-10% | FFmpeg transcoding |
| RAM | 10-20 MB | 30-50 MB | Segment buffers |
| Disk I/O | 1-3 MB/s | 3-6 MB/s | HLS + output |
| Network | 1-5 Mbps | Same | RTSP stream |

### System Total (5 Cameras with Pre-Recording)

| Metric | Expected | Maximum |
|--------|----------|---------|
| CPU Usage | 10-25% | 50% |
| RAM Usage | 50-100 MB | 250 MB |
| Disk I/O | 5-15 MB/s | 30 MB/s |
| Temp Disk | 50-100 MB | 200 MB |

### Recommendations

- **Raspberry Pi 4:** Max 2-3 cameras with pre-recording
- **Intel NUC / Mini PC:** Max 5-7 cameras
- **Full Server:** Max 10 cameras (configurable limit)

---

## 🚀 Rollout Plan

### Phase 1: Development (Week 1)
- [ ] Implement PreRecordBuffer class
- [ ] Implement PreRecordManager class
- [ ] Add configuration options
- [ ] Basic unit tests

### Phase 2: Integration (Week 2)
- [ ] Integrate with __init__.py
- [ ] Update config_flow.py
- [ ] Add translations
- [ ] Integration tests

### Phase 3: Testing (Week 3)
- [ ] Internal testing (developer)
- [ ] Beta testing (selected users)
- [ ] Performance profiling
- [ ] Bug fixes

### Phase 4: Release (Week 4)
- [ ] Documentation update
- [ ] CHANGELOG update
- [ ] Release v1.2.0-beta
- [ ] Monitor feedback

---

## ⚠️ Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| FFmpeg process crashes | Medium | Medium | Health check + auto-restart |
| High CPU usage | Medium | Medium | Configurable limits, documentation |
| Disk space exhaustion | Low | High | Segment cleanup, size limits |
| Recording gaps during concat | Low | Medium | Overlap strategy, fallback |
| Incompatible RTSP streams | Medium | Low | Clear error messages, disable option |

---

## 📝 Notes & Considerations

### Why HLS Segments Instead of RAM Buffer?

1. **Memory Safety:** Doesn't consume unbounded RAM
2. **Crash Recovery:** Segments persist on disk
3. **Simplicity:** No complex circular buffer management
4. **FFmpeg Native:** Uses built-in HLS muxer

### Alternative Approaches Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| RAM Ring Buffer | Fast, no disk I/O | Complex, crash loses data | ❌ |
| HLS Segments | Simple, persistent | Disk I/O | ✅ Selected |
| Continuous MP4 | Single file | Complex seeking, large files | ❌ |
| Frame Buffer (OpenCV) | Frame-accurate | High CPU, complex | ❌ |

---

## 📚 References

- [FFmpeg HLS Documentation](https://ffmpeg.org/ffmpeg-formats.html#hls-2)
- [FFmpeg Concat Demuxer](https://ffmpeg.org/ffmpeg-formats.html#concat-1)
- [Home Assistant Custom Integration](https://developers.home-assistant.io/docs/creating_integration_manifest)

---

*Document Version: 1.0*  
*Last Updated: 2026-02-02*  
*Author: RTSP Recorder Development Team*
