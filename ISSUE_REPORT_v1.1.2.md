# ISSUE REPORT v1.1.2

**Datum:** 05. Februar 2026  
**Version:** v1.1.2  
**Status:** Alle kritischen Bugs behoben

---

## Behobene Issues

### 1. Batch Analysis "auto_device undefined" (BEHOBEN)
**Symptom:** "Alle Aufnahmen analysieren" startete, aber jede Datei schlug fehl mit:
```
Batch analysis error for ...: name 'auto_device' is not defined
```

**Ursache:** In `services.py` Zeile 614 wurde `auto_device` verwendet, das nur in einem anderen Scope (`handle_analyze_recording`) definiert war, aber nicht in `_analyze_batch`.

**Fix:** `device=auto_device` geändert zu `device=device` (korrekter Funktionsparameter).

**Status:** ✅ BEHOBEN in v1.1.2

---

### 2. Integration Icon wird nicht angezeigt (BEKANNT)
**Symptom:** In HA Einstellungen → Integrationen wird kein Icon für RTSP Recorder angezeigt.

**Ursache:** Home Assistant lädt Icons nur aus dem offiziellen `home-assistant/brands` Repository, nicht aus lokalen Dateien.

**Workaround:** PR an https://github.com/home-assistant/brands erstellen.

**Status:** ⏳ OFFEN (kosmetisch, nicht kritisch)

---

### 3. Face Match Threshold zu niedrig (BEKANNT)
**Symptom:** Unbekannte Personen werden fälschlicherweise als bekannte Person erkannt.

**Ursache:** Default `face_match_threshold` ist 0.35 (35%). Das ist zu permissiv für zuverlässige Unterscheidung.

**Workaround:** In Einstellungen → Analyse den Wert auf 0.55-0.60 erhöhen.

**Status:** ⚠️ BEKANNT - User muss manuell anpassen

---

## Offene Verbesserungen (Nice-to-have)

### 1. Type Hints Coverage erhöhen
**Aktuell:** 88.2% (134/152 Funktionen)
**Ziel:** 95%+
**Betroffene Module:** services.py (50%), recorder_optimized.py (58.8%)

### 2. Test Coverage erhöhen
**Aktuell:** Grundlegende Integration Tests
**Ziel:** Unit Tests für alle kritischen Funktionen

### 3. Brands Repository PR
**Status:** Vorbereitet, nicht eingereicht
**Ziel:** Offizielles Icon in HA Integration

---

## Keine bekannten kritischen Bugs

Per 05. Februar 2026 sind alle kritischen Bugs behoben. Die Integration funktioniert wie erwartet.

---

**Zuletzt aktualisiert:** 05. Februar 2026
