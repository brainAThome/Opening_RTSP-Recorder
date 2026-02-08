# 🔧 RTSP Recorder - Troubleshooting

> 🇬🇧 **[English Version](TROUBLESHOOTING.md)**

**Version:** 1.2.2  
**Letzte Aktualisierung:** 07. Februar 2026

---

## Inhaltsverzeichnis

1. [Schnelldiagnose](#1-schnelldiagnose)
2. [Installation & Setup](#2-installation--setup)
3. [Aufnahmen](#3-aufnahmen)
4. [Analyse & Detection](#4-analyse--detection)
5. [Coral USB / TPU](#5-coral-usb--tpu)
6. [Gesichtserkennung](#6-gesichtserkennung)
7. [Dashboard Card](#7-dashboard-card)
8. [Performance](#8-performance)
9. [Log-Analyse](#9-log-analyse)
10. [Häufige Fehlermeldungen](#10-häufige-fehlermeldungen)

---

## 1. Schnelldiagnose

### System-Check Befehle

```bash
# Integration geladen?
grep -i "rtsp_recorder" /config/home-assistant.log | tail -10

# Detector erreichbar?
curl http://localhost:5000/info

# Aufnahmen vorhanden?
ls -la /media/rtsp_recorder/ring_recordings/*/

# Coral erkannt?
curl http://localhost:5000/info | grep coral
```

### Status-Checkliste

| Check | Befehl | Erwartung |
|-------|--------|-----------|
| HA läuft | `ha core check` | "Command completed" |
| Integration | `grep rtsp_recorder /config/.storage/core.config_entries` | Eintrag vorhanden |
| Detector | `curl localhost:5000/info` | JSON Response |
| Coral | Detector /info | `"coral_available": true` |
| Speicher | `df -h /media` | >10% frei |

---

## 2. Installation & Setup

### Problem: Integration nicht gefunden

**Symptom:** "rtsp_recorder" erscheint nicht in Integrationen

**Ursachen & Lösungen:**

1. **Dateien fehlen**
   ```bash
   ls /config/custom_components/rtsp_recorder/
   # Muss enthalten: __init__.py, manifest.json, etc.
   ```

2. **Manifest ungültig**
   ```bash
   python3 -c "import json; json.load(open('/config/custom_components/rtsp_recorder/manifest.json'))"
   ```

3. **Cache-Problem**
   - HA komplett neustarten (nicht nur reload)
   - Browser-Cache leeren (Ctrl+Shift+R)

### Problem: Integration lädt nicht

**Symptom:** Fehler beim Setup

**Log prüfen:**
```bash
grep -i "error.*rtsp" /config/home-assistant.log | tail -20
```

**Häufige Ursachen:**

| Fehler | Lösung |
|--------|--------|
| ImportError | Python-Abhängigkeiten prüfen |
| FileNotFoundError | Pfade prüfen |
| PermissionError | Rechte prüfen: `chmod -R 755 /config/custom_components/rtsp_recorder` |

---

## 3. Aufnahmen

### Problem: Keine Aufnahmen bei Bewegung

**Diagnose:**

1. **Motion Sensor prüfen**
   ```yaml
   # In Entwicklerwerkzeuge → Status
   # Prüfe: binary_sensor.xxx_motion wechselt zu "on"?
   ```

2. **Event-Trigger prüfen**
   ```bash
   grep -i "motion.*trigger\|recording.*start" /config/home-assistant.log | tail -10
   ```

3. **Kamera-Konfiguration**
   - Ist die Kamera in den Optionen konfiguriert?
   - Ist der richtige Motion-Sensor zugewiesen?

**Lösungen:**

| Problem | Lösung |
|---------|--------|
| Sensor falsch | Korrekten binary_sensor zuweisen |
| Kein RTSP | RTSP-URL prüfen |
| FFmpeg-Fehler | Log prüfen, Codec-Probleme |

### Problem: Aufnahme bricht ab

**Symptom:** Aufnahmen sind zu kurz oder unvollständig

**Ursachen:**

1. **RTSP-Stream instabil**
   ```bash
   # Test mit ffprobe
   ffprobe rtsp://user:pass@ip/stream
   ```

2. **Timeout zu kurz**
   - Netzwerk-Latenz prüfen
   - FFmpeg TCP-Modus bereits aktiv (Standard)

3. **Speicher voll**
   ```bash
   df -h /media
   ```

### Problem: Keine Thumbnails

**Diagnose:**
```bash
ls /media/rtsp_recorder/thumbnails/*/
```

**Lösungen:**

| Ursache | Lösung |
|---------|--------|
| Pfad falsch | snapshot_path prüfen |
| Keine Rechte | `chmod 755 /media/rtsp_recorder/thumbnails` |
| FFmpeg-Fehler | Codec-Kompatibilität prüfen |

---

## 4. Analyse & Detection

### Problem: Analyse startet nicht

**Diagnose:**
```bash
# Detector erreichbar?
curl -X POST http://localhost:5000/detect \
  -F "image=@test.jpg" 2>&1 | head -5
```

**Lösungen:**

| Problem | Lösung |
|---------|--------|
| Detector offline | Add-on starten |
| URL falsch | `analysis_detector_url` prüfen |
| Port blockiert | Firewall/Docker-Netzwerk prüfen |

### Problem: Keine Objekte erkannt

**Ursachen:**

1. **Confidence zu hoch**
   ```yaml
   # Senken auf 0.3 oder 0.4
   analysis_detector_confidence: 0.4
   ```

2. **Objekt nicht in Liste**
   ```yaml
   analysis_objects:
     - person
     - car
     - dog  # Hinzufügen was fehlt
   ```

3. **Videoqualität zu niedrig**
   - Mindestens 720p
   - Ausreichende Beleuchtung

### Problem: Analyse langsam

**CPU-Modus:**
- Normal: ~500ms/Frame
- Mit Coral: ~50ms/Frame

**Lösung:** Coral USB einrichten

```yaml
analysis_device: coral_usb
```

---

## 5. Coral USB / TPU

### Problem: Coral nicht erkannt

**Diagnose:**
```bash
# USB-Geräte prüfen
lsusb | grep -i google

# Detector-Log
docker logs addon_local_rtsp_recorder_detector | grep -i coral
```

**Lösungen:**

| Problem | Lösung |
|---------|--------|
| USB nicht sichtbar | Physisch prüfen, anderer Port |
| Kein Passthrough | Add-on Konfiguration: `devices: ["/dev/bus/usb"]` |
| Permission denied | udev-Regeln prüfen |

### Problem: Coral-Fehler "Delegate error"

**Ursache:** libedgetpu-Version inkompatibel

**Lösung:**
```bash
# Im Add-on Container
pip install --upgrade pycoral
```

### Problem: TPU-Load immer 0%

**Ursache:** Keine Inferenzen auf Coral

**Prüfen:**
```bash
curl http://localhost:5000/info
# "device": "coral_usb" sollte angezeigt werden
```

---

## 6. Gesichtserkennung

### Problem: Keine Gesichter erkannt

**Diagnose:**
1. Face Detection aktiviert?
   ```yaml
   analysis_face_enabled: true
   ```

2. Confidence zu hoch?
   ```yaml
   analysis_face_confidence: 0.2  # Senken
   ```

3. Gesicht zu klein im Bild?
   - Mindestens 50x50 Pixel

### Problem: Falsche Person erkannt

**Lösungen:**

1. **Match Threshold senken**
   ```yaml
   analysis_face_match_threshold: 0.30  # statt 0.35
   ```

2. **Negative Samples hinzufügen**
   - Falsche Matches als negativ markieren

3. **Mehr Training-Samples**
   - 5-10 verschiedene Samples pro Person

### Problem: Person wird nicht mehr erkannt

**Ursache:** Aussehen verändert

**Lösung:** Neue Samples mit aktuellem Aussehen hinzufügen

---

## 7. Dashboard Card

### Problem: Card nicht sichtbar

**Diagnose:**

1. **Resource registriert?**
   - Einstellungen → Dashboards → Ressourcen
   - URL: `/local/rtsp-recorder-card.js`

2. **Datei vorhanden?**
   ```bash
   ls -la /config/www/rtsp-recorder-card.js
   ```

3. **Browser-Cache**
   - Ctrl+Shift+R (Hard Refresh)
   - Inkognito-Modus testen

### Problem: Card zeigt Fehler

**"Custom element doesn't exist":**
```yaml
# Ressource neu hinzufügen
type: module
url: /local/rtsp-recorder-card.js?v=1.1.0  # Version-Parameter
```

### Problem: Videos laden nicht

**Ursachen:**

| Problem | Lösung |
|---------|--------|
| Pfad falsch | storage_path prüfen |
| Keine Rechte | `chmod -R 755 /media/rtsp_recorder` |
| CORS-Fehler | HA Proxy-Einstellungen |

---

## 8. Performance

### Problem: HA wird langsam

**Diagnose:**
```bash
# CPU-Last
top -bn1 | head -20

# Memory
free -h

# Disk I/O
iostat -x 1 5
```

**Lösungen:**

| Ursache | Lösung |
|---------|--------|
| Zu viele Aufnahmen | Retention reduzieren |
| Analyse zu häufig | frame_interval erhöhen |
| SQLite nicht aktiv | `use_sqlite: true` |

### Problem: Speicher voll

**Diagnose:**
```bash
du -sh /media/rtsp_recorder/*
```

**Lösungen:**
1. Retention reduzieren
2. Alte Aufnahmen manuell löschen
3. Speicher erweitern

### Blocking Call Warnings

**Symptom:**
```
Detected blocking call to open... inside the event loop
```

**Erklärung:** Diese Warnungen sind bekannt und unkritisch. Sie betreffen Datei-I/O-Operationen, die synchron ausgeführt werden.

**Status:** Low Priority - Funktionalität nicht beeinträchtigt

---

## 9. Log-Analyse

### Wichtige Log-Zeilen

```bash
# Erfolgreiche Aufnahme
grep "Recording saved" /config/home-assistant.log

# Analyse-Ergebnisse
grep "Analysis complete\|detected" /config/home-assistant.log

# Fehler
grep -i "error.*rtsp" /config/home-assistant.log

# Metriken
grep "METRIC" /config/home-assistant.log
```

### Debug-Modus aktivieren

```yaml
# In configuration.yaml
logger:
  default: info
  logs:
    custom_components.rtsp_recorder: debug
    custom_components.rtsp_recorder.analysis: debug
    custom_components.rtsp_recorder.recorder: debug
```

### Log-Rotation

```bash
# Alte Logs bereinigen
truncate -s 0 /config/home-assistant.log
```

---

## 10. Häufige Fehlermeldungen

### "Connection refused to detector"

```
Error connecting to http://local-rtsp-recorder-detector:5000
```

**Lösung:**
1. Add-on starten
2. URL prüfen (lokal vs. Docker-Netzwerk)

### "FFmpeg process failed"

```
FFmpeg exited with code 1
```

**Lösungen:**
1. RTSP-URL prüfen
2. Netzwerk-Konnektivität testen
3. Kamera-Credentials prüfen

### "Permission denied: /media/..."

```
PermissionError: [Errno 13] Permission denied
```

**Lösung:**
```bash
chmod -R 755 /media/rtsp_recorder
chown -R root:root /media/rtsp_recorder
```

### "Database is locked"

```
sqlite3.OperationalError: database is locked
```

**Lösung:**
1. HA neustarten
2. WAL-Modus prüfen (Standard)

### "No module named 'xxx'"

```
ModuleNotFoundError: No module named 'cv2'
```

**Lösung:** Abhängigkeiten sind im Add-on enthalten, nicht in HA direkt.

---

## Support

### Informationen sammeln

Vor dem Erstellen eines Issues:

```bash
# System-Info
cat /config/custom_components/rtsp_recorder/manifest.json | grep version

# Letzte Fehler
grep -i error /config/home-assistant.log | tail -50 > error_log.txt

# Konfiguration (ohne Passwörter!)
cat /config/.storage/core.config_entries | grep -A 100 rtsp_recorder
```

### Issue erstellen

[GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)

Bitte inkludieren:
1. RTSP Recorder Version
2. Home Assistant Version
3. Fehlermeldung (vollständig)
4. Schritte zur Reproduktion
5. Relevante Logs

---

## Siehe auch

- 📖 [Benutzerhandbuch](USER_GUIDE.md)
- ⚙️ [Konfiguration](CONFIGURATION.md)
- 🚀 [Installation](INSTALLATION.md)

---

*Bei Problemen: [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)*
