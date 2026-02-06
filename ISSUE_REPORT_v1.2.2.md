# ISSUE REPORT v1.2.2

**Datum:** 07. Februar 2026  
**Version:** v1.2.2 BETA  
**Status:** ✅ Alle Features implementiert und getestet

---

## Session-Zusammenfassung (06.-07.02.2026)

Diese Session hat 4 Features implementiert und mehrere Bugs behoben:

| Issue | Status | Beschreibung |
|-------|--------|--------------|
| Stats Reset | ✅ DONE | Button zum Zurücksetzen der Detector-Statistiken |
| Recording Indicator | ✅ FIXED | "Aufnahme läuft" verschwand bei Multi-Kamera Events |
| FPS Display | ✅ FIXED | Video-FPS aus Analyse-Daten anzeigen |
| smooth_video | ✅ REMOVED | Ungenutzte Option aus Config entfernt |

---

## Behobene Issues

### 1. Statistik Reset Feature ✅
**Session:** 06.-07.02.2026

**Anforderung:** User wünscht "Statistik zurücksetzen" Button im Leistungs-Tab.

**Implementiert:**

1. **WebSocket Handler** (`websocket_handlers.py`):
   - Neuer Handler: `rtsp_recorder/reset_detector_stats`
   - Funktion: `ws_reset_detector_stats()`
   - Ruft: `POST {detector_url}/stats/reset`

2. **Detector Endpoint** (`addons/rtsp-recorder-detector/app.py`):
   - Neuer Endpoint: `POST /stats/reset`
   - Funktion: `stats_reset()`
   - Setzt zurück: `total_inferences`, `tpu_inferences`, `cpu_inferences`
   - Setzt: `_startup_time` für Uptime-Reset

3. **Card Button** (`www/rtsp-recorder-card.js`):
   - Orangener Button "Statistik zurücksetzen" neben "Test-Inferenz starten"
   - JavaScript-Funktion: `resetDetectorStats()`

**Gelöstes Problem:**
- Ursprünglich "Reset endpoint not supported by detector" Fehler
- Ursache: Falscher Container-Name `addon_a861495c_rtsp_recorder_detector`
- Lösung: Korrekter Container-Name `addon_local_rtsp_recorder_detector`

**Test erfolgreich:**
```json
{"success":true,"message":"Statistics reset. Previous: 60 total (60 Coral, 0 CPU)","reset_at":"2026-02-06 22:41:03"}
```

---

### 2. Recording Indicator Bug ✅
**Session:** 06.-07.02.2026

**Problem:** "Aufnahme läuft" Anzeige verschwand sobald eine andere Kamera ein Video lieferte, obwohl noch Aufnahmen liefen.

**Symptom (User-Beschreibung):**
> "Aufnahme Anzeige läuft solange bis eine andere Kamera ein Video liefert, dann verschwindet die Aufnahmeanzeige. Aber wenn kurz danach wieder eine Aufnahme startet wird die Aufnahmeanzeige angezeigt mit der Kamera die noch am aufzeichnen ist und die neu die gerade aufzeichnet"

**Root Cause Analyse:**
Das Recording-Status-System verwendete zwei verschiedene Mechanismen:
1. **Event-driven** (`_runningRecordings` Map): Korrekt, wird durch Events aktualisiert
2. **Polling-based** (`_recordingProgress` Cache): Veraltet, überschrieb die korrekte Anzeige

Die Funktion `_restoreStatusIndicators()` und der Polling-Code riefen `_updateRecordingStatusOnly()` auf, das den alten Polling-Cache verwendete, statt `_updateRecordingUI()` das die Event-driven Map nutzt.

**Fix (3 Änderungen in `www/rtsp-recorder-card.js`):**

1. **Zeile ~196**: Nach Timeline-Refresh `_updateRecordingUI()` aufrufen
2. **Zeile ~541**: Polling-Code ruft jetzt `_updateRecordingUI()` statt `_updateRecordingStatusOnly()`
3. **Zeile ~5302**: `_restoreStatusIndicators()` ruft jetzt `_updateRecordingUI()` auf

**Verifiziert durch Debug-Logging:**
```
[RTSP-Recorder] ADD: .../Testcam_..., Running recordings after add: 1 [Testcam]
[RTSP-Recorder] ADD: .../Flur_oben_..., Running recordings after add: 2 [Testcam, Flur_oben]
[RTSP-Recorder] DELETE: .../Testcam_..., was in Map: true
[RTSP-Recorder] Running recordings after delete: 1 [Flur_oben] ✓
```

---

### 3. FPS Display Fix ✅
**Session:** 06.02.2026

**Problem:** Video-Player zeigte immer 25 FPS statt der tatsächlichen Video-FPS.

**Ursache:** Die `video_fps` wurde vom Detector zurückgegeben, aber nicht im Frontend verwendet.

**Fix:**
1. **Detector** (`app.py`): Liefert `video_fps` im Analysis-Response
2. **Frontend** (`rtsp-recorder-card.js`): Liest `data.video_fps` und speichert in `this._videoFps`
3. **Fallback**: 25 FPS (PAL-Standard) wenn keine Analyse-Daten

**Code:**
```javascript
// Line 4304: From analysis data
this._videoFps = data.video_fps || null;

// Line 4599: Use in player
let fps = this._videoFps || 25;
```

---

### 4. smooth_video Option entfernt ✅
**Session:** 06.02.2026

**Anforderung:** Ungenutzte `smooth_video` Option aus der Konfiguration entfernen.

**Betroffene Dateien:**
- `config_flow.py`: Option aus Flow entfernt
- `__init__.py`: Variable entfernt
- `services.py`: Parameter entfernt
- `analysis.py`: Verwendung entfernt
- `translations/de.json`: Übersetzung entfernt

**Verifiziert:**
```bash
$ Select-String "smooth_video" *.py | Measure-Object | Select-Object -ExpandProperty Count
0
```

---

## Vorherige Fixes (v1.2.2)

### 5. Mobile Portrait-Ansicht ✅
**Session:** 06.02.2026

- Mobile Portrait-Layout (Ring-Style)
- Footer und Tabs mobil scrollbar und kompakt
- Video-Controls auf Mobile ausgeblendet
- @media-Queries für 768px/480px
- Getestet auf Android/iOS

---

### 6. MEDIUM Findings Remediation (v1.2.1) ✅
**Session:** 05.02.2026

- **CODE-001**: `analyze_recording` CC 140→23 (-84%)
- **REL-001**: 7 silent `except:pass` → Debug-Logging
- **SEC-002**: SECURITY.md erstellt

---

## Bekannte/Offene Issues

### 1. Face Match Threshold zu niedrig ⚠️
**Symptom:** Unbekannte Personen werden als bekannte erkannt

**Workaround:** In Einstellungen → Analyse auf 0.55-0.60 erhöhen

**Status:** ⚠️ BEKANNT - Manueller Eingriff nötig

---

### 2. Integration Icon fehlt ⏳
**Symptom:** In HA Einstellungen → Integrationen kein Icon

**Lösung:** PR an https://github.com/home-assistant/brands erstellen

**Status:** ⏳ OFFEN (kosmetisch)

---

## Server-Status (07.02.2026, 00:05 Uhr)

| Komponente | Status | Details |
|------------|--------|---------|
| Integration v1.2.2 | ✅ Deployed | Alle WebSocket Handler aktiv |
| Detector Addon | ✅ Aktuell | Container `addon_local_rtsp_recorder_detector` |
| TPU | ✅ Healthy | Coral USB Accelerator funktioniert |
| Card | ✅ Deployed | 279.414 Bytes, Lokal = Server |
| Stats Reset | ✅ Funktioniert | Endpoint getestet |
| Recording Indicator | ✅ Fixed | Multi-Kamera Events korrekt |

---

## Geänderte Dateien in dieser Session

### Integration (`custom_components/rtsp_recorder/`):
| Datei | Änderung |
|-------|----------|
| `websocket_handlers.py` | `ws_reset_detector_stats()` hinzugefügt |
| `config_flow.py` | `smooth_video` entfernt |
| `__init__.py` | `smooth_video` entfernt |
| `services.py` | `smooth_video` entfernt |
| `analysis.py` | `smooth_video` entfernt |
| `translations/de.json` | `smooth_video` Übersetzung entfernt |

### Detector Addon (`addons/rtsp-recorder-detector/`):
| Datei | Änderung |
|-------|----------|
| `app.py` | `POST /stats/reset` Endpoint hinzugefügt |

### Frontend (`www/`):
| Datei | Änderung |
|-------|----------|
| `rtsp-recorder-card.js` | Stats Reset Button, Recording Indicator Fix |

---

## Deployment-Befehle

```bash
# Integration deployen
scp custom_components/rtsp_recorder/*.py root@homeassistant.local:/root/config/custom_components/rtsp_recorder/
ssh root@homeassistant.local "ha core restart"

# Card deployen
scp www/rtsp-recorder-card.js root@homeassistant.local:/root/config/www/
ssh root@homeassistant.local "sed -i 's/\r$//' /root/config/www/rtsp-recorder-card.js"

# Sync prüfen
$local = (Get-Item "www/rtsp-recorder-card.js").Length
$remote = ssh root@homeassistant.local "stat -c%s /root/config/www/rtsp-recorder-card.js"
if ($local -eq $remote) { "✓ SYNCHRON" } else { "✗ MISMATCH" }
```

---

**Zuletzt aktualisiert:** 07. Februar 2026, 00:10 Uhr
