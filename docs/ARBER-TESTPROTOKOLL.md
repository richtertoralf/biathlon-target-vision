# Testprotokoll für den Praxistest am Arber

Praxistest am **21.10.2026 ab 15:00 Uhr** im Hohenzollern-Skistadion am Arber
([Issue #13](https://github.com/richtertoralf/biathlon-target-vision/issues/13)).
Diese Datei beschreibt, was BTV ab Version `0.8.4` automatisch dokumentiert, was
vor Ort von Hand festgehalten werden muss und wie beides ausgewertet wird.
Testplan und offene technische Fragen stehen in der [Roadmap](ROADMAP.md).

**Leitprinzip:** BTV erfasst automatisch, was es bereits weiß. Von Hand wird nur
protokolliert, was eine unabhängige Beobachtung oder Messung vor Ort erfordert.

## Testaufbau

- Server `mediamtx18` mit BTV als systemd-Dienst auf Port 8091 und MediaMTX als
  eigenständigem Dienst. MediaMTX stellt die Kamerastreams bereit und zeichnet sie
  unabhängig von BTV auf.
- Ein bis sechs IP-Kameras, je Kamera eine bis fünf Schießbahnen. BTV liest die
  Streams über MediaMTX.
- Tablets und Kontrollmonitor im getrennten, vertrauenswürdigen Netz.

## Ablauf am Testtag

Alle Schritte liegen unter `/admin#sessions` im Bereich
**„Praxistest: Protokolle und Testdiagnose“**:

1. **Sitzung benennen**, etwa „Arber Praxistest 21.10.“, oder dafür eine neue
   Sitzung beginnen.
2. **„Feldprotokoll (PDF) herunterladen“** und ausdrucken. Das Formular ist mit
   Sitzung, Version, Kameras, Bahnen, Bildauflösung und Kalibrierungsstand
   vorausgefüllt.
3. **„Testdiagnose starten“** vor Beginn der Messdurchgänge.
4. Optional kurze Angaben vor Ort eintragen: Kameraabstände, Wetter, Licht,
   Beobachtungen und, falls nicht automatisch erkannt, das MediaMTX-Aufzeichnungsverzeichnis.
5. Testdurchgänge gemäß Roadmap durchführen und das Feldprotokoll von Hand führen.
6. **„Testdiagnose beenden“** nach dem letzten Durchgang.
7. **„Testprotokoll erstellen“**. Die Markdown-Datei wird heruntergeladen und
   bleibt in der Sitzung gespeichert. Über **„Messwerte (JSON)“** lassen sich alle
   Messungen für die Nachauswertung laden.

Ein Testprotokoll kann jederzeit erneut erstellt werden, auch für abgeschlossene
Sitzungen (Liste „Abgeschlossene Sitzungen“). Es ist immer eine neue Datei.

## Automatisch erfasste Daten

**Bei Diagnosebeginn (einmalig):** BTV-Version und Commit, Betriebssystem,
Kernel, Python-Version, CPU-Modell und Kernanzahl, Arbeitsspeicher, Datenträger,
Netzwerkadressen, Serverzeit und Zeitzone.

**Etwa alle fünf Sekunden** (nur während der Testdiagnose):

| Bereich | Messgrößen |
|---|---|
| BTV-Prozess | CPU in Prozent eines Kerns (einschließlich RTSP-Dekodierung), RAM (RSS), Threadanzahl |
| System | CPU aller Kerne, verfügbarer RAM, Last, freier Speicher im Datenordner |
| Zustand | Gesundheitsstatus, ob die Erkennungsaufgabe läuft |
| Je Kamera | verbunden ja/nein, Verbindungszähler des Decoders, dekodierte Bildnummer, tatsächliche Bildauflösung, Empfangszeit des letzten Bildes |
| Je Bahn | Erfassungsstatus „Automatik aktiv“, „unsicher“ oder „nicht verfügbar“ |
| Verarbeitung | Dauer jeder Bildauswertung je Bahn, Dauer jedes Erkennungsdurchlaufs und Abstand zwischen Durchläufen |

**Nur aus vorhandenen Quellen ausgewertet** (keine zusätzliche Speicherung):

- *Ereignisjournal der Sitzung:* Belegungen, Freigaben, Startnummern und
  Korrekturen, manuelle Scheibenkorrekturen mit Kamera-Vergleichswert,
  automatische Beobachtungen und Grundbeobachtungen, Rückstellungen,
  Zeitstempel und Reihenfolge. Es bleibt die maßgebliche Quelle und wird nicht
  kopiert oder verändert.
- *Weitere Quellen:* Korrekturbelege unter `corrections/`, Kamera- und
  Bahnkonfiguration (Adressen ohne Zugangsdaten), gespeicherte Kalibrierungen mit
  Bildgröße, Scheibendurchmesser und Scheibenabstand in Pixeln.
- *MediaMTX-Aufzeichnungen:* Dateiname, Größe und Änderungszeit je Kamera. Die
  Zuordnung erfolgt über den Pfad der Kamera-URL; Dateien werden nur aufgelistet,
  nie geöffnet oder verändert. Das Verzeichnis stammt aus absoluten `recordPath`
  in `/usr/local/etc/mediamtx.yml`, `/etc/mediamtx/mediamtx.yml` oder
  `/etc/mediamtx.yml`, sonst aus der Angabe in der Testdiagnose. Der BTV-Dienst
  muss es lesen dürfen; `/home` ist für ihn durch systemd gesperrt.

## Von Hand zu erfassen: Feldprotokoll

Das PDF (DIN A4, schwarz-weiß, Seitenzahlen und Sitzungsname auf jeder Seite)
enthält:

- *Übersicht:* Ort, Protokollführung, Beteiligte, Testzeiten, Tablets, Netzwerk,
  Stromversorgung; dazu die Kameraliste laut BTV.
- *Je Kamera ein Blatt:* Hersteller und Modell, Objektiv und Brennweite,
  Zoomstellung, Montagehöhe, Aufstellungsposition, Betrachtungswinkel. Je Bahn:
  Abstand Kamera–Scheiben, Scheibengröße, Scheibe im Bild laut BTV,
  Kalibrierungsstand. Platz für Besonderheiten des Kamerabildes.
- *Wetter und Licht:* mehrere Beobachtungen mit Uhrzeit, Temperatur, Himmel,
  Niederschlag, Wind, Sicht, Gegenlicht, Schatten und Lichtwechsel.
- *Referenzbeobachtungen (zwei Seiten):* je Zeile Uhrzeit oder Videozeit,
  Kamera, Bahn, tatsächliche Stellung der fünf Scheiben (A, G oder ?), die
  BTV-Anzeige zum Vergleich, Abweichung und Bemerkung. Die tatsächliche Stellung
  ist die unabhängige Referenz; Treffer oder Schüsse werden nicht abgeleitet.
- *Bedienbarkeit und Auffälligkeiten:* Ablesbarkeit, Handschuhe, Touch,
  WLAN-Unterbrechungen, Verzögerungen, Fehleingaben, Kameraausfälle,
  Vorschläge der Kampfrichter.

Die Erzeugung verändert keine Wettkampfdaten und ist während einer laufenden
Sitzung möglich.

## Testprotokoll (automatisch)

Gliederung des Markdown-Berichts:

1. Sitzung
2. BTV-Version
3. Server und Betriebssystem
4. Kameraübersicht
5. Kamera-/Bahnzuordnung
6. Kalibrierungen und Bildgeometrie
7. Zeitraum der Diagnoseaufzeichnung
8. Systemleistung
9. Kameraverfügbarkeit und Ausfälle
10. Erkennungsleistung und Verarbeitungszeiten
11. Ereignisjournal
12. Manuelle Korrekturen
13. Aufzeichnungsdateien
14. Nicht verfügbare Messwerte
15. Testfälle aus #13 mit belegbaren Daten
16. Offene Fragen und Probleme
17. Zusammenfassung

Statistiken (Minimum, Median, 95. Perzentil, Maximum, Anzahl) werden nur aus
tatsächlich gespeicherten Messungen berechnet. Fehlende Werte heißen „nicht
gemessen“. Der Bericht bewertet keinen Testfall als bestanden; Abschnitt 15 nennt
nur, was die Daten belegen.

## Auswertung nach dem Test

1. Feldprotokoll und Testprotokoll zusammenführen.
2. Referenzbeobachtungen mit dem Journal (`/api/events?session_id=…`,
   `observed_at`, `accepted_at`) und den MediaMTX-Videos vergleichen.
3. Latenz über die Zeiteinblendung der Kamera im Video gegen `accepted_at`
   bestimmen (siehe Roadmap).
4. Befunde, Grenzen und nach Schwere priorisierte Fehler im
   [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md) dokumentieren und #13 aktualisieren.

## Speicherort, Neustart und Grenzen

- **Ablage:** `sessions/<Sitzungs-ID>/diagnostics/` im Datenordner, bei der
  systemd-Installation `/var/lib/biathlon-target-vision/`. Dort liegen
  `state.json` (Läufe mit Beginn, Ende, Grund, Neustarts und Systemangaben),
  `samples.jsonl` (eine Zeile pro Messung, sofort mit `fsync` geschrieben),
  `notes.json` und die erzeugten `testprotokoll-*.md`.
- **Neustart:** Eine laufende Testdiagnose wird nach einem Neustart von BTV
  automatisch fortgesetzt; der Neustart erscheint im Bericht. Beim Abschluss
  einer Sitzung wird sie beendet; die Daten bleiben in der alten Sitzung.
- **Fehler:** Schreibfehler halten nur die Diagnose an und werden angezeigt.
  Tablet-Bedienung, Journal und Erkennung laufen weiter.
- **Aufwand:** Gemessen mit 20 synthetischen Bahnen auf vier Kameras etwa 2 ms
  pro Messung alle fünf Sekunden; kein messbarer Unterschied der Prozess-CPU.
  Rund 3,4 KB pro Messung, das sind etwa 2,5 MB pro Stunde.
- **Genauigkeit:**
  - *Messzeitpunkte:* Die Messungen sind Stichproben alle fünf Sekunden.
    Kürzere Kameraausfälle zeigen sich nur über den Verbindungszähler.
  - *Verarbeitungszeiten:* Sie umfassen die Bildauswertung in BTV einschließlich
    Thread-Übergabe, nicht die physische Ende-zu-Ende-Latenz.
  - *Prozess-CPU:* Sie enthält die RTSP-Dekodierung und den OpenCV-Threadpool.
  - *Kalibrierungen und Kamerazuordnung:* Sie entsprechen dem Stand bei
    Berichtserstellung, nicht historisiert (#15).
