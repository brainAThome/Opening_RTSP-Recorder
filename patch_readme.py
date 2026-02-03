#!/usr/bin/env python3
with open('/config/custom_components/rtsp_recorder/README.md', 'r', encoding='utf-8') as f:
    content = f.read()

old_text = '''### Person Management
- 👤 **Person database** with training workflow
- ✅ **Positive samples** for face matching
- ❌ **Negative samples** to prevent false matches (threshold: 75%)
- 🚦 **Optional person entities** for Home Assistant automations
- 🏷️ **Rename and delete** persons from dashboard

### Analysis & Scheduling'''

new_text = '''### Person Management
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

### Analysis & Scheduling'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('/config/custom_components/rtsp_recorder/README.md', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: Added Person Entities & Automations section')
else:
    print('ERROR: Pattern not found')
