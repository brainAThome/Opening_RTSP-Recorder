# 📚 Opening RTSP Recorder - Dokumentation

**Version:** 1.3.4 | **ISO 25010:** 94/100 | **ISO 27001:** 88/100

---

## Schnellstart

| Schritt | Link |
|---------|------|
| 1. Installation | [INSTALLATION.md](INSTALLATION.md) |
| 2. Erste Schritte | [USER_GUIDE.md](USER_GUIDE.md#3-erste-schritte) |
| 3. Kameras konfigurieren | [CONFIGURATION.md](CONFIGURATION.md#2-kamera-einstellungen) |

---

## Dokumentations-Übersicht

### 📖 [Benutzerhandbuch](USER_GUIDE.md)
Komplette Anleitung für alle Features:
- Dashboard-Nutzung
- Timeline & Aufnahmen
- KI-Analyse
- Personen-Erkennung
- Person Detail Popup (NEU)
- Automatisierungen mit Person-Entities

### 🚀 [Installation](INSTALLATION.md)
Schritt-für-Schritt Installationsanleitung:
- HACS Installation
- Manuelle Installation
- Detector Add-on Setup
- Coral USB Einrichtung

### ⚙️ [Konfiguration](CONFIGURATION.md)
Vollständige Konfigurationsreferenz:
- Alle Optionen erklärt
- Beispiel-Konfigurationen
- Per-Kamera Einstellungen

### 🧠 [Gesichtserkennung](FACE_RECOGNITION.md)
Face Recognition Training & Setup:
- Personen anlegen
- Training mit Samples
- Person Detail Popup (NEU)
- Schwellenwerte anpassen
- Person-Entities für Automationen (NEU)

### 🔧 [Troubleshooting](TROUBLESHOOTING.md)
Problemlösung & FAQ:
- Schnelldiagnose
- Häufige Probleme
- Log-Analyse
- Fehlermeldungen

---

## Projekt-Dateien

### Reports
| Datei | Beschreibung |
|-------|--------------|
| [CHANGELOG.md](../CHANGELOG.md) | Versionshistorie |
| [README.md](../README.md) | Projekt-Übersicht |
| [RELEASE_HISTORY.md](RELEASE_HISTORY.md) | Release-Übersicht |
| [FINAL_AUDIT_REPORT_v1.3.1.md](FINAL_AUDIT_REPORT_v1.3.1.md) | Qualitäts-Audit (ISO 25010 + ISO 27001) |
| [FINAL_AUDIT_REPORT_v1.3.1_DE.md](FINAL_AUDIT_REPORT_v1.3.1_DE.md) | Qualitäts-Audit (Deutsch) |

### Technisch
| Datei | Beschreibung |
|-------|--------------|
| [SECURITY.md](../SECURITY.md) | Sicherheitsrichtlinie |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Beitragsrichtlinien |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Verhaltenskodex |

---

## Quick Links

### Integration
- **GitHub:** [github.com/brainAThome/Opening_RTSP-Recorder](https://github.com/brainAThome/Opening_RTSP-Recorder)
- **HACS:** Custom Repository

### Support
- **Issues:** [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)
- **Discussions:** [GitHub Discussions](https://github.com/brainAThome/Opening_RTSP-Recorder/discussions)

---

## Version 1.3.4 Highlights

### Neue Features (v1.3.3-v1.3.4)
| Feature | Beschreibung |
|---------|-------------|
| 📱 **Mobile Video Fix** | Videos laden sofort auf Mobilgeräten (fMP4 → MP4 Remux) |
| 🌐 **Video Streaming Endpoint** | `/api/rtsp_recorder/video/` mit HTTP Range/206 Support |
| 🔧 **Post-Recording Remux** | Automatisch nach jeder Aufnahme, <1 Sekunde |
| 📦 **Batch Migration** | 497 bestehende Videos konvertiert |

### Bisherige Features
| Feature | Beschreibung |
|---------|-------------|
| 👤 **Person Detail Popup** | Klickbare Personennamen öffnen Übersicht aller Samples |
| 🏠 **Person-Entities** | `binary_sensor.rtsp_person_{name}` für Automationen |
| 📊 **Sample Quality Analysis** | Qualitäts-Scores mit Outlier-Erkennung |
| 📲 **Push Notifications** | Benachrichtigungen bei Personenerkennung |
| 🔧 **Debug Mode** | Toggle für technische Anzeigen |
| 🏷️ **Opening Branding** | Einheitliches Branding in 5 Sprachen |

### Neue Module
| Modul | Zweck |
|-------|-------|
| `rate_limiter.py` | DoS-Schutz via Token Bucket |
| `exceptions.py` | 20+ Custom Exception Types |
| `performance.py` | Operations-Metriken |
| `migrations.py` | Database Schema Versioning |
| `analysis_helpers.py` | Analyse-Hilfsfunktionen |

### Code-Qualität
- **~12,000+** Lines of Code
- **27** Python Module
- **100%** Type Hint Coverage
- **ISO 25010:** 94/100 (EXCELLENT)
- **ISO 27001:** 88/100 (GOOD)

---

*Dokumentation zuletzt aktualisiert: 22. Februar 2026*
