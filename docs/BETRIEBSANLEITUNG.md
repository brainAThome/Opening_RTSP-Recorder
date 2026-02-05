# RTSP Recorder – Betriebsanleitung

![Version](https://img.shields.io/badge/Version-1.1.2%20BETA-brightgreen)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)

> [!NOTE]
> Diese Betriebsanleitung beschreibt die Funktionen und Bedienung der **RTSP Recorder Card** für Home Assistant.
> Stand: Februar 2026

---

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [Hauptoberfläche](#hauptoberfläche)
3. [Aufnahmen durchsehen](#aufnahmen-durchsehen)
4. [Videowiedergabe](#videowiedergabe)
5. [Einstellungen (Card)](#einstellungen-card)
   - [Allgemein](#allgemein)
   - [Speicher](#speicher)
   - [Analyse](#analyse)
   - [Personen](#personen)
   - [Bewegung](#bewegung)
   - [Leistung](#leistung)
6. [Konfiguration (Integration)](#konfiguration-integration)
   - [Globale Einstellungen](#globale-einstellungen)
   - [Kamera hinzufügen](#kamera-hinzufügen)
   - [Offline-Analyse](#offline-analyse-konfiguration)
7. [Performance-Anzeige](#performance-anzeige)
8. [Tipps & Best Practices](#tipps--best-practices)
9. [Fehlerbehebung](#fehlerbehebung)

---

## Übersicht

Der **RTSP Recorder** ist eine vollständige Videoüberwachungslösung mit KI-gestützter Objekterkennung für Home Assistant. Mit der integrierten Lovelace-Card können Sie:

- 🎥 Aufnahmen von RTSP-Kameras durchsehen
- 🔍 KI-basierte Objekterkennung mit Coral USB EdgeTPU
- 👤 Gesichtserkennung und Personenmanagement
- 📊 Echtzeit-Leistungsüberwachung
- 🗂️ Automatische Speicherverwaltung

---

## Hauptoberfläche

![Hauptoberfläche der RTSP Recorder Card](images/rtsp_recorder_interface_1770149290384.png)

Die Hauptoberfläche besteht aus drei Bereichen:

### 1. Kopfzeile
| Element | Beschreibung |
|---------|--------------|
| **Kamera Archiv** | Titel mit Versionsanzeige (BETA v1.1.2) |
| **Letzte 24 Std** | Zeitfilter für die Aufnahmen |
| **Kameras** | Kameraauswahl-Dropdown |
| **Menue** | Öffnet die Einstellungen |

### 2. Video-Player (Zentrum)
Der zentrale Bereich zeigt das ausgewählte Video mit Standard-Steuerelementen:
- ▶️ Play/Pause
- 🔊 Lautstärkeregler
- ⛶ Vollbildmodus
- Timeline/Fortschrittsbalken

### 3. Aufnahmen-Timeline (Rechts)
Eine vertikale, scrollbare Liste aller verfügbaren Aufnahmen:
- Vorschau-Thumbnails
- Kameraname und Zeitstempel
- Status-Badges (z.B. "🔄 Analyse")

---

## Aufnahmen durchsehen

### Zeitfilter verwenden
Klicken Sie auf **"Letzte 24 Std"** um den Zeitraum zu ändern:
- Letzte 24 Stunden
- Letzte 7 Tage
- Letzte 30 Tage
- Benutzerdefiniert

### Kamerafilter
Klicken Sie auf **"Kameras"** um nach bestimmten Kameras zu filtern:
- **Alle** – Zeigt alle Kameras
- Einzelne Kameras auswählen (z.B. Wohnzimmer, Flur oben)

Verfügbare Kameras in diesem Setup:
- Flur oben
- Garten hinten
- Haustuer
- Kinderzimmer
- Wohnzimmer

---

## Videowiedergabe

### Aktionsleiste
Unter dem Video-Player befinden sich folgende Steuerelemente:

| Button | Funktion |
|--------|----------|
| **Download** | Lädt die aktuelle Aufnahme herunter |
| **Loeschen** (rot) | Löscht die Aufnahme permanent |
| **Overlay** | Schaltet Objekterkennung-Markierungen ein/aus |

### Wiedergabegeschwindigkeit
Wählen Sie die Abspielgeschwindigkeit:
- **0.5x** – Zeitlupe
- **1x** – Normal (Standard)
- **2x** – Schnellvorlauf

### Objekterkennung-Overlay
Wenn aktiviert, werden erkannte Objekte mit farbigen Rahmen markiert:
- 🟦 Personen
- 🟩 Tiere (Katze, Hund)
- 🟨 Fahrzeuge (Auto, Fahrrad)
- 🟪 Möbel/Objekte (Couch, Pflanze)

---

## Einstellungen

Öffnen Sie die Einstellungen über den **"Menue"**-Button. Es stehen 6 Tabs zur Verfügung:

### Allgemein

![Allgemein Tab](images/general_tab_screenshot_1770149392938.png)

Globale Einstellungen für die Benutzeroberfläche:

| Option | Beschreibung |
|--------|--------------|
| **Kiosk Modus** | Versteckt alle Steuerelemente für Display-Ansicht |
| **Animationen** | Aktiviert/deaktiviert UI-Animationen |
| **Footer anzeigen** | Zeigt/versteckt die Leistungsanzeige |

---

### Speicher

![Speicher Tab](images/storage_tab_screenshot_1770149407122.png)

Übersicht und Verwaltung des Speicherplatzes:

#### Statistiken
- **Aufnahmen gesamt** – Gesamtanzahl aller Aufnahmen
- **Geschätzte Größe** – Berechneter Speicherverbrauch in GB
- **Pro Kamera** – Aufschlüsselung nach Kamera

#### Aufräumen
Löschen Sie alte Aufnahmen nach Kriterien:

| Option | Beschreibung |
|--------|--------------|
| **Kamera** | Alle Kameras oder bestimmte auswählen |
| **Älter als** | Alter in Tagen (z.B. "älter als 7 Tage") |
| **Auch Analysen löschen** | Entfernt zugehörige Analyse-Daten |

> [!WARNING]
> **Gelöschte Aufnahmen können nicht wiederhergestellt werden!**

---

### Analyse

![Analyse Tab](images/analysis_tab_screenshot_1770149345176.png)

KI-Objekterkennung konfigurieren:

#### Objekte auswählen
Wählen Sie, welche Objekte erkannt werden sollen:

**Schnellprofile:**
- 👤 **Persons** – Nur Personen
- 🐾 **Animals** – Haustiere (Katze, Hund, Vogel)
- 🚗 **Vehicles** – Fahrzeuge (Auto, Fahrrad, Bus)
- 🏠 **Thema Zimmer** – Wohnraumobjekte

**Einzelne Objekte:**
- Person, Katze, Hund, Auto, Fahrrad, Bus, Motorrad
- Vogel, Pferd, Schaf, Kuh
- und mehr...

#### Hardware
Wählen Sie das Erkennungsgerät:
- **Coral USB** – Hardwarebeschleunigt (empfohlen)
- **CPU** – Software-Fallback

#### Aktuelle Aufnahme analysieren
- Checkbox: **Objekte im Video anzeigen**
- Button: **Analyse aktuelle Aufnahme** – Führt Analyse für das aktuelle Video durch

#### Alle Aufnahmen analysieren (Batch)
Analysieren Sie mehrere Aufnahmen auf einmal:

| Option | Beschreibung |
|--------|--------------|
| **Zeitraum** | Maximales Alter der zu analysierenden Videos |
| **Limit** | Maximale Anzahl der Videos |
| **Nur neue Dateien** | Überspringt bereits analysierte Videos |

---

### Personen

![Personen Tab](images/persons_tab_screenshot_1770149356233.png)

Verwalten Sie die Gesichtserkennung:

#### Personenliste
Zeigt alle bekannten Personen mit:
- **Name** – Bearbeitbar
- **Embeddings** – Anzahl der gespeicherten Gesichtsmerkmale
- **Vorschaubilder** – Thumbnails der erkannten Gesichter

#### Aktionen pro Person
| Icon | Aktion |
|------|--------|
| ✏️ | Name bearbeiten |
| 🗑️ | Person löschen |
| ➕ | Neue Gesichtsprobe hinzufügen |

#### Neue Person hinzufügen
Klicken Sie auf **"Hinzufügen"** um eine neue Person zur Datenbank hinzuzufügen.

> [!TIP]
> **Training-Tipp:** Für beste Erkennungsraten fügen Sie 5-10 Bilder pro Person hinzu – aus verschiedenen Winkeln und Lichtverhältnissen.

---

### Bewegung

Das Bewegungsprofil zeigt, wo und wann Personen erkannt wurden. Es gibt zwei Ansichten:

#### Diagramm-Ansicht

![Bewegungsprofil Diagramm](images/bewegung_diagramm.png)

Statistische Übersicht:

| Statistik | Bedeutung |
|-----------|-----------|
| **Gesamt** | Gesamtanzahl aller Erkennungen |
| **Personen** | Anzahl erkannter Personen |
| **Kameras** | Anzahl aktiver Kameras |
| **Aktive Std** | Stunden mit Aktivität |

**Erkennungen pro Person:** Farbige Balkendiagramme zeigen, wie oft jede Person erkannt wurde.

**Erkennungen pro Kamera:** Zeigt die Verteilung der Erkennungen auf die Kameras.

**Aktivität pro Person (24h):** Heatmap der Aktivität im Tagesverlauf.

#### Listen-Ansicht

![Bewegungsprofil Liste](images/bewegung_liste.png)

Chronologische Auflistung aller Erkennungen pro Person:

- **Personenname** – Gruppiert nach erkannter Person
- **Kamerastandort** – Wo die Person erkannt wurde
- **Zeitstempel** – Datum und Uhrzeit
- **Konfidenz** – Erkennungsgenauigkeit in %

#### Ansicht wechseln

| Button | Ansicht |
|--------|----------|
| **Diagramm** | Statistische Auswertung mit Balken und Heatmap |
| **Liste** | Chronologische Timeline pro Person |

---

### Leistung

![Leistung Tab](images/performance_tab_screenshot_1770149379171.png)

Echtzeit-Systemüberwachung:

#### Live System Monitor
| Metrik | Beschreibung |
|--------|--------------|
| **CPU-Auslastung** | Aktuelle Prozessorauslastung in % |
| **RAM-Auslastung** | Arbeitsspeichernutzung in % |

#### Objekt-Erkennung (Coral)
| Metrik | Beschreibung |
|--------|--------------|
| **Status** | Aktiv / Inaktiv |
| **Coral USB** | Erkannter EdgeTPU-Beschleuniger |
| **Coral Nutzung** | Anteil der Coral-Verwendung (0-100%) |
| **TPU-Last** | Aktuelle Hardware-Auslastung der TPU |
| **Inferenzzeit** | Durchschnittliche Erkennungszeit in ms |
| **Inferenzen gesamt** | Gesamtanzahl der durchgeführten Erkennungen |

#### TPU Test
Klicken Sie auf **"Eim Abstand testen"** um eine Testinferenz durchzuführen und die TPU-Reaktionsfähigkeit zu prüfen.

#### CPU-Verlauf
Ein Graph der letzten 60 Messungen zeigt den CPU-Verlauf.

---

## Konfiguration (Integration)

Die Integration wird über **Einstellungen → Geräte & Dienste → RTSP Recorder → Konfigurieren** eingerichtet.

### Globale Einstellungen

![Globale Einstellungen](images/einstellungen_global.png)

Grundkonfiguration des RTSP Recorders:

| Option | Beschreibung | Standardwert |
|--------|--------------|-------------|
| **Speicherpfad** | Verzeichnis für Aufnahmen | `/media/rtsp_recorder/ring_recordings` |
| **Thumbnail-Pfad** | Verzeichnis für Vorschaubilder | `/media/rtsp_recorder/thumbnails` |
| **Video-Aufbewahrung** | Tage bis zur automatischen Löschung | 7 Tage |
| **Thumbnail-Aufbewahrung** | Tage für Vorschaubilder | 7 Tage |
| **Aufräum-Intervall** | Häufigkeit der Bereinigung | 24 Std |

> [!NOTE]
> Wenn der Speicherpfad nicht freigegeben ist, fügen Sie folgendes zur `configuration.yaml` hinzu:
> ```yaml
> homeassistant:
>   allowlist_external_dirs:
>     - /media
> ```

---

### Kamera hinzufügen

![Kamera hinzufügen](images/kamera_hinzufuegen.png)

Fügen Sie RTSP-Kameras manuell hinzu, die nicht automatisch erkannt wurden:

| Feld | Beschreibung | Beispiel |
|------|--------------|----------|
| **Kamera-Name** | Eindeutiger Name | Garage, Einfahrt |
| **RTSP-URL** | Stream-URL der Kamera | `rtsp://user:pass@192.168.1.100:554/stream` |
| **Bewegungssensor** | Binary Sensor der die Aufnahme startet | `binary_sensor.motion_garage` |
| **Aufnahmedauer** | Länge der Aufnahme in Sekunden | 120 Sek |
| **Snapshot-Verzögerung** | Wartezeit vor Thumbnail-Erstellung | 0 Sek |
| **Eigene Aufbewahrung** | Überschreibt globale Einstellung (0 = global) | 0 Std |

> [!TIP]
> Aktivieren Sie **"Weitere Kamera hinzufügen"** um mehrere Kameras nacheinander einzurichten.

---

### Offline-Analyse Konfiguration

![Offline-Analyse](images/offline_analyse.png)

Konfigurieren Sie die KI-basierte Videoanalyse:

#### Grundeinstellungen

| Option | Beschreibung |
|--------|--------------|
| **Analyse aktiv** | Aktiviert die Offline-Analyse |
| **Hardware** | Coral USB (empfohlen) oder CPU |

#### Objektfilter

Wählen Sie die zu erkennenden Objekte aus:
- Person, Auto, Bett, Buch, Bus, Gastisch
- Fahrrad, Fernbedienung, Fernseher, Flasche, Hund
- Katze, Laptop, LKW, Koffer, Motorrad
- Handy, Tasse, Sofa, Stuhl, Rucksack, Vogel
- Regenschirm, Pflanze, Paket

#### Analyse-Parameter

| Option | Beschreibung | Empfohlen |
|--------|--------------|----------|
| **Analyse-Ordner** | Speicherort für Ergebnisse | `/media/rtsp_recorder/ring_recordings/_analysis` |
| **Frame-Intervall** | Sekunden zwischen Frames | 2 Sek |
| **Detektor URL** | Addresse des Detector-Addons | `http://local-rtsp-recorder-detector:5000` |
| **Erkennungs-Schwelle** | Minimum für Objekterkennung | 0.5 |
| **Gesichtserkennung aktiv** | Aktiviert Face Detection | ✅ |
| **Gesichts-Erkennungsschwelle** | Minimum für Gesichtserkennung | 0.2 |
| **Gesichts-Matching-Schwelle** | Schwellwert für Personenzuordnung | 0.35 |

#### Automatisierung

| Option | Beschreibung |
|--------|--------------|
| **Personen-Entitäten erstellen** | Erstellt Binary Sensors für erkannte Personen |
| **SQLite Datenbank nutzen** | Bessere Performance bei vielen Personen |
| **Automatik aktiv** | Analysiert nach Zeitplan |
| **Neue Videos sofort analysieren** | Analysiert nach dem Speichern |
| **Modus** | Täglich (Uhrzeit) oder Intervall |

---

## Performance-Anzeige

Die **Footer-Leiste** am unteren Rand zeigt Echtzeitdaten:

| Anzeige | Bedeutung | Farbcodes |
|---------|-----------|-----------|
| **CPU** | Prozessorauslastung | 🟢 <50% 🟠 50-80% 🔴 >80% |
| **RAM** | Arbeitsspeicher | 🟢 <70% 🟠 70-90% 🔴 >90% |
| **Coral** | TPU-Status | Aktiv/Inaktiv |
| **TPU %** | Coral-Last | 🟢 <5% 🟠 5-25% 🔴 >25% |
| **Inferenz** | Erkennungszeit | ms |

---

## Tipps & Best Practices

### Optimale Konfiguration

> [!TIP]
> **Für beste Performance:**
> - Verwenden Sie einen **Coral USB EdgeTPU** für hardwarebeschleunigte Erkennung
> - Setzen Sie das **Cleanup-Intervall** auf 1 Stunde bei kurzer Aufbewahrung
> - Nutzen Sie **Pro-Kamera-Retention** für unterschiedliche Aufbewahrungszeiten

### Gesichtserkennung verbessern

1. **Mehrere Proben sammeln** – 5-10 verschiedene Bilder pro Person
2. **Verschiedene Lichtverhältnisse** – Tag und Nacht
3. **Verschiedene Winkel** – Frontal und seitlich
4. **Negative Samples** – Fügen Sie falsch-positive Erkennungen als Negativ hinzu

### Speicherplatz sparen

1. **Kurze Aufbewahrung** – Setzen Sie `retention_days` auf 7-14 Tage
2. **Automatisches Cleanup** – Aktivieren Sie die automatische Bereinigung
3. **Gezielte Analyse** – Analysieren Sie nur relevante Aufnahmen

---

## Fehlerbehebung

### Häufige Probleme

| Problem | Lösung |
|---------|--------|
| **Coral wird nicht erkannt** | USB-Verbindung prüfen, Add-on neu starten |
| **Langsame Erkennung** | CPU-Fallback aktiv → Coral USB anschließen |
| **Keine Aufnahmen sichtbar** | Zeitfilter anpassen, Kamerafilter überprüfen |
| **Gesicht nicht erkannt** | Mehr Trainingsbilder hinzufügen |
| **Hohe CPU-Last** | Analyse-Batches kleiner halten, Intervall erhöhen |

### Logs prüfen

Überprüfen Sie die Home Assistant Logs unter:
**Einstellungen → System → Protokolle**

Filtern Sie nach `rtsp_recorder` für relevante Einträge.

### Support

Bei weiteren Problemen:
1. Prüfen Sie die [Troubleshooting-Dokumentation](TROUBLESHOOTING.md)
2. Öffnen Sie ein Issue im Repository

---

> **RTSP Recorder v1.1.1 BETA** – KI-gestützte Videoüberwachung für Home Assistant
