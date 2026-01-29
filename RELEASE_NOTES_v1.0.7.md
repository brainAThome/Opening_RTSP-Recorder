# Release Notes – RTSP Recorder BETA v1.0.7

Datum: 2026-01-29

## Highlights
- Face-Detection mit Embeddings und Personen-Datenbank
- Personen-Workflow in der UI inkl. Thumbnails
- Optional pro Person eigene `binary_sensor`-Entitäten
- Auto-Analyse zuverlässiger (Datei-Ready-Check)
- Face-Detection stabiler (Retry mit niedrigerer Confidence)

## Neu
- Face-Detection/Embeddings in der Offline-Analyse
- Personen-Datenbank (Erstellen/Umbenennen/Löschen, Sample-Zuordnung)
- Personen-Tab im Dashboard mit Training-Workflow
- Option: Person-Entitäten für Automationen
- Auto Coral Toggle für automatische Analysen

## Verbesserungen
- Auto-Analyse startet schneller im Hintergrund
- Auto-Analyse wartet auf stabile Datei vor dem Start
- Face-Erkennung reagiert besser auf schwierige Frames

## Fixes
- Zuverlässigeres Matching (Fallback-Embeddings werden nicht mehr verwendet)
- Stabilere Personen-Aktionen (ID-Handling, Fallback-Matching)

## Hinweise
- Für neue Overlays/Labels bitte bestehende Aufnahmen neu analysieren.
- Nach UI-Updates Cache im Browser leeren.

## Technische Details
- Integration: v1.0.7
- Dashboard Card: v1.0.7 BETA
- Detector Add-on: v1.0.7
