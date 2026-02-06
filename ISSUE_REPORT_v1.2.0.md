# ISSUE REPORT v1.2.0

**Datum:** 05. Februar 2026  
**Version:** v1.2.2 BETA  
**Status:** Produktionsreif - MEDIUM Findings behoben

---

## Behobene Issues in dieser Session


### 1. Mobile Portrait-Ansicht (v1.2.2) ✅
**Session:** 06.02.2026, 10:00-12:00 Uhr

**Behoben/Implementiert:**
- Mobile Portrait-Layout (Ring-Style)
- Footer und Tabs mobil scrollbar und kompakt
- Video-Controls auf Mobile ausgeblendet, stattdessen Download/Löschen im Footer
- Leistungsanzeige und Checkboxen mobil optimiert
- Status-Indikatoren mobil ausgeblendet
- Vollständige @media-Queries für 768px/480px
- Getestet auf Android/iOS

---

### 0. MEDIUM Findings Remediation (v1.2.1) ✅
**Session:** 05.02.2026, 22:30-23:10 Uhr

**Behoben:**
- **CODE-001**: `analyze_recording` CC 140→23 (Grade F→D, -84%)
- **REL-001**: 7 kritische silent `except:pass` → Debug-Logging hinzugefügt
- **MEDIUM-001**: 30 generische Exception-Handler analysiert, alle korrekt
- **SEC-002**: SECURITY.md erstellt mit Biometrie-Policy

**Geänderte Dateien:**
- `analysis.py`: 16 Helper-Funktionen extrahiert, CC drastisch reduziert
- `__init__.py`: Timer cancel + person entities logging
- `helpers.py`: log_to_file stderr fallback
- `services.py`: Snapshot task + person entities logging

**Neue Dateien:**
- `SECURITY.md`: Biometrische Daten Policy, GDPR-Hinweise
- `MEDIUM_FINDINGS_REMEDIATION.md`: Session-Dokumentation

**Commit:** `d9e43cc` - fix(medium): REL-001 silent except:pass + SEC-002 documentation

**Status:** ✅ DEPLOYED + LIVE GETESTET (432 Analyse-Runs, TPU healthy)

---

### 0b. Flake8 Code Style Fixes (v1.2.1) ✅
**Session:** 05.02.2026, 23:30 Uhr

**Behoben:**
- **F824**: `global _cpu_history, _ram_history` entfernt (helpers.py) - Python Listen werden in-place modifiziert, global unnötig
- **F401**: Unused imports entfernt (websocket_handlers.py): `DOMAIN`, `_update_person_centroid`, `_update_all_face_matches`

**Commit:** `4a05b70` - fix(flake8): Remove unused global statements and imports (F824, F401)

**Status:** ✅ DEPLOYED

---

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

### Vollständige Timeline

1. **Overlay Smoothing verifiziert** - User bestätigte: "ich erkenne es deutlich am overlay das die funktion greift"
2. **System-Check durchgeführt** - TPU healthy, 33.100+ Inferences, alle Modelle geladen
3. **Kamera-Thresholds dokumentiert** - Pro-Kamera Confidence-Werte geprüft
4. **Sample Quality Analysis** implementiert:
   - `database.py`: `get_person_details_with_quality()` mit Cosine-Similarity
   - `database.py`: `bulk_delete_embeddings()` für Mehrfach-Löschung
   - `websocket_handlers.py`: 2 neue WebSocket-Endpoints
   - `rtsp-recorder-card.js`: Qualitäts-UI, Checkboxen, Bulk-Actions
5. **Mehrere Bugfixes** während Implementierung:
   - `@websocket_api.async_response` Decorator vergessen → hinzugefügt
   - `db = get_database()` Import fehlte → hinzugefügt
6. **Logo in README** integriert + Credit für @ElektroGandhi
7. **Release v1.2.0** erstellt und gepusht

### Server-Status nach Session

| Komponente | Status | Details |
|------------|--------|---------|
| Integration v1.2.0 | ✅ Deployed | Alle Features aktiv |
| TPU | ✅ Healthy | 33.100+ Inferences, ~34ms avg |
| Multi-Sensor | ✅ Funktioniert | Mehrere Sensoren pro Kamera |
| Logo + Badge | ✅ Sichtbar | Opening Logo im Header |
| Quality Analysis | ✅ Aktiv | 70.2% Ø Qualität, 23 Ausreißer erkannt |
| Overlay Smoothing | ✅ Aktiv | Alpha 0.55, EMA-Algorithmus |
| 5 Personen | ✅ In DB | Mit Quality-Scores |
| 182 Embeddings | ✅ In DB | Sven: 107, Bianca: 57, etc. |
| Aufnahmen | ✅ 61+ vorhanden | Mit Analysen |

### Wichtige Git-Commits

| Commit | Beschreibung |
|--------|--------------|
| `cf7d818` | v1.2.0: Sample Quality Analysis, Outlier Detection, Bulk Delete, Overlay Smoothing |
| `47829c5` | README: Add logo and credit to @ElektroGandhi |

### Dateien geändert in dieser Session

| Datei | Änderungen |
|-------|-----------|
| `database.py` | +`get_person_details_with_quality()`, +`bulk_delete_embeddings()` |
| `websocket_handlers.py` | +2 neue WebSocket-Handler mit `@async_response` |
| `rtsp-recorder-card.js` | +Quality UI, +Bulk Selection, +Outlier Badges |
| `README.md` | +Logo, +@ElektroGandhi Credit, +Quality Features |
| `CHANGELOG.md` | +v1.2.0 Features dokumentiert |
| `ISSUE_REPORT_v1.2.0.md` | +Session-Zusammenfassung |

### API-Endpoints (NEU in v1.2.0)

| Endpoint | Beschreibung |
|----------|--------------|
| `rtsp_recorder/get_person_details_quality` | Person mit Quality-Scores, Outlier-Erkennung |
| `rtsp_recorder/bulk_delete_embeddings` | Mehrere Embeddings auf einmal löschen |

### Git-Status

- **Branch:** main
- **Tag:** v1.2.0 (neu erstellt)
- **Remote:** https://github.com/brainAThome/RTSP-Recorder
- **Release:** https://github.com/brainAThome/RTSP-Recorder/releases/tag/v1.2.0

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

## Neue Features in v1.2.0 (05.02.2026)

### 5. Sample Quality Analysis (People DB) ✅
**Anforderung:** Qualitätsbewertung und Ausreißer-Erkennung für Face Embeddings

**Implementierung:**
- `database.py`: `get_person_details_with_quality()` - Cosine-Similarity zu Centroid
- `database.py`: `bulk_delete_embeddings()` - Mehrfach-Löschung
- `websocket_handlers.py`: Neue WebSocket-Endpoints
- `rtsp-recorder-card.js`: Qualitäts-UI mit Farbcodes

**Features:**
- Qualitäts-Score pro Sample (0-100%)
- Ausreißer-Erkennung (Schwelle: 65%)
- Bulk-Auswahl mit Checkboxen
- "Alle Ausreißer auswählen" Button
- Bulk-Löschen ausgewählter Samples
- Visuelle Indikatoren: ⚠️ Badge, Farbcodes

**Status:** ✅ IMPLEMENTIERT und deployed

---

### 6. Overlay Smoothing ✅
**Anforderung:** Flüssigere Darstellung der Analyse-Overlays (weniger Jitter)

**Implementierung:**
- `rtsp-recorder-card.js`: EMA-Algorithmus für Box-Positionen
- Config-Optionen: `analysis_overlay_smoothing`, `analysis_overlay_smoothing_alpha`
- Default Alpha: 0.55 (0.1 = sehr glatt, 1.0 = kein Smoothing)

**Status:** ✅ IMPLEMENTIERT und deployed

---

## Nächste Schritte

1. ~~Sample Quality Analysis~~ ✅ ERLEDIGT
2. ~~Overlay Smoothing~~ ✅ ERLEDIGT
3. ~~MEDIUM Findings~~ ✅ ERLEDIGT (CODE-001, REL-001, SEC-002)
4. **Type Hints erhöhen** - services.py, recorder_optimized.py
5. **Unit Tests** - Kritische Funktionen testen
6. **Brands PR** - Offizielles Icon für HA

---

**Zuletzt aktualisiert:** 05. Februar 2026, 23:15 Uhr
