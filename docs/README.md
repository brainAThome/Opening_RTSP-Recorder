# 📚 RTSP Recorder - Dokumentation

**Version:** 1.1.1 | **ISO 25010:** 93/100 | **ISO 27001:** 85/100

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
| [AUDIT_REPORT_v1.1.0_BETA.md](../AUDIT_REPORT_v1.1.0_BETA.md) | Qualitäts-Audit |

### Technisch
| Datei | Beschreibung |
|-------|--------------|
| [HANDOVER_v1.1.0.md](../HANDOVER_v1.1.0.md) | Entwickler-Übergabe |
| [AGENT_PROMPT_v1.1.0.md](../AGENT_PROMPT_v1.1.0.md) | AI-Agent Kontext |

---

## Quick Links

### Integration
- **GitHub:** [github.com/brainAThome/Opening_RTSP-Recorder](https://github.com/brainAThome/Opening_RTSP-Recorder)
- **HACS:** Custom Repository

### Support
- **Issues:** [GitHub Issues](https://github.com/brainAThome/Opening_RTSP-Recorder/issues)
- **Discussions:** [GitHub Discussions](https://github.com/brainAThome/Opening_RTSP-Recorder/discussions)

---

## Version 1.1.0n BETA Highlights

### Neue Features
| Feature | Beschreibung |
|---------|--------------|
| 👤 **Person Detail Popup** | Klickbare Personennamen öffnen Übersicht aller Samples |
| 🏠 **Person-Entities** | `binary_sensor.rtsp_person_{name}` für Automationen |
| 📊 **Erkennungszähler** | Zeigt wie oft Person erkannt wurde |
| ⏰ **Zuletzt gesehen** | Datum, Uhrzeit und Kamera der letzten Erkennung |
| 🗑️ **Sample-Löschung** | Einzelne Samples im Popup entfernen |

### Neue Module
| Modul | Zweck |
|-------|-------|
| `rate_limiter.py` | DoS-Schutz via Token Bucket |
| `exceptions.py` | 20+ Custom Exception Types |
| `performance.py` | Operations-Metriken |
| `migrations.py` | Database Schema Versioning |

### Verbesserungen
- ⚡ Parallele Snapshots (3-5s schneller)
- 📊 TPU-Load Anzeige
- 🌐 5 Sprachen (DE, EN, ES, FR, NL)
- 🧪 pytest Unit Tests (8 Dateien)
- 🧹 Automatische Analyse-Bereinigung

### Code-Qualität
- **11,832** Lines of Code
- **27** Python Module
- **74%** Type Hint Coverage
- **86%** Docstring Coverage
- **84.4%** Audit Score

---

*Dokumentation zuletzt aktualisiert: 03. Februar 2026*
