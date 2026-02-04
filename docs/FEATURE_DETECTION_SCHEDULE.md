# Feature: Detection Schedule (Erkennungs-Zeitplan)

## Übersicht

Dieses Feature ermöglicht es, für jede Kamera individuelle Zeitpläne zu definieren, wann die lokale Personen-/Objekterkennung aktiv sein soll.

**Version:** 1.2.0 (geplant)

## Motivation

- **Privatsphäre**: Ring Motion Detection kann komplett deaktiviert werden → kein Traffic zu Amazon
- **Performance**: CPU/Coral-TPU-Last nur wenn nötig
- **Flexibilität**: Unterschiedliche Erkennungsprofile für Tag/Nacht
- **Lokale Kontrolle**: Unabhängig von Cloud-Diensten

## Feature-Beschreibung

### Zeitplan-Modi

| Modus | Beschreibung |
|-------|--------------|
| `always` | Erkennung immer aktiv (Standard) |
| `scheduled` | Erkennung nur innerhalb definierter Zeiten |
| `disabled` | Erkennung immer deaktiviert |
| `home_away` | Basierend auf HA-Anwesenheitsstatus |

### Konfigurationsoptionen pro Kamera

```yaml
# Beispiel-Konfiguration
detection_schedule:
  Wohnzimmer:
    mode: "scheduled"
    schedule:
      - start: "22:00"
        end: "06:00"
        days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    objects_during_schedule: ["person"]
    objects_outside_schedule: []
    face_recognition_scheduled_only: true
    
  Haustür:
    mode: "always"
    objects: ["person", "car"]
    
  Garten:
    mode: "home_away"
    home_entity: "person.sven"
    when_home: []  # Keine Erkennung wenn zuhause
    when_away: ["person", "car"]
```

---

## Technische Implementierung

### 1. Neue Konstanten (`const.py`)

```python
# ===== Detection Schedule (v1.2.0) =====
CONF_DETECTION_SCHEDULE = "detection_schedule"
CONF_SCHEDULE_MODE = "schedule_mode"
CONF_SCHEDULE_START = "schedule_start"
CONF_SCHEDULE_END = "schedule_end"
CONF_SCHEDULE_DAYS = "schedule_days"
CONF_SCHEDULE_OBJECTS = "schedule_objects"
CONF_SCHEDULE_OUTSIDE_OBJECTS = "schedule_outside_objects"
CONF_SCHEDULE_FACE_ONLY = "schedule_face_recognition_only"
CONF_SCHEDULE_HOME_ENTITY = "schedule_home_entity"

# Schedule Mode Values
SCHEDULE_MODE_ALWAYS = "always"
SCHEDULE_MODE_SCHEDULED = "scheduled"
SCHEDULE_MODE_DISABLED = "disabled"
SCHEDULE_MODE_HOME_AWAY = "home_away"

# Default Schedule
DEFAULT_SCHEDULE_MODE = SCHEDULE_MODE_ALWAYS
DEFAULT_SCHEDULE_START = "22:00"
DEFAULT_SCHEDULE_END = "06:00"
DEFAULT_SCHEDULE_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# WebSocket Types
WS_TYPE_GET_DETECTION_SCHEDULE = f"{DOMAIN}/get_detection_schedule"
WS_TYPE_SET_DETECTION_SCHEDULE = f"{DOMAIN}/set_detection_schedule"
```

---

### 2. Schedule-Utility-Funktionen (`schedule_utils.py` - NEU)

```python
"""Detection Schedule Utilities for RTSP Recorder."""
import datetime
from typing import Any

from .const import (
    SCHEDULE_MODE_ALWAYS,
    SCHEDULE_MODE_SCHEDULED,
    SCHEDULE_MODE_DISABLED,
    SCHEDULE_MODE_HOME_AWAY,
)


def get_current_weekday() -> str:
    """Return current weekday as short string (mon, tue, etc.)."""
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return days[datetime.datetime.now().weekday()]


def parse_time(time_str: str) -> datetime.time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return datetime.time(int(parts[0]), int(parts[1]))


def is_time_in_range(start: str, end: str, check_time: datetime.time = None) -> bool:
    """Check if current/given time is within range.
    
    Handles overnight ranges (e.g., 22:00 - 06:00).
    """
    if check_time is None:
        check_time = datetime.datetime.now().time()
    
    start_time = parse_time(start)
    end_time = parse_time(end)
    
    if start_time <= end_time:
        # Same-day range (e.g., 08:00 - 18:00)
        return start_time <= check_time <= end_time
    else:
        # Overnight range (e.g., 22:00 - 06:00)
        return check_time >= start_time or check_time <= end_time


def is_schedule_active(schedule_config: dict) -> bool:
    """Check if detection should be active based on schedule config.
    
    Args:
        schedule_config: Schedule configuration dict for a camera
        
    Returns:
        True if detection should be active, False otherwise
    """
    mode = schedule_config.get("mode", SCHEDULE_MODE_ALWAYS)
    
    if mode == SCHEDULE_MODE_ALWAYS:
        return True
    
    if mode == SCHEDULE_MODE_DISABLED:
        return False
    
    if mode == SCHEDULE_MODE_SCHEDULED:
        schedule = schedule_config.get("schedule", {})
        start = schedule.get("start", "22:00")
        end = schedule.get("end", "06:00")
        days = schedule.get("days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        
        current_day = get_current_weekday()
        if current_day not in days:
            return False
        
        return is_time_in_range(start, end)
    
    # SCHEDULE_MODE_HOME_AWAY handled separately (needs hass)
    return True


def get_active_objects(schedule_config: dict, is_active: bool) -> list[str]:
    """Get list of objects to detect based on schedule state.
    
    Args:
        schedule_config: Schedule configuration dict
        is_active: Whether schedule is currently active
        
    Returns:
        List of object types to detect
    """
    if is_active:
        return schedule_config.get("objects_during_schedule", 
                                   schedule_config.get("objects", ["person"]))
    else:
        return schedule_config.get("objects_outside_schedule", [])


def should_run_face_recognition(schedule_config: dict, is_active: bool) -> bool:
    """Check if face recognition should run.
    
    Args:
        schedule_config: Schedule configuration dict
        is_active: Whether schedule is currently active
        
    Returns:
        True if face recognition should run
    """
    face_scheduled_only = schedule_config.get("face_recognition_scheduled_only", False)
    
    if face_scheduled_only:
        return is_active
    
    return True  # Default: Face recognition always on if globally enabled
```

---

### 3. Integration in `services.py`

Die Schedule-Prüfung wird VOR der Analyse eingefügt:

```python
# In _analyze_batch() - nach Zeile ~590 (cam_objects Berechnung)

from .schedule_utils import is_schedule_active, get_active_objects, should_run_face_recognition

# ... existing code ...

cam_objects = config_data.get(f"analysis_objects_{cam_name}", [])
objects_to_use = cam_objects if cam_objects else objects

# ===== NEW: Detection Schedule Check =====
cam_schedule = config_data.get(f"detection_schedule_{cam_name}", {})
schedule_mode = cam_schedule.get("mode", "always")

if schedule_mode != "always":
    schedule_active = is_schedule_active(cam_schedule)
    
    if schedule_mode == "home_away":
        # Check HA entity state
        home_entity = cam_schedule.get("home_entity")
        if home_entity:
            state = hass.states.get(home_entity)
            is_home = state and state.state in ("home", "on", "true")
            schedule_active = not is_home  # Detect when AWAY
    
    if not schedule_active:
        # Get objects for outside-schedule time
        outside_objects = cam_schedule.get("objects_outside_schedule", [])
        if not outside_objects:
            log_to_file(f"Skipping {cam_name}: Schedule not active, no outside-schedule objects")
            continue
        objects_to_use = outside_objects
    else:
        # Use schedule-specific objects if defined
        schedule_objects = cam_schedule.get("objects_during_schedule", [])
        if schedule_objects:
            objects_to_use = schedule_objects
    
    # Check face recognition schedule
    if analysis_face_enabled:
        run_face = should_run_face_recognition(cam_schedule, schedule_active)
        if not run_face:
            log_to_file(f"Face recognition disabled for {cam_name} (outside schedule)")
            # Temporarily disable for this analysis
            face_enabled_for_this = False
        else:
            face_enabled_for_this = True
    else:
        face_enabled_for_this = False
else:
    face_enabled_for_this = analysis_face_enabled
# ===== END Schedule Check =====
```

---

### 4. WebSocket API (`websocket_handlers.py`)

Neue Handler für Schedule-Konfiguration:

```python
# ===== Detection Schedule Handlers =====

@websocket_api.websocket_command({
    vol.Required("type"): "rtsp_recorder/get_detection_schedule",
    vol.Optional("camera"): str,
})
@websocket_api.async_response
async def ws_get_detection_schedule(hass, connection, msg):
    """Get detection schedule configuration."""
    camera = msg.get("camera")
    
    if camera:
        safe_cam = camera.replace(" ", "_").replace("-", "_")
        schedule_key = f"detection_schedule_{safe_cam}"
        schedule = config_data.get(schedule_key, {
            "mode": "always",
            "schedule": {
                "start": "22:00",
                "end": "06:00",
                "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            },
            "objects_during_schedule": [],
            "objects_outside_schedule": [],
            "face_recognition_scheduled_only": False,
            "home_entity": None
        })
        
        # Add current status
        from .schedule_utils import is_schedule_active
        schedule["is_currently_active"] = is_schedule_active(schedule)
        
        connection.send_result(msg["id"], {
            "camera": camera,
            "schedule": schedule
        })
    else:
        # Return all camera schedules
        all_schedules = {}
        for key, value in config_data.items():
            if key.startswith("detection_schedule_"):
                cam_name = key.replace("detection_schedule_", "")
                from .schedule_utils import is_schedule_active
                value["is_currently_active"] = is_schedule_active(value)
                all_schedules[cam_name] = value
        
        connection.send_result(msg["id"], {
            "schedules": all_schedules
        })

websocket_api.async_register_command(hass, ws_get_detection_schedule)


@websocket_api.websocket_command({
    vol.Required("type"): "rtsp_recorder/set_detection_schedule",
    vol.Required("camera"): str,
    vol.Required("schedule"): dict,
})
@websocket_api.async_response
async def ws_set_detection_schedule(hass, connection, msg):
    """Set detection schedule for a camera."""
    try:
        camera = msg["camera"]
        schedule = msg["schedule"]
        
        # Validate schedule
        mode = schedule.get("mode", "always")
        if mode not in ["always", "scheduled", "disabled", "home_away"]:
            raise ValueError(f"Invalid schedule mode: {mode}")
        
        if mode == "scheduled":
            sched = schedule.get("schedule", {})
            if not sched.get("start") or not sched.get("end"):
                raise ValueError("Scheduled mode requires start and end times")
        
        if mode == "home_away":
            if not schedule.get("home_entity"):
                raise ValueError("home_away mode requires home_entity")
        
        safe_cam = camera.replace(" ", "_").replace("-", "_")
        schedule_key = f"detection_schedule_{safe_cam}"
        
        new_data = dict(entry.data)
        new_options = dict(entry.options) if entry.options else {}
        
        new_data[schedule_key] = schedule
        new_options[schedule_key] = schedule
        
        hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
        
        log_to_file(f"Set detection schedule for {camera}: mode={mode}")
        
        connection.send_result(msg["id"], {
            "success": True,
            "camera": camera,
            "schedule": schedule,
            "message": f"Schedule for {camera} updated"
        })
    except Exception as e:
        log_to_file(f"Set detection schedule error: {e}")
        connection.send_result(msg["id"], {
            "success": False,
            "message": str(e)
        })

websocket_api.async_register_command(hass, ws_set_detection_schedule)
```

---

### 5. Dashboard UI (Lovelace Card)

Neuer Tab "Zeitplan" in der RTSP Recorder Card:

```javascript
// In rtsp-recorder-card.js - Schedule Tab

_renderScheduleTab() {
    return html`
        <div class="tab-content schedule-tab">
            <div class="section-header">
                <ha-icon icon="mdi:clock-outline"></ha-icon>
                <span>Erkennungs-Zeitplan</span>
            </div>
            
            ${this._cameras.map(camera => html`
                <div class="camera-schedule-card">
                    <div class="camera-name">${camera.name}</div>
                    
                    <div class="schedule-mode">
                        <label>Modus:</label>
                        <select 
                            @change="${e => this._setScheduleMode(camera.name, e.target.value)}"
                            .value="${this._getScheduleMode(camera.name)}"
                        >
                            <option value="always">Immer aktiv</option>
                            <option value="scheduled">Nach Zeitplan</option>
                            <option value="disabled">Deaktiviert</option>
                            <option value="home_away">Anwesenheit</option>
                        </select>
                    </div>
                    
                    ${this._getScheduleMode(camera.name) === 'scheduled' ? html`
                        <div class="schedule-times">
                            <div class="time-input">
                                <label>Von:</label>
                                <input type="time" 
                                    .value="${this._getScheduleStart(camera.name)}"
                                    @change="${e => this._setScheduleTime(camera.name, 'start', e.target.value)}"
                                />
                            </div>
                            <div class="time-input">
                                <label>Bis:</label>
                                <input type="time" 
                                    .value="${this._getScheduleEnd(camera.name)}"
                                    @change="${e => this._setScheduleTime(camera.name, 'end', e.target.value)}"
                                />
                            </div>
                        </div>
                        
                        <div class="schedule-days">
                            <label>Tage:</label>
                            <div class="day-buttons">
                                ${['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map((day, i) => html`
                                    <button 
                                        class="${this._isDayActive(camera.name, i) ? 'active' : ''}"
                                        @click="${() => this._toggleDay(camera.name, i)}"
                                    >${day}</button>
                                `)}
                            </div>
                        </div>
                        
                        <div class="schedule-objects">
                            <div class="object-group">
                                <label>Erkennung während Zeitplan:</label>
                                <div class="object-chips">
                                    ${['person', 'car', 'dog', 'cat'].map(obj => html`
                                        <span 
                                            class="chip ${this._isObjectActive(camera.name, obj, 'during') ? 'active' : ''}"
                                            @click="${() => this._toggleObject(camera.name, obj, 'during')}"
                                        >${obj}</span>
                                    `)}
                                </div>
                            </div>
                            <div class="object-group">
                                <label>Erkennung außerhalb Zeitplan:</label>
                                <div class="object-chips">
                                    ${['person', 'car', 'dog', 'cat'].map(obj => html`
                                        <span 
                                            class="chip ${this._isObjectActive(camera.name, obj, 'outside') ? 'active' : ''}"
                                            @click="${() => this._toggleObject(camera.name, obj, 'outside')}"
                                        >${obj}</span>
                                    `)}
                                </div>
                            </div>
                        </div>
                    ` : ''}
                    
                    ${this._getScheduleMode(camera.name) === 'home_away' ? html`
                        <div class="home-entity-select">
                            <label>Anwesenheits-Entity:</label>
                            <select 
                                @change="${e => this._setHomeEntity(camera.name, e.target.value)}"
                                .value="${this._getHomeEntity(camera.name)}"
                            >
                                <option value="">Bitte wählen...</option>
                                ${this._personEntities.map(e => html`
                                    <option value="${e}">${e}</option>
                                `)}
                            </select>
                            <p class="hint">Erkennung nur aktiv wenn Person NICHT zuhause</p>
                        </div>
                    ` : ''}
                    
                    <div class="schedule-status">
                        <span class="status-indicator ${this._isScheduleActive(camera.name) ? 'active' : 'inactive'}">
                            ${this._isScheduleActive(camera.name) ? '● Aktiv' : '○ Inaktiv'}
                        </span>
                    </div>
                </div>
            `)}
        </div>
    `;
}
```

---

## Migrations-Strategie

### Upgrade von v1.1.x

- **Keine Breaking Changes**: Kameras ohne Schedule-Config verhalten sich wie bisher (mode: "always")
- **Opt-in Feature**: Schedule wird nur aktiv wenn explizit konfiguriert

### Config Entry Migration

```python
# In __init__.py async_migrate_entry()

if current_version < 5:
    # v1.2.0: Add detection_schedule support
    # No migration needed - missing schedules default to "always" mode
    new_version = 5
```

---

## Test-Szenarien

### Unit Tests

1. **Time Range Tests**
   - Same-day range (08:00 - 18:00)
   - Overnight range (22:00 - 06:00)
   - Edge cases (midnight crossing)

2. **Day Filter Tests**
   - Only weekdays
   - Only weekends
   - Specific days

3. **Object Filter Tests**
   - Different objects during/outside schedule
   - Empty outside-schedule list (skip analysis)

### Integration Tests

1. **Schedule Mode Switching**
   - always → scheduled → disabled → home_away

2. **Home/Away Detection**
   - Entity state changes
   - Missing entity handling

3. **Face Recognition Scheduling**
   - Scheduled-only mode
   - Always-on mode

---

## Zeitplan

| Phase | Aufgabe | Geschätzt |
|-------|---------|-----------|
| 1 | const.py + schedule_utils.py | 1h |
| 2 | services.py Integration | 2h |
| 3 | websocket_handlers.py | 1h |
| 4 | Dashboard UI | 3h |
| 5 | Tests | 2h |
| 6 | Dokumentation | 1h |
| **Total** | | **~10h** |

---

## Offene Fragen

1. **Sollen Aufnahmen auch nach Zeitplan erfolgen oder nur die Analyse?**
   - Aktuelle Annahme: Aufnahmen immer, nur Analyse nach Zeitplan

2. **Home/Away: Mehrere Personen?**
   - Option A: Alle müssen weg sein
   - Option B: Konfigurierbar (any/all)

3. **Benachrichtigungen?**
   - Soll bei Schedule-Wechsel ein Event gefeuert werden?

---

## Zusammenfassung

Dieses Feature ermöglicht:

✅ **Lokale Kontrolle** über Erkennungszeiten  
✅ **Ring Motion Detection AUS** → Kein Cloud-Traffic  
✅ **Granulare Steuerung** pro Kamera  
✅ **Anwesenheitsbasierte Erkennung**  
✅ **Unterschiedliche Objekte** für Tag/Nacht  
✅ **Einfache UI** im Dashboard
