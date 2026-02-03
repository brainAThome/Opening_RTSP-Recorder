# RTSP Recorder v1.1.0k - Marktvergleich & Projekteinschätzung

**Stand:** 03. Februar 2026  
**Version:** v1.1.0k BETA  
**Audit Score:** 90.0% (Grade A)

---

## 🏆 Vergleich mit Open-Source Alternativen

| Projekt | ⭐ Stars | 👥 Contributors | 📦 Releases | 🎯 Fokus |
|---------|---------|----------------|-------------|----------|
| **[Frigate NVR](https://github.com/blakeblackshear/frigate)** | 29,900 | 620 | 77 | Vollständiges NVR, Object Detection |
| **[MotionEye](https://github.com/motioneye-project/motioneye)** | 4,500 | 161 | 55 | Motion Detection, Web UI |
| **[Double Take](https://github.com/jakowenko/double-take)** | 1,400 | 7 | 54 | Face Recognition Hub |
| **[RTSP Recorder](https://github.com/brainAThome/RTSP-Recorder)** | ~10 | 1 | 5 | HA Integration mit Face Recognition |

---

## 📋 Feature-Vergleich

| Feature | Frigate | MotionEye | Double Take | RTSP Recorder |
|---------|:-------:|:---------:|:-----------:|:-------------:|
| **Motion Recording** | ✅ | ✅ | ❌ | ✅ |
| **Object Detection** | ✅ | ❌ | ❌ | ✅ |
| **Face Detection** | ❌ | ❌ | ✅* | ✅ |
| **Face Recognition** | ❌ | ❌ | ✅* | ✅ |
| **Face Training UI** | ❌ | ❌ | ✅ | ✅ |
| **Negative Samples** | ❌ | ❌ | ❌ | ✅ |
| **Coral EdgeTPU** | ✅ | ❌ | ❌ | ✅ |
| **CPU Fallback** | ✅ | ✅ | N/A | ✅ |
| **HA Integration** | ✅ Add-on | ❌ | ✅ MQTT | ✅ Native |
| **Lovelace Card** | ✅ Separat | ❌ | ❌ | ✅ Inkludiert |
| **24/7 Recording** | ✅ | ✅ | ❌ | ❌ |
| **RTSP Re-Stream** | ✅ | ❌ | ❌ | ❌ |
| **Zones/Masks** | ✅ | ✅ | ❌ | ❌ |
| **Person Entities** | ❌ | ❌ | ✅ | ✅ |
| **Movement Profile** | ❌ | ❌ | ❌ | ✅ |
| **Per-Camera Thresholds** | ✅ | ❌ | ❌ | ✅ |
| **Multi-Language** | ✅ (Weblate) | ✅ | ❌ | ✅ 5 Sprachen |
| **SQLite Backend** | ✅ | ❌ | ✅ | ✅ |
| **HACS Compatible** | ✅ | N/A | ✅ | ✅ |

*Double Take benötigt externe Detector (CompreFace, DeepStack, Rekognition)

---

## 🎯 USPs (Unique Selling Points) RTSP Recorder

| USP | Beschreibung | Konkurrenz |
|-----|--------------|------------|
| **All-in-One Face Recognition** | Komplette Pipeline inkl. Coral TPU | Frigate: keine Face Recognition, Double Take: benötigt externes System |
| **Negative Samples** | Ausschluss von Fehlerkennungen (75% Threshold) | Kein anderes Projekt hat das |
| **Native HA Integration** | Keine zusätzlichen Add-ons nötig | Frigate: separates Add-on, Double Take: MQTT-basiert |
| **Inkludierte Lovelace Card** | Eine Datei = komplett | Frigate: separate Integration/Card |
| **Movement Profile** | Recognition History mit Zeitstempel | Einzigartig |
| **Per-Camera Thresholds** | Individuelle Detection/Face/Match Werte | Frigate: ähnlich, andere: nicht |
| **Konfigurierbares Cleanup** | 1-24h Intervall, Analysis-Cleanup | Einzigartig |

---

## 📈 Stärken & Schwächen

### ✅ STÄRKEN RTSP Recorder

| Stärke | Details |
|--------|---------|
| **Vollständige Face Pipeline** | Detection → Embedding → Matching → Training in einem |
| **Negative Samples** | Einzigartiges Feature zur Verbesserung der Genauigkeit |
| **Coral TPU Support** | Hardware-Beschleunigung wie Frigate |
| **Native HA Integration** | Custom Component, keine Docker-Container nötig |
| **ISO 25010/27001 Audit** | 90% Score, professionelle Codequalität |
| **Gute Dokumentation** | Mermaid-Diagramme, detaillierte README |
| **Aktive Entwicklung** | 38 Issues in v1.1.0 behoben |

### ⚠️ SCHWÄCHEN RTSP Recorder

| Schwäche | Details | Frigate zum Vergleich |
|----------|---------|----------------------|
| **Keine 24/7 Aufnahme** | Nur Motion-triggered | ✅ Frigate hat 24/7 |
| **Keine Zones/Masks** | Keine räumliche Filterung | ✅ Frigate hat built-in Editor |
| **Kein RTSP Re-Stream** | Direkte Kamera-Verbindungen | ✅ Frigate reduziert Verbindungen |
| **Single Developer** | Bus-Factor = 1 | 620 Contributors bei Frigate |
| **Kleine Community** | ~10 Stars | 29,900 bei Frigate |
| **Beta Status** | Noch nicht production-stable | Frigate: 0.16.4 stable |

---

## 🎯 Zielgruppen-Vergleich

| Zielgruppe | Empfehlung |
|------------|------------|
| **Vollständiges NVR benötigt** | → **Frigate** (24/7, Zones, Re-Stream) |
| **Face Recognition mit Frigate** | → **Double Take** (als Add-on zu Frigate) |
| **Einfache Motion-Erkennung** | → **MotionEye** (leichtgewichtig) |
| **Face Recognition in HA ohne Docker** | → **RTSP Recorder** ✅ |
| **Personen-Tracking mit Negative Samples** | → **RTSP Recorder** ✅ |
| **Coral TPU + Face Recognition** | → **RTSP Recorder** ✅ |

---

## 📊 Projektstand-Einschätzung

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    RTSP RECORDER v1.1.0k PROJEKT-STATUS                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  REIFEGRAD:        ████████░░░░░░░░  BETA (60%)                              ║
║  CODE-QUALITÄT:    █████████████░░░  90% (ISO Audit)                         ║
║  FEATURE-SET:      ██████████░░░░░░  65% (vs Frigate)                        ║
║  DOKUMENTATION:    ████████████░░░░  80%                                     ║
║  COMMUNITY:        ██░░░░░░░░░░░░░░  10% (1 Dev, ~10 Stars)                  ║
║  INNOVATION:       ████████████████  100% (Negative Samples, Movement)       ║
║                                                                               ║
║  GESAMTBEWERTUNG:  ████████████░░░░  75% - VIELVERSPRECHEND                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 🚀 Empfehlungen für die Zukunft

| Priorität | Feature | Impact |
|-----------|---------|--------|
| 🔴 HIGH | **24/7 Recording Option** | Würde Frigate-Konkurrenz ermöglichen |
| 🔴 HIGH | **Zone/Mask Editor** | Wichtig für komplexe Szenen |
| 🟡 MEDIUM | **RTSP Re-Stream** | Reduziert Kamera-Last |
| 🟡 MEDIUM | **WebRTC Live View** | Moderne Streaming-Technologie |
| 🟢 LOW | **Audio Detection** | Frigate hat das |
| 🟢 LOW | **Multi-Model Support** | YOLO, etc. |

---

## 💡 Fazit

**RTSP Recorder v1.1.0k** ist ein **Nischen-Projekt mit einzigartigen Features**:

| Aspekt | Bewertung |
|--------|-----------|
| **Gegen Frigate** | ❌ Kann nicht konkurrieren (Feature-Set, Community) |
| **Mit Frigate** | ✅ Komplementär (Face Recognition Add-on) |
| **Alleinstellung** | ✅ Negative Samples, Movement Profile, Native HA |
| **Zukunftspotential** | ⭐⭐⭐⭐ Hoch, wenn Community wächst |

**Empfehlung:** Projekt als **"Face Recognition Integration für Home Assistant"** positionieren, nicht als Frigate-Alternative. Die Negative-Samples und Movement-Profile Features sind echte Innovationen!

---

## 📈 Code-Metriken Vergleich

| Metrik | Frigate | Double Take | RTSP Recorder |
|--------|---------|-------------|---------------|
| **Python LOC** | ~100k+ | - | 10,062 |
| **TypeScript/JS LOC** | ~150k+ | ~20k | 4,328 |
| **Gesamt LOC** | ~250k+ | ~25k | ~15k |
| **Module** | 50+ | 10+ | 20 |
| **Tests** | ✅ CI/CD | ✅ | ❌ (TODO) |
| **Docker** | ✅ Official | ✅ | ❌ (HA only) |

---

## 🔗 Links

- **Frigate NVR**: https://github.com/blakeblackshear/frigate
- **MotionEye**: https://github.com/motioneye-project/motioneye
- **Double Take**: https://github.com/jakowenko/double-take
- **RTSP Recorder**: https://github.com/brainAThome/RTSP-Recorder

---

*Erstellt: 03. Februar 2026*
