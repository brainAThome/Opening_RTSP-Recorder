# Umbau: Pro-Kamera-Analyse-Einstellungen + Kamera löschen

**Branch:** `feature/per-camera-analysis-settings` · **Stand Phase 1 (Ist-Kartierung):** abgeschlossen
(11 Agenten, read-only, gegen Code v1.3.4 belegt). Dieses Dokument ist die session-unabhängige
Arbeitsgrundlage. Keine Credentials/PII — nichts Sensibles hier hinein.

## Ziel (vom Nutzer)
1. **Saubere UI-Trennung** global vs. pro-Kamera der Analyse-Einstellungen — in **Config-Flow UND
   Lovelace-Karte**.
2. **Neue Funktion „Kamera löschen"** — Scope: **nur Config/Entities** entfernen, Aufnahmen/Dateien
   auf der Platte bleiben.
3. Auslieferung: Branch → GitHub-Push + Deploy ins Live-HA — **nur** nach Credential-Scan +
   Diff-Freigabe pro Schritt.

## Grundbefund (warum „gilt für alle")
Der prominente Dialog „Offline-Analyse" ist der **globale** Step `async_step_analysis`
(config_flow.py:585-649) und schreibt **alle** Felder ohne Kamera-Suffix. Der per-Kamera-Step
`async_step_camera_config` (config_flow.py:290-484) existiert, deckt aber nur **4** Felder ab und
ist versteckt. Empirisch bestätigt: Wert aus „Offline-Analyse" landet global; `detector_confidence_<Cam>`
bleibt unberührt.

## Datenmodell IST (flat keys im ConfigEntry)
Alles flach in `{**entry.data, **entry.options}` (config_flow.py:163, __init__.py:327).
- **Global:** `analysis_<feld>` (ohne Suffix).
- **Per-Kamera (nur 4 Analyse-Felder):** `analysis_objects_<Cam>`, `detector_confidence_<Cam>`,
  `face_confidence_<Cam>`, `face_match_threshold_<Cam>` — Konvention „0/leer = global".
- **Per-Kamera-Basis (kein Analyse-Setting):** `sensors_<Cam>` (+ legacy `sensor_<Cam>`),
  `duration_<Cam>`, `snapshot_delay_<Cam>`, `rtsp_url_<Cam>`, `retention_hours_<Cam>`.
- `<Cam>` = `sanitize_camera_key(name)` (config_flow.py:75: `[^\w\s-]`→'', strip, ' '→'_'). **Kein** lower().

## Settings-Matrix (global-only vs. per-cam-fähig)
| Feld | Status | Schreiben | Lesen |
|---|---|---|---|
| analysis_objects | **per-cam** | :622 / `_<Cam>`:348 | services.py:495-497,665,766 (Fallback) |
| analysis_detector_confidence | **per-cam** | :627 / `_<Cam>`:355 | services.py:499-503,657-661,763-768 |
| analysis_face_confidence | **per-cam** | :630 / `_<Cam>`:361 | services.py (cam>0?cam:global) |
| analysis_face_match_threshold | **per-cam** | :631 / `_<Cam>`:367 | services.py |
| analysis_frame_interval | global-only (**Lücke**) | :624 | global an analyze_recording |
| analysis_face_enabled | global-only (**Lücke**) | :629 | global |
| analysis_face_multiscale | global-only | :632 | global |
| analysis_overlay_smoothing(_alpha) | global-only + **fehlende de.json-Labels** | :634-635 | global |
| analysis_enabled / device / detector_url / output_path / max_concurrent / perf_* | global-only (by design) | div. | global |
| analysis_auto_* (Scheduler) | global-only (by design) | :637-644 | __init__ Scheduler |

## Impact — UI-Trennung
- `config_flow.py:290-484` per-cam-Step um fehlende Felder erweitern (frame_interval, face_enabled,
  multiscale, overlay) — falls echtes per-cam gewollt.
- `config_flow.py:585-649` bleibt globaler Default-Editor; Label klarstellen „Standard für alle ohne
  eigenen Wert".
- `services.py` 3 Call-Sites (499-505, 657-665, 763-768): Fallback-Lesen für **jedes** neue
  per-cam-Feld — **zentrale Helper-Funktion** statt 3× dupliziert.
- `websocket_handlers.py`: **neue Commands** (per-cam get/set settings) — bestehender
  `ws_set_camera_objects`:557 als Vorlage. `ws_set_analysis_config`:510 speichert nur `auto_*`.
- `www/rtsp-recorder-card.js` `renderAnalysisTab` (~2265-2666): per-cam-Editor + Kamera-Selektor;
  Objekt-Editor (set_camera_objects) als Vorlage.
- `de.json/en.json/strings.json`: Labels neue Felder + fehlende overlay-Labels; klare Benennung.
- `const.py`: neue `WS_TYPE_*`.

## Impact — Kamera löschen (existiert NIRGENDS, neu)
Zu entfernende flache Keys (ALLE Suffixe): `sensors_<Cam>`, `sensor_<Cam>` (legacy), `duration_<Cam>`,
`snapshot_delay_<Cam>`, `rtsp_url_<Cam>`, `retention_hours_<Cam>`, `analysis_objects_<Cam>`,
`detector_confidence_<Cam>`, `face_confidence_<Cam>`, `face_match_threshold_<Cam>`.
- HA-Entities via entity_registry: `camera.<cam>`, `camera.<cam>_snapshot`, `binary_sensor.<cam>_motion`,
  abgeleitete Person/Recognition-Sensoren.
- `__init__.py` Motion-Listener + Health-Watchdog referenzieren Kameranamen → nach Löschen
  `async_update_entry` + `async_reload`.
- **Disk:** NICHT löschen (Nutzer-Entscheid) — Aufnahmen/Thumbnails/_analysis bleiben.
- Muss `sanitize_camera_key` + `_deduplicate_cameras`-Logik respektieren.

## Risiken (aus Devil's-Advocate-Verifikation)
1. **KEY-MISMATCH (höchstes Risiko):** Schreib-Key `sanitize_camera_key` vs. Lese-Key
   `_extract_camera_name_from_path`/Ordnername müssen identisch sein, sonst greift Override stumm nie.
2. **Zwei Normalisierer:** `sanitize_camera_key` (space→_) vs. `normalize_camera_name` (lower, _→space)
   — Verwechslung = stiller Verlust.
3. **entry.data vs entry.options:** WS schreibt teils in data, config_flow in options →
   `async_update_entry` muss beide konsistent halten.
4. **Reload-Pflicht:** ohne `async_reload` bleiben Listener/Scheduler stale.
5. **DB/JSON nicht im Lösch-Scope:** `database.py` (SQLite, camera-Spalte = Klartextname) +
   `people_db.py` (rtsp_recorder_people.json) referenzieren Kameranamen → verwaisen beim Löschen.
   (Bewusst außerhalb „nur Config/Entities" — als bekannte Rest-Verwaisung dokumentieren.)
6. **Rückwärtskompatibilität:** flat→nested würde brechen → **additive** Suffix-Beibehaltung.
7. **Test-Schulden:** Teil der Tests rot (ImportError `from analysis import …` — braucht
   `PYTHONPATH=custom_components/rtsp_recorder`). Baseline vor Umbau: **141 passed** (venv py3.13).

## Designentscheidungen (offen — über 3 Runden + Verifikation, NICHT im Alleingang)
- D1: Welche der global-only-Felder werden per-cam-fähig? (Vorschlag: objects + 3 Schwellen [schon da]
  + frame_interval + face_enabled + multiscale; NICHT: device, auto_*, max_concurrent, output_path, perf.)
- D2: Speicherort konsistent — alles in entry.options (config_flow-Konvention), WS angleichen.
- D3: Zentrale Helper `get_cam_setting(config, field, cam, default)` für Schreib- UND Lesepfad, damit
  Key-Bildung an EINER Stelle lebt (behebt Risiko 1+2).
- D4: UI — Kamera-Selektor oben im Analyse-Tab; „Alle/Global" + je Kamera; Reset-auf-global-Button.

## Arbeitsstand-Infra
- Clone: `/tmp/rtsp-work`, Branch `feature/per-camera-analysis-settings` (voller Clone, kein Push).
- Test-venv: `/tmp/rtsp-work/.venv` (Python 3.13 + pytest-homeassistant-custom-component).
- Baseline-Test: `PYTHONPATH=custom_components/rtsp_recorder .venv/bin/python -m pytest tests/`.
