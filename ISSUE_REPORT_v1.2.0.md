# ISSUE REPORT v1.2.0

**Datum:** 05. Februar 2026  
**Version:** v1.2.0 BETA  
**Status:** Produktionsreif mit bekannten Kosmetik-Issues

---

## Behobene Issues in dieser Session

### 1. Multi-Sensor Feature (NEU in v1.2.0) ✅
**Anforderung:** Mehrere Trigger-Sensoren pro Kamera

**Implementierung:**
- `config_flow.py`: EntitySelector mit `multiple=True`
- `__init__.py`: Loop über Sensor-Liste mit `async_track_state_change_event`
- Backward-kompatibel: `sensor_{camera}` (alt) wird weiterhin unterstützt

**Status:** ✅ IMPLEMENTIERT und deployed

---

### 2. Logo-Integration ✅
**Anforderung:** Opening-Logo statt "Kamera Archiv" Text

**Implementierung:**
- `www/opening_logo4.png` - 93KB transparentes PNG
- `rtsp-recorder-card.js` Zeile ~1191: IMG-Tag mit Logo
- Version-Badge: "BETA v1.2.0"

**Status:** ✅ IMPLEMENTIERT und deployed

---

### 3. Batch Analysis "auto_device undefined" (v1.1.2) ✅
**Symptom:** "Alle Aufnahmen analysieren" schlug fehl mit:
```
Batch analysis error for ...: name 'auto_device' is not defined
```

**Ursache:** In `services.py` Zeile 614 wurde `auto_device` verwendet (falscher Scope)

**Fix:** `device=auto_device` → `device=device`

**Status:** ✅ BEHOBEN in v1.1.2

---

### 4. Card Konfigurationsfehler durch CRLF ✅
**Symptom:** Nach Card-Upload: "Konfigurationsfehler" im Dashboard

**Ursache:** Windows CRLF (`\r\n`) in JS-Datei stört Browser-Parsing

**Fix:** Nach jedem Upload:
```bash
ssh root@192.168.178.123 "sed -i 's/\r$//' /config/www/rtsp-recorder-card.js"
```

**Status:** ✅ BEHOBEN - Workflow dokumentiert

---

### 5. Browser-Cache verhindert Card-Updates ✅
**Symptom:** Änderungen erscheinen nicht trotz korrektem Upload

**Ursache:** Aggressives Browser-Caching der JS-Datei

**Lösung:** 
- Strg+Shift+R (Hard Refresh) ODER
- Browser schließen und neu öffnen

**Status:** ✅ DOKUMENTIERT - User-Aktion erforderlich

---

## Offene Issues

### 1. Face Match Threshold zu niedrig ⚠️
**Symptom:** Unbekannte Personen werden als bekannte erkannt

**Ursache:** Default `face_match_threshold` ist 0.35 (zu permissiv)

**Workaround:** In Einstellungen → Analyse auf 0.55-0.60 erhöhen

**Status:** ⚠️ BEKANNT - Manueller Eingriff nötig

---

### 2. Integration Icon fehlt ⏳
**Symptom:** In HA Einstellungen → Integrationen kein Icon

**Ursache:** HA lädt Icons nur aus offiziellem `home-assistant/brands` Repository

**Lösung:** PR an https://github.com/home-assistant/brands erstellen

**Status:** ⏳ OFFEN (kosmetisch)

---

### 3. Type Hints Coverage nicht 100% ℹ️
**Aktuell:** 88.2% (134/152 Funktionen)

**Betroffene Module:**
- `services.py`: 50%
- `recorder_optimized.py`: 58.8%

**Status:** ℹ️ Nice-to-have

---

### 4. Thumbnails-Ordner leer ℹ️
**Symptom:** `/media/rtsp_recorder/thumbnails/` ist leer

**Ursache:** Thumbnails werden nur bei Analyse erstellt

**Status:** ℹ️ Normal wenn keine Analyse durchgeführt

---

## Session-Zusammenfassung (05.02.2026)

### Timeline

1. **Batch Analysis Bug** gefixt (v1.1.2)
2. **Multi-Sensor Feature** implementiert (v1.2.0)
3. **Logo-Integration** durchgeführt
   - Mehrere Versuche wegen Browser-Cache-Problemen
   - CRLF-Problem identifiziert und gelöst
4. **Dokumentation** aktualisiert (README, CHANGELOG)
5. **Deep-Analyse** des laufenden Systems
6. **HANDOVER + AGENT_PROMPT** erstellt

### Server-Status nach Session

| Komponente | Status |
|------------|--------|
| Integration v1.2.0 | ✅ Deployed |
| Multi-Sensor | ✅ Funktioniert |
| Logo + Badge | ✅ Sichtbar |
| 5 Personen | ✅ In DB |
| 132 Embeddings | ✅ In DB |
| 175 Analysen | ✅ In DB |
| Aufnahmen | ✅ 61+ vorhanden |

### Dateien geändert

| Datei | Änderung |
|-------|----------|
| `config_flow.py` | Multi-Sensor EntitySelector |
| `__init__.py` | Sensor-Loop für Multi-Sensor |
| `strings.json` | Labels aktualisiert |
| `de.json`, `en.json` | Übersetzungen |
| `rtsp-recorder-card.js` | Logo + Version Badge |
| `README.md` | v1.2.0 Features dokumentiert |
| `CHANGELOG.md` | v1.2.0 Einträge |

### Git-Status

- Tag: `v1.2.0` erstellt und gepusht
- GitHub: `brainAThome/RTSP-Recorder`

---

## Bekannte Fallstricke für Agenten

| Problem | Vermeidung |
|---------|------------|
| CRLF in JS-Dateien | `sed -i 's/\r$//' <datei>` nach Upload |
| Browser-Cache | User zu Hard-Refresh auffordern |
| PowerShell Escaping | Einfache Befehle oder Server-Skripte |
| lovelace_resources editieren | Nur wenn absolut nötig, JSON prüfen |
| Falscher SSH-User | `root@192.168.178.123` verwenden |

---

## Nächste Schritte

1. **Type Hints erhöhen** - services.py, recorder_optimized.py
2. **Unit Tests** - Kritische Funktionen testen
3. **Brands PR** - Offizielles Icon für HA
4. **Face Threshold** - Default auf 0.55 erhöhen?

---

**Zuletzt aktualisiert:** 05. Februar 2026, 19:45 Uhr
