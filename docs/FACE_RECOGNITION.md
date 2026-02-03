# 🧠 RTSP Recorder - Gesichtserkennung

**Version:** 1.1.0n BETA  
**Letzte Aktualisierung:** 03. Februar 2026

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Personen anlegen](#3-personen-anlegen)
4. [Training mit positiven Samples](#4-training-mit-positiven-samples)
5. [Negative Samples](#5-negative-samples)
6. [Person Detail Popup](#6-person-detail-popup)
7. [Schwellenwerte anpassen](#7-schwellenwerte-anpassen)
8. [Person-Entities für Automationen](#8-person-entities-für-automationen)
9. [Best Practices](#9-best-practices)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Übersicht

Die Gesichtserkennung in RTSP Recorder ermöglicht:

- **Bekannte Personen identifizieren** in Aufnahmen
- **Automatische Benachrichtigungen** bei bestimmten Personen
- **Aktivitäts-Historie** wer wann wo war
- **Home Assistant Automationen** basierend auf Personen

### Wie es funktioniert

```
Video Frame → Face Detection → Embedding Extraction → Matching → Person ID
     ↓              ↓                   ↓                ↓
  MobileNet     512-dim Vector    Cosine Similarity   Threshold
```

### Modelle

| Modell | Zweck | Hardware |
|--------|-------|----------|
| MobileNet V2 | Gesichtserkennung | Coral/CPU |
| EfficientNet-EdgeTPU-S | Embedding-Extraktion | Coral/CPU |

---

## 2. Voraussetzungen

### Hardware

- ✅ Google Coral USB (empfohlen) für schnelle Inferenz
- ⚠️ CPU-only möglich, aber 10x langsamer

### Software

- RTSP Recorder v1.0.7+ 
- Detector Add-on mit Face-Modellen
- SQLite aktiviert (empfohlen für Historie)

### Einstellungen prüfen

In Integration Optionen:

```yaml
analysis_face_enabled: true
analysis_face_confidence: 0.2      # Gesichtserkennung-Schwelle
analysis_face_match_threshold: 0.35 # Matching-Schwelle
```

---

## 3. Personen anlegen

### Via Dashboard

1. Öffne **RTSP Recorder Card**
2. Gehe zum Tab **👥 Personen**
3. Klicke **➕ Neue Person**
4. Gib einen **Namen** ein
5. Bestätige mit **Erstellen**

### Via Service Call

```yaml
service: rtsp_recorder.create_person
data:
  name: "Max Mustermann"
```

### Via WebSocket API

```javascript
hass.callWS({
  type: 'rtsp_recorder/people_action',
  action: 'create',
  name: 'Max Mustermann'
});
```

---

## 4. Training mit positiven Samples

### Schritt 1: Analyse durchführen

1. Nimm ein Video auf, in dem die Person gut sichtbar ist
2. Führe **Analyse** durch (manuell oder automatisch)
3. Warte auf Abschluss

### Schritt 2: Gesichter zuweisen

1. Öffne das analysierte Video im Dashboard
2. Klicke auf **Detection Overlay**
3. Du siehst erkannte Gesichter mit **"Unbekannt"**
4. Klicke auf ein Gesicht
5. Wähle **"Zu Person hinzufügen"**
6. Wähle die Person aus der Liste

### Schritt 3: Mehrere Samples hinzufügen

**Empfehlung:** 5-10 Samples pro Person für gute Erkennung

| Sample-Typ | Wichtigkeit |
|------------|-------------|
| Frontal, gutes Licht | ⭐⭐⭐⭐⭐ |
| Leicht seitlich | ⭐⭐⭐⭐ |
| Verschiedene Beleuchtung | ⭐⭐⭐⭐ |
| Mit Brille / ohne | ⭐⭐⭐ |
| Verschiedene Entfernungen | ⭐⭐⭐ |

### Schritt 4: Training verifizieren

Nach dem Hinzufügen von Samples:

1. Gehe zu **Personen** → Wähle Person
2. Prüfe **Sample-Anzahl**
3. Führe eine neue Analyse durch
4. Die Person sollte jetzt erkannt werden

---

## 5. Negative Samples

### Was sind Negative Samples?

Negative Samples sind Gesichter, die **NICHT** zu einer Person gehören, aber fälschlicherweise zugeordnet wurden.

### Wann verwenden?

- Falsch-positive Erkennungen reduzieren
- Ähnlich aussehende Personen unterscheiden
- Haustiere oder Bilder ausschließen

### Negative Sample hinzufügen

1. Bei einer falschen Erkennung:
2. Klicke auf das falsch erkannte Gesicht
3. Wähle **"Als negatives Sample markieren"**
4. Wähle die Person, der es NICHT gehört

### Schwellenwert

Wenn mehr als **75%** der Embeddings einer Person als negativ markiert sind, wird das Matching blockiert.

---

## 6. Person Detail Popup

**NEU in v1.1.0n** - Klicke auf einen Personennamen im People-Tab um das Detail-Popup zu öffnen.

### Was wird angezeigt?

| Bereich | Beschreibung |
|---------|--------------|
| **Positive Samples** | Alle Gesichtsbilder, die dieser Person zugeordnet sind |
| **Negative Samples** | Bilder, die NICHT diese Person zeigen (korrigierte Fehlerkennungen) |
| **Erkennungen** | Wie oft wurde diese Person insgesamt erkannt |
| **Zuletzt gesehen** | Datum, Uhrzeit und Kamera der letzten Erkennung |

### Samples verwalten

Im Popup kannst du:

1. **Alle Samples einsehen** mit Datum der Erstellung
2. **Einzelne Samples löschen** durch Klick auf das rote ✕
3. **Statistiken prüfen** zur Qualitätskontrolle

### Popup öffnen

1. Gehe zu **👥 Personen**-Tab
2. Klicke auf den **blauen, unterstrichenen Namen** einer Person
3. Das Popup öffnet sich mit allen Details

### Wann Samples löschen?

- **Positive löschen**: Wenn ein falsches Bild zugeordnet wurde
- **Negative löschen**: Wenn ein Bild fälschlich als "nicht diese Person" markiert wurde

---

## 7. Schwellenwerte anpassen

### Face Confidence (Gesichtserkennung)

```yaml
analysis_face_confidence: 0.2  # Standard
```

| Wert | Effekt |
|------|--------|
| 0.1 | Mehr Gesichter erkannt, mehr False Positives |
| 0.2 | **Empfohlen** - Gute Balance |
| 0.3 | Weniger Gesichter, höhere Qualität |
| 0.5 | Nur sehr deutliche Gesichter |

### Face Match Threshold (Matching)

```yaml
analysis_face_match_threshold: 0.35  # Standard
```

| Wert | Effekt |
|------|--------|
| 0.25 | Streng - Weniger Matches, weniger Fehler |
| 0.35 | **Empfohlen** - Gute Balance |
| 0.45 | Locker - Mehr Matches, mehr False Positives |
| 0.55 | Sehr locker - Hohe Fehlerrate |

### Per-Kamera Schwellenwerte

In den Optionen kannst du pro Kamera anpassen:

```yaml
detector_confidence_Wohnzimmer: 0.6  # Höher für gut beleuchtete Räume
detector_confidence_Flur: 0.4        # Niedriger für schwierige Bedingungen
```

---

## 8. Person-Entities für Automationen

**NEU in v1.1.0n** - Erstelle automatisch Home Assistant Entities für erkannte Personen.

### Aktivieren

1. Gehe zu **Einstellungen** → **Geräte & Dienste** → **RTSP Recorder**
2. Klicke auf **Konfigurieren**
3. Aktiviere **Person-Entities erstellen** ✅

### Erstellte Entities

Für jede Person wird automatisch ein Binary Sensor erstellt:

```yaml
binary_sensor.rtsp_person_max_mustermann:
  state: "on"  # Wenn kürzlich erkannt (letzte 5 Minuten)
  attributes:
    last_seen: "2026-02-03T14:30:00"
    last_camera: "Wohnzimmer"
    confidence: 0.87
    total_sightings: 42
```

### Automatisierungen erstellen

**Beispiel 1: Benachrichtigung wenn Person erkannt**

```yaml
automation:
  - alias: "Max erkannt - Benachrichtigung"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_max_mustermann
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "👤 Person erkannt"
          message: "Max wurde bei {{ trigger.to_state.attributes.last_camera }} gesehen"
          data:
            image: "/local/thumbnails/{{ trigger.to_state.attributes.last_camera }}/latest.jpg"
```

**Beispiel 2: Licht einschalten bei Ankunft**

```yaml
automation:
  - alias: "Willkommen zuhause"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_max_mustermann
        to: "on"
    condition:
      - condition: state
        entity_id: sun.sun
        state: "below_horizon"
    action:
      - service: light.turn_on
        target:
          entity_id: light.flur
```

**Beispiel 3: Unbekannte Person erkannt**

```yaml
automation:
  - alias: "Unbekannte Person Alarm"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_unknown
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "⚠️ Unbekannte Person"
          message: "Unbekannte Person bei {{ trigger.to_state.attributes.last_camera }} erkannt"
          data:
            tag: "unknown_person"
            importance: high
```

### Erkennungs-Timeout

- Person-Entity geht auf `off` nach **5 Minuten** ohne neue Erkennung
- Bei erneuter Erkennung wechselt es zurück auf `on`

### Entity-Benennung

| Person-Name | Entity-ID |
|-------------|-----------|
| Max Mustermann | `binary_sensor.rtsp_person_max_mustermann` |
| Max | `binary_sensor.rtsp_person_max` |
| Unknown | `binary_sensor.rtsp_person_unknown` |

---

## 9. Best Practices

### ✅ Do's

| Empfehlung | Grund |
|------------|-------|
| 5-10 Samples pro Person | Bessere Genauigkeit |
| Verschiedene Winkel | Robustere Erkennung |
| Gute Beleuchtung bevorzugen | Höhere Qualität |
| Negative Samples nutzen | Weniger False Positives |
| Person Detail Popup prüfen | Qualitätskontrolle der Samples |
| Person-Entities für Automationen | Smart Home Integration |

### ❌ Don'ts

| Vermeiden | Grund |
|-----------|-------|
| Nur 1-2 Samples | Unzuverlässige Erkennung |
| Unscharfe Bilder als Sample | Schlechte Embeddings |
| Zu niedrige Schwellenwerte | Viele Fehlerkennungen |
| Zu viele Personen (>50) | Performance-Impact |
| Samples nie überprüfen | Schlechte Trainingsdaten akkumulieren |

### Optimale Kamera-Einstellungen

```
Auflösung: 1080p (min. 720p)
Framerate: 15+ fps
Codec: H.264
Beleuchtung: Gute Ausleuchtung des Gesichts
Winkel: Frontal bis 45° zur Kamera
```

---

## 10. Troubleshooting

### Problem: Keine Gesichter erkannt

**Ursachen:**
1. Face Detection deaktiviert
2. Confidence zu hoch
3. Schlechte Videoqualität

**Lösung:**
```yaml
# Prüfe Einstellungen
analysis_face_enabled: true
analysis_face_confidence: 0.2  # Senken wenn nötig
```

### Problem: Falsche Person erkannt

**Ursachen:**
1. Zu wenige Samples
2. Match Threshold zu hoch
3. Ähnlich aussehende Personen

**Lösung:**
1. Mehr Samples hinzufügen
2. Negative Samples für Verwechslungen
3. Threshold senken: `0.35 → 0.30`

### Problem: Person wird nicht mehr erkannt

**Ursachen:**
1. Aussehen verändert (Bart, Brille, Frisur)
2. Andere Beleuchtung
3. Anderer Kamerawinkel

**Lösung:**
1. Neue Samples mit aktuellem Aussehen hinzufügen
2. Alte Samples behalten (für Variation)

### Problem: Zu viele False Positives

**Ursachen:**
1. Match Threshold zu hoch
2. Zu wenige negative Samples
3. Bilder/Poster werden erkannt

**Lösung:**
1. Threshold senken: `0.35 → 0.30`
2. False Positives als negative Samples markieren
3. Bilder/Poster-Bereiche von Detection ausschließen

### Logs prüfen

```bash
# Auf HA Server
grep -i "face\|person\|embedding" /config/home-assistant.log | tail -50
```

---

## Erweitert: Embedding-Qualität

### Embedding-Statistiken abrufen

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

### SQLite-Abfragen

```sql
-- Erkennungs-Historie
SELECT * FROM recognition_history 
WHERE person_id = 'abc123' 
ORDER BY timestamp DESC 
LIMIT 10;

-- Statistiken pro Person
SELECT person_id, COUNT(*) as sightings 
FROM recognition_history 
GROUP BY person_id;
```

---

## Siehe auch

- 📖 [Benutzerhandbuch](USER_GUIDE.md)
- ⚙️ [Konfiguration](CONFIGURATION.md)
- 🔧 [Troubleshooting](TROUBLESHOOTING.md)

---

*Bei Problemen: [GitHub Issues](https://github.com/brainAThome/RTSP-Recorder/issues)*
