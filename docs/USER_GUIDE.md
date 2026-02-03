# RTSP Recorder - Benutzerhandbuch

**Version:** 1.1.0n BETA  
**Datum:** Februar 2026  
**Kompatibilität:** Home Assistant 2024.1+

---

## Inhaltsverzeichnis

1. [Einführung](#1-einführung)
2. [Installation](#2-installation)
3. [Erste Schritte](#3-erste-schritte)
4. [Dashboard Card](#4-dashboard-card)
5. [Aufnahmen & Timeline](#5-aufnahmen--timeline)
6. [KI-Analyse](#6-ki-analyse)
7. [Personen-Erkennung](#7-personen-erkennung)
8. [Einstellungen im Detail](#8-einstellungen-im-detail)
9. [Automatisierungen](#9-automatisierungen)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-faq)

> 📚 **Weitere Dokumentation:**
> - [Installation](INSTALLATION.md) - Detaillierte Installationsanleitung
> - [Konfiguration](CONFIGURATION.md) - Alle Optionen erklärt
> - [Gesichtserkennung](FACE_RECOGNITION.md) - Training & Matching
> - [Troubleshooting](TROUBLESHOOTING.md) - Problemlösung

---

## 1. Einführung

RTSP Recorder ist eine umfassende Videoüberwachungslösung für Home Assistant mit KI-gestützter Objekterkennung und Gesichtserkennung.

### Was ist neu in v1.1.0?

| Feature | Beschreibung |
|---------|--------------|
| ⚡ **Parallele Snapshots** | Thumbnails während der Aufnahme |
| 📊 **TPU-Load Anzeige** | Echtzeit Coral-Auslastung |
| 🔒 **Rate Limiter** | DoS-Schutz für API |
| 🌐 **5 Sprachen** | DE, EN, ES, FR, NL |
| 🧪 **Unit Tests** | pytest Framework |

### Hauptfunktionen

| Funktion | Beschreibung |
|----------|--------------|
| **Bewegungsgesteuerte Aufnahme** | Automatische Aufzeichnung bei Bewegungserkennung |
| **KI-Objekterkennung** | Erkennung von Personen, Autos, Tieren etc. |
| **Gesichtserkennung** | Training und Wiedererkennung bekannter Personen |
| **Coral USB Support** | Hardware-beschleunigte Inferenz (~50ms statt ~600ms) |
| **Timeline-Ansicht** | Visuelle Übersicht aller Aufnahmen |
| **Retention Management** | Automatische Bereinigung alter Aufnahmen |

### Systemanforderungen

- Home Assistant 2024.1 oder neuer
- Python 3.11+
- Optional: Google Coral USB Accelerator
- Speicherplatz für Aufnahmen (empfohlen: min. 50 GB)

---

## 2. Installation

### 2.1 Installation via HACS (Empfohlen)

1. **HACS öffnen** in Home Assistant
2. Klicke auf **⋮** (Drei-Punkte-Menü) → **Custom repositories**
3. Repository-URL eingeben:
   ```
   https://github.com/brainAThome/RTSP-Recorder
   ```
4. Kategorie: **Integration**
5. Klicke **Add**
6. Suche nach "RTSP Recorder" und klicke **Download**
7. **Home Assistant neustarten**

### 2.2 Manuelle Installation

1. **Integration kopieren:**
   ```
   custom_components/rtsp_recorder/ → /config/custom_components/rtsp_recorder/
   ```

2. **Dashboard Card kopieren:**
   ```
   www/rtsp-recorder-card.js → /config/www/rtsp-recorder-card.js
   ```

3. **Lovelace Resource hinzufügen:**
   
   Einstellungen → Dashboards → Ressourcen → Ressource hinzufügen:
   ```yaml
   URL: /local/rtsp-recorder-card.js
   Typ: JavaScript-Modul
   ```

4. **Home Assistant neustarten**

### 2.3 Detector Add-on (Optional, für Coral USB)

Das Detector Add-on ermöglicht Hardware-beschleunigte KI-Analyse.

1. Kopiere `addons/rtsp-recorder-detector/` nach `/addons/`
2. Einstellungen → Add-ons → Add-on Store
3. Klicke **⋮** → **Repositories** (wird automatisch erkannt)
4. Installiere "RTSP Recorder Detector"
5. Konfiguriere USB-Passthrough für Coral
6. Starte das Add-on

---

## 3. Erste Schritte

### 3.1 Integration hinzufügen

1. Gehe zu **Einstellungen** → **Geräte & Dienste**
2. Klicke **+ Integration hinzufügen**
3. Suche nach **"RTSP Recorder"**
4. Folge dem Konfigurationsassistenten

### 3.2 Erste Kamera konfigurieren

Im Konfigurationsassistenten:

| Feld | Beschreibung | Beispiel |
|------|--------------|----------|
| **Name** | Anzeigename der Kamera | `Wohnzimmer` |
| **Kamera-Entity** | Home Assistant Kamera-Entity | `camera.wohnzimmer` |
| **RTSP URL** | Direkter RTSP-Stream (optional) | `rtsp://192.168.1.100/stream` |
| **Bewegungssensor** | Entity für Bewegungserkennung | `binary_sensor.wohnzimmer_motion` |

### 3.3 Dashboard Card hinzufügen

1. Dashboard bearbeiten → **+ Karte hinzufügen**
2. Wähle **Manuell** (YAML)
3. Füge ein:

```yaml
type: custom:rtsp-recorder-card
base_path: /media/rtsp_recordings
thumb_path: /local/thumbnails
```

---

## 4. Dashboard Card

Die Dashboard Card ist das Herzstück der Benutzeroberfläche.

### 4.1 Übersicht

Die Card zeigt:
- **Video-Player** mit aktueller/ausgewählter Aufnahme
- **Timeline** mit Thumbnails aller Aufnahmen
- **Kamera-Auswahl** (Dropdown)
- **Einstellungen-Button** (Zahnrad-Icon)
- **Performance-Footer** (optional)

### 4.2 Navigation

| Element | Funktion |
|---------|----------|
| **Timeline-Thumbnails** | Klicken zum Abspielen |
| **Pfeile links/rechts** | Durch Aufnahmen blättern |
| **Kamera-Dropdown** | Zwischen Kameras wechseln |
| **Datum-Filter** | Aufnahmen nach Datum filtern |
| **⚙️ Zahnrad** | Einstellungen öffnen |

### 4.3 Video-Steuerung

- **Play/Pause:** Klick auf Video oder Spacebar
- **Vor/Zurück:** Pfeiltasten oder Timeline
- **Vollbild:** Doppelklick auf Video
- **Download:** Rechtsklick → Speichern

---

## 5. Aufnahmen & Timeline

### 5.1 Automatische Aufnahme

Aufnahmen werden automatisch erstellt, wenn:
1. Der konfigurierte Bewegungssensor auf **ON** wechselt
2. Die Kamera verfügbar ist
3. Keine Aufnahme bereits läuft

**Aufnahme-Parameter:**

| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| Aufnahmedauer | 30 Sekunden | Nach Bewegungsende |
| Snapshot-Verzögerung | 2 Sekunden | Für Thumbnail |
| Format | MP4 (H.264) | Kompatibel mit allen Browsern |

### 5.2 Manuelle Aufnahme

**Via Service-Call:**
```yaml
service: rtsp_recorder.save_recording
data:
  camera_name: wohnzimmer
  duration: 60  # Optional, in Sekunden
```

### 5.3 Aufnahmen löschen

**Einzelne Aufnahme:**
- Rechtsklick auf Thumbnail → Löschen
- Oder via Service-Call

**Mehrere Aufnahmen:**
```yaml
service: rtsp_recorder.delete_all_recordings
data:
  camera_name: wohnzimmer  # Optional
  older_than_days: 7       # Optional
```

### 5.4 Retention (Speicherverwaltung)

Die Retention-Einstellungen steuern, wie lange Aufnahmen aufbewahrt werden.

**Globale Einstellungen:**
- Aufnahmen: X Tage
- Snapshots: X Tage
- Analyse-Daten: X Tage

**Pro-Kamera-Override:**
Jede Kamera kann eigene Retention-Werte haben, die die globalen überschreiben.

---

## 6. KI-Analyse

### 6.1 Funktionsweise

Die KI-Analyse erkennt Objekte in Aufnahmen:

```
Video → Frames extrahieren → Objekterkennung → Ergebnisse speichern
```

**Erkennbare Objekte:**
- Person, Fahrrad, Auto, Motorrad, Bus, LKW
- Hund, Katze, Vogel, Pferd
- Und 70+ weitere COCO-Klassen

### 6.2 Analyse-Modi

| Modus | Beschreibung |
|-------|--------------|
| **Manuell** | Einzelne Aufnahme analysieren |
| **Auto-Analyse** | Neue Aufnahmen automatisch analysieren |
| **Batch-Analyse** | Alle/gefilterte Aufnahmen analysieren |
| **Zeitplan** | Tägliche automatische Analyse |

### 6.3 Auto-Analyse aktivieren

1. Öffne **Einstellungen** → **Analyse**
2. Aktiviere **"Neue Aufnahmen automatisch analysieren"**
3. Optional: **"Coral für Auto-Analyse erzwingen"**

### 6.4 Batch-Analyse

Für nachträgliche Analyse aller Aufnahmen:

1. Einstellungen → Analyse
2. Klicke **"Alle analysieren"**
3. Optional: Filter setzen (Kamera, Zeitraum)
4. **"Bereits analysierte überspringen"** für Effizienz

### 6.5 Analyse-Zeitplan

Automatische Analyse zu bestimmten Zeiten:

| Option | Beschreibung |
|--------|--------------|
| **Täglich um** | Feste Uhrzeit (z.B. 03:00) |
| **Alle X Stunden** | Intervall-basiert |

### 6.6 Erkennungsschwellwerte

Pro Kamera konfigurierbar:

| Schwellwert | Beschreibung | Empfohlen |
|-------------|--------------|-----------|
| **Detektor** | Mindest-Konfidenz für Objekterkennung | 0.5 - 0.7 |
| **Gesicht** | Mindest-Konfidenz für Gesichtserkennung | 0.6 - 0.8 |
| **Match** | Mindest-Ähnlichkeit für Personen-Match | 0.6 - 0.75 |

### 6.7 Objekt-Filter

Wähle, welche Objekte pro Kamera erkannt werden sollen:

```
☑ Person  ☑ Auto  ☐ Hund  ☐ Katze  ☐ Fahrrad
```

Nicht aktivierte Objekte werden ignoriert (spart Ressourcen).

---

## 7. Personen-Erkennung

Die Gesichtserkennung ermöglicht die Identifikation bekannter Personen.

### 7.1 Konzept

```
Gesicht erkannt → Embedding erstellen → Mit Datenbank vergleichen → Person identifizieren
```

**Begriffe:**
- **Embedding:** 1280-dimensionaler Vektor eines Gesichts
- **Positive Samples:** Bilder, die ZU einer Person gehören
- **Negative Samples:** Bilder, die NICHT zu einer Person gehören

### 7.2 Person anlegen

1. Öffne **Einstellungen** → **Personen**
2. Klicke **"+ Person hinzufügen"**
3. Gib einen Namen ein (z.B. "Max")
4. Bestätige mit **OK**

### 7.3 Training aus Analyse

Das Training erfolgt über erkannte Gesichter aus Analysen:

1. Wähle eine **analysierte Aufnahme** im Dropdown
2. Klicke **"Analyse laden"**
3. Erkannte Gesichter werden angezeigt

**Gesicht zuweisen:**
- Wähle eine Person im Dropdown
- Klicke auf ein **nicht zugewiesenes Bild** → wird direkt hinzugefügt
- Das Bild wird **grün markiert** (✓)

**Korrigieren:**
- Klicke auf ein **bereits zugewiesenes (grünes) Bild**
- Ein **Korrektur-Popup** erscheint
- Wähle die richtige Person oder "Überspringen"

### 7.4 Negative Samples

Negative Samples verhindern falsche Zuordnungen.

**Wann verwenden?**
- Wenn Person A fälschlicherweise als Person B erkannt wird
- Bei ähnlich aussehenden Personen

**So geht's:**
1. Klicke auf ein Bild → Popup erscheint
2. Klicke auf **❌** neben der falschen Person
3. Das Bild wird als "Nicht diese Person" markiert

**Schwellwert:** 75% - Wenn ein Gesicht >75% Ähnlichkeit mit einem Negativ-Sample hat, wird es ausgeschlossen.

### 7.5 Empfehlungen für gutes Training

| Empfehlung | Grund |
|------------|-------|
| **3-5 Positive Samples** pro Person | Verschiedene Winkel/Lichtverhältnisse |
| **Klare Frontalaufnahmen** bevorzugen | Bessere Embedding-Qualität |
| **Negative Samples** bei Verwechslungen | Verhindert False Positives |
| **Regelmäßig nachtrainieren** | Verbessert Genauigkeit über Zeit |

### 7.6 Person Detail Popup (NEU in v1.1.0n)

Klicke auf den **Namen einer Person** im People-Tab, um das Detail-Popup zu öffnen.

**Was zeigt das Popup?**
- **Positive Samples:** Alle zugewiesenen Gesichtsbilder mit Datum
- **Negative Samples:** Alle Ausschluss-Bilder
- **Erkennungen:** Wie oft wurde diese Person insgesamt erkannt
- **Zuletzt gesehen:** Datum, Uhrzeit und Kamera der letzten Erkennung

**Samples verwalten:**
- Klicke auf das rote **✕** um einzelne Samples zu löschen
- Ideal für die Qualitätskontrolle deiner Trainingsdaten

### 7.7 Person-Entities für Automationen (NEU in v1.1.0n)

Erstelle Home Assistant Entities für erkannte Personen:

1. Gehe zu **Einstellungen** → **RTSP Recorder** → **Konfigurieren**
2. Aktiviere **Person-Entities erstellen**

**Erstellte Entities:**
```yaml
binary_sensor.rtsp_person_max:
  state: "on"  # Wenn kürzlich erkannt
  attributes:
    last_seen: "2026-02-03T14:30:00"
    last_camera: "Wohnzimmer"
    confidence: 0.87
```

**Beispiel-Automation:**
```yaml
automation:
  - alias: "Max erkannt"
    trigger:
      - platform: state
        entity_id: binary_sensor.rtsp_person_max
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Max wurde bei {{ trigger.to_state.attributes.last_camera }} gesehen"
```

> 📚 **Mehr Details:** Siehe [Gesichtserkennung](FACE_RECOGNITION.md#8-person-entities-für-automationen)

### 7.8 Person umbenennen/löschen

- **Umbenennen:** Klicke auf ✏️ neben dem Namen
- **Löschen:** Klicke auf 🗑️ → Bestätigen

⚠️ **Achtung:** Beim Löschen werden alle Embeddings unwiderruflich entfernt!

---

## 8. Einstellungen im Detail

Die Einstellungen sind in 5 Tabs organisiert:

### 8.1 Tab: Allgemein

| Einstellung | Beschreibung |
|-------------|--------------|
| **Aufnahmedauer** | Sekunden nach Bewegungsende (Standard: 30) |
| **Snapshot-Verzögerung** | Sekunden bis Thumbnail (Standard: 2) |
| **Footer anzeigen** | Performance-Anzeige unter Video |

### 8.2 Tab: Speicher

| Einstellung | Beschreibung |
|-------------|--------------|
| **Aufnahmen aufbewahren** | Tage bis zur automatischen Löschung |
| **Snapshots aufbewahren** | Tage für Thumbnail-Aufbewahrung |
| **Analyse-Daten aufbewahren** | Tage für JSON-Ergebnisse |
| **Pro-Kamera-Einstellungen** | Override für einzelne Kameras |

**Speicherplatz-Anzeige:**
- Gesamtgröße aller Aufnahmen
- Anzahl der Dateien
- Aufschlüsselung nach Kamera

### 8.3 Tab: Analyse

| Einstellung | Beschreibung |
|-------------|--------------|
| **Detektor-URL** | Adresse des Detector Add-ons |
| **Auto-Analyse** | Neue Aufnahmen automatisch analysieren |
| **Coral erzwingen** | Coral USB für Auto-Analyse verwenden |
| **Zeitplan** | Automatische Batch-Analyse |
| **SQLite nutzen** | Datenbank statt JSON für Personen |

**Aktionen:**
- **Test-Inferenz:** Prüft Verbindung zum Detektor
- **Alle analysieren:** Startet Batch-Analyse

### 8.4 Tab: Personen

| Bereich | Beschreibung |
|---------|--------------|
| **Personen-Liste** | Alle angelegten Personen mit Embeddings |
| **Training aus Analyse** | Gesichter aus Aufnahmen zuweisen |
| **Erkannte Gesichter** | Bilder zum Zuweisen/Korrigieren |

**Pro Person:**
- Name + Embedding-Anzahl
- Vorschaubilder (Thumbnails)
- Bearbeiten/Löschen-Buttons

### 8.5 Tab: Leistung

Live-Statistiken des Detector Add-ons:

| Metrik | Beschreibung |
|--------|--------------|
| **CPU** | Aktuelle CPU-Auslastung |
| **RAM** | Speicherverbrauch |
| **Coral Status** | Verbunden/Nicht verbunden |
| **Inferenzen** | Anzahl durchgeführter Analysen |
| **Ø Inferenzzeit** | Durchschnittliche Analysezeit (ms) |
| **Coral-Anteil** | Prozent der Coral-Analysen |

**Test-Button:** Führt eine Test-Inferenz durch und zeigt Zeit.

---

## 9. Automatisierungen

### 9.1 Person erkannt - Benachrichtigung

```yaml
automation:
  - alias: "Person erkannt - Push-Nachricht"
    trigger:
      - platform: event
        event_type: rtsp_recorder_person_detected
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.person_name != 'Unbekannt' }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Person erkannt"
          message: "{{ trigger.event.data.person_name }} wurde von {{ trigger.event.data.camera }} erkannt"
          data:
            image: "{{ trigger.event.data.thumbnail }}"
```

### 9.2 Unbekannte Person - Alarm

```yaml
automation:
  - alias: "Unbekannte Person - Alarm"
    trigger:
      - platform: event
        event_type: rtsp_recorder_person_detected
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.person_name == 'Unbekannt' }}"
      - condition: state
        entity_id: alarm_control_panel.home
        state: "armed_away"
    action:
      - service: notify.all
        data:
          title: "⚠️ Unbekannte Person!"
          message: "Unbekannte Person bei {{ trigger.event.data.camera }}"
```

### 9.3 Tägliche Analyse nachts

```yaml
automation:
  - alias: "Nachtliche Batch-Analyse"
    trigger:
      - platform: time
        at: "03:00:00"
    action:
      - service: rtsp_recorder.analyze_all_recordings
        data:
          skip_analyzed: true
          use_coral: true
```

### 9.4 Aufnahme bei Abwesenheit

```yaml
automation:
  - alias: "Aufnahme wenn niemand zuhause"
    trigger:
      - platform: state
        entity_id: binary_sensor.eingang_motion
        to: "on"
    condition:
      - condition: state
        entity_id: group.family
        state: "not_home"
    action:
      - service: rtsp_recorder.save_recording
        data:
          camera_name: eingang
          duration: 60
```

### 9.5 Verfügbare Events

| Event | Beschreibung | Daten |
|-------|--------------|-------|
| `rtsp_recorder_recording_saved` | Aufnahme gespeichert | camera, filename, duration |
| `rtsp_recorder_analysis_complete` | Analyse abgeschlossen | camera, filename, detections |
| `rtsp_recorder_person_detected` | Person erkannt | camera, person_name, confidence, thumbnail |

### 9.6 Verfügbare Services

| Service | Beschreibung |
|---------|--------------|
| `rtsp_recorder.save_recording` | Manuelle Aufnahme starten |
| `rtsp_recorder.delete_recording` | Einzelne Aufnahme löschen |
| `rtsp_recorder.delete_all_recordings` | Bulk-Löschung |
| `rtsp_recorder.analyze_recording` | Einzelne Analyse |
| `rtsp_recorder.analyze_all_recordings` | Batch-Analyse |

---

## 10. Troubleshooting

### 10.1 Aufnahmen starten nicht

**Mögliche Ursachen:**

| Problem | Lösung |
|---------|--------|
| Bewegungssensor falsch | Entity-ID in Kamera-Einstellungen prüfen |
| Kamera nicht erreichbar | RTSP-URL testen, Netzwerk prüfen |
| Speicherplatz voll | Alte Aufnahmen löschen, Retention anpassen |
| FFmpeg-Fehler | Logs prüfen, FFmpeg neu installieren |

**Diagnose:**
```bash
# In HA Terminal:
tail -f /config/home-assistant.log | grep rtsp_recorder
```

### 10.2 Coral USB nicht erkannt

1. **USB-Passthrough prüfen:**
   ```bash
   lsusb | grep -i coral
   # Sollte "Global Unichip Corp" zeigen
   ```

2. **Add-on-Konfiguration:**
   - Einstellungen → Add-ons → Detector → Konfiguration
   - USB-Gerät hinzufügen

3. **Reset versuchen:**
   - Detector Add-on neustarten
   - Oder: `/tpu_reset` Endpoint aufrufen

### 10.3 Gesichtserkennung ungenau

| Symptom | Lösung |
|---------|--------|
| Falsche Zuordnungen | Mehr Training-Samples hinzufügen |
| Person nicht erkannt | Bessere Bilder (frontal, gut beleuchtet) |
| Verwechslungen | Negative Samples für verwechselte Person |
| Zu viele Unbekannte | Match-Schwellwert senken (z.B. 0.55) |

### 10.4 Analyse sehr langsam

| Ursache | Lösung |
|---------|--------|
| CPU-Fallback aktiv | Coral USB installieren/prüfen |
| Zu viele Frames | Frame-Intervall erhöhen |
| Große Videos | Kürzere Aufnahmedauer |
| Server ausgelastet | Analyse nachts planen |

### 10.5 Dashboard Card lädt nicht

1. **Browser-Cache leeren:** Ctrl+F5
2. **Resource prüfen:**
   ```yaml
   # In Lovelace YAML:
   resources:
     - url: /local/rtsp-recorder-card.js?v=1.0.9
       type: module
   ```
3. **Datei vorhanden?** `/config/www/rtsp-recorder-card.js`
4. **Konsole prüfen:** F12 → Console → Fehler suchen

---

## 11. FAQ

### Allgemein

**Q: Wie viel Speicherplatz brauche ich?**
> A: Ca. 1-5 MB pro Minute Aufnahme (abhängig von Qualität). Bei 10 Kameras mit je 10 Aufnahmen/Tag à 30 Sek ≈ 1-3 GB/Tag.

**Q: Funktioniert es ohne Coral USB?**
> A: Ja, aber Analysen dauern 10-15x länger (CPU-Fallback).

**Q: Kann ich mehrere Coral USB verwenden?**
> A: Aktuell wird nur ein Coral unterstützt.

### Aufnahmen

**Q: Warum sind manche Aufnahmen sehr kurz?**
> A: Die Aufnahme endet X Sekunden nach der letzten Bewegung. Kurze Bewegung = kurze Aufnahme.

**Q: Kann ich die Aufnahmequalität ändern?**
> A: Die Qualität wird von der Kamera/RTSP-Stream bestimmt, nicht von RTSP Recorder.

**Q: Werden Aufnahmen verschlüsselt?**
> A: Nein, Aufnahmen werden als normale MP4-Dateien gespeichert.

### KI-Analyse

**Q: Welche Objekte werden erkannt?**
> A: Alle 80 COCO-Klassen (Person, Auto, Hund, Katze, etc.). Vollständige Liste: https://cocodataset.org

**Q: Wie genau ist die Gesichtserkennung?**
> A: Bei guten Trainingsdaten ~85-95% Genauigkeit. Hängt stark von Bildqualität und Beleuchtung ab.

**Q: Werden Daten in die Cloud gesendet?**
> A: Nein, alle Analysen laufen lokal auf deinem Server.

### Personen

**Q: Wie viele Personen kann ich trainieren?**
> A: Technisch unbegrenzt. Empfohlen: max. 50 für beste Performance.

**Q: Kann ich Embeddings exportieren/importieren?**
> A: Die Daten liegen in `/config/rtsp_recorder.db` (SQLite) oder `rtsp_recorder_people.json`.

**Q: Was passiert bei ähnlichen Zwillingen?**
> A: Negative Samples verwenden, um Verwechslungen zu minimieren.

---

## Anhang

### A. Dateipfade

| Pfad | Beschreibung |
|------|--------------|
| `/config/custom_components/rtsp_recorder/` | Integration |
| `/config/www/rtsp-recorder-card.js` | Dashboard Card |
| `/media/rtsp_recordings/` | Aufnahmen |
| `/config/www/thumbnails/` | Thumbnails |
| `/media/rtsp_analysis/` | Analyse-Ergebnisse |
| `/config/rtsp_recorder.db` | SQLite-Datenbank |
| `/config/rtsp_recorder_people.json` | Personen (JSON-Modus) |

### B. API-Referenz

**Detector Add-on Endpoints:**

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/health` | GET | Health-Check |
| `/info` | GET | Geräte-Info |
| `/metrics` | GET | Performance-Metriken |
| `/detect` | POST | Objekterkennung |
| `/faces` | POST | Gesichtserkennung |
| `/embed_face` | POST | Embedding extrahieren |

### C. Verwendete KI-Modelle

| Modell | Aufgabe | Input | Hardware |
|--------|---------|-------|----------|
| MobileDet SSD | Objekterkennung | 320x320 | Coral/CPU |
| MobileNet V2 | Gesichtserkennung | 320x320 | Coral/CPU |
| EfficientNet-S | Face Embedding | 224x224 | Coral/CPU |
| MoveNet Lightning | Pose Estimation | 192x192 | CPU |

---

*RTSP Recorder v1.0.9 STABLE - © 2026 brainAThome*
