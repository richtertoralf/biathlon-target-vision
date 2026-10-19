# Roadmap

Stand: **19. Oktober 2026**, Release `v0.8.3` (Development Release, `main` nach
PR #43): 14 offene und drei abgeschlossene Issues. Die Prioritäten und Reihenfolgen sind Empfehlungen; sie
ändern weder die GitHub-Issues noch den implementierten Umfang. Die fachliche
Zielbeschreibung steht im [Produktkonzept](PRODUKTKONZEPT.md), der tatsächliche
Entwicklungsstand im [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md). BTV ist in
aktiver Entwicklung und nicht für produktiven Wettkampfbetrieb freigegeben.

## Entwicklungsstand vor dem ersten Praxistest

| Bereich | Stand | Nachweis und Grenze |
|---|---|---|
| Bahnablauf, BIB, mehrere Tablets, Monitor, Sitzungen | implementiert, automatisiert getestet | 142 Python-Tests und neun Browserprüfungen, CI grün; keine physischen Tablets, kein Stadion-WLAN |
| Optische Erkennung: Kalibrierung, Nachführung, Klassifikation, Stabilisierung, Status je Bahn | implementiert, nur synthetisch getestet | Generierte Scheibenbilder mit dunkler Öffnung, heller Klappe und sichtbarem Rand; keine reale Aufnahme |
| RTSP-Eingang | implementiert, lokal getestet | Nur MediaMTX/FFmpeg-Teststream mit einem Schlüsselbild je Sekunde; keine reale IP-Kamera |
| Mehrere Bahnen je Kamera | implementiert, synthetisch getestet | Je Bahn eine eigene ROI und Kalibrierung mit genau einer Fünferreihe |
| Installation als systemd-Dienst | implementiert, isoliert getestet | systemd in Tests ersetzt; noch keine reale Installation auf einem Zielrechner |
| Korrekturausschnitte | implementiert | Einzelbilder bei manueller Korrektur; BTV zeichnet kein Video auf |
| Journalansicht/Export, Zuordnungsprotokoll, Zugriffsschutz, Sprachumschaltung außerhalb des Tablets | geplant | #14, #15, #24/#25, #28 |
| Schießposition, Juryvorfälle, Schussbeobachtung, Video-Geometrie-API, Sensorik | geplant oder Konzept | #16, #17, #18/#19, #26; Sensorik ohne Issue |

Es gibt keine bestätigte Praxistauglichkeit oder Herstellerintegration.

## Meilenstein: Praxistest am 21. Oktober 2026

**Mittwoch, 21.10.2026, ab 15:00 Uhr, Hohenzollern-Skistadion am Arber
([#13](https://github.com/richtertoralf/biathlon-target-vision/issues/13)).**
Schwerpunkt ist die praktische Zuverlässigkeit der optischen Erkennung an
mechanischen Klappscheiben mit vier IP-Kameras, perspektivisch zwei bis vier
Bahnen je Kamera. Bis zum Test werden keine Funktionen ergänzt; Programmänderungen
nur, wenn sie Installation oder Testdurchführung tatsächlich blockieren.

**Testaufbau:** Server `mediamtx18` (Intel Core i5-11400T, 6 Kerne/12 Threads,
16 GB RAM, Ubuntu 24.04, 206 GB frei). MediaMTX läuft dort bereits als systemd-Dienst,
hält die Kameraverbindungen dauerhaft und zeichnet unabhängig von BTV auf. BTV läuft
als eigener systemd-Dienst auf demselben Rechner und liest die Kamerastreams über
MediaMTX (`rtsp://127.0.0.1:8554/PFAD`), nicht direkt von den Kameras. Damit bleibt
es bei einer Verbindung je Kamera, und BTV wertet denselben Stream aus, der
aufgezeichnet wird. MediaMTX wird nicht umgebaut.

### Vorbereitung bis Dienstag, 20.10.

1. **Softwarestand festlegen:** Auf `mediamtx18` mit
   `sudo biathlon-target-vision --upgrade` auf `v0.8.3` wechseln (überarbeitete
   Administration, ausführliches `--status`, einheitlicher Seitenrahmen mit
   Betriebsuhr). Danach die Kameras unter `/admin` anlegen.
   `sudo biathlon-target-vision --status` meldet Version `0.8.3`; den Commit des Tags im
   Testprotokoll festhalten. `--upgrade` wechselt nur auf einen höheren Versionstag;
   weitere Korrekturen vor dem Test deshalb nur als neuer Patch-Tag.
2. **Bahnanzahl vor dem ersten Dienststart klären:** Der Installer startet den
   Dienst ohne `--lanes`, also mit 20 Bahnen; die Zahl ist danach je Datenordner
   fest. Sollen physische Bahnnummern über 20 verwendet werden, `--lanes N` per
   systemd-Drop-in (`systemctl edit`) ergänzen und den Datenordner bis auf
   `config.json` leeren, bevor Testdaten entstehen. BTV-Bahnnummern entsprechen
   den physischen Bahnnummern.
3. **Erste reale Installation prüfen:** Dienststart, `biathlon-target-vision
   --status`, `/api/health`, Zugriff von Tablet und Monitor, Rechnerneustart mit
   automatischem Start von MediaMTX und BTV. Port 8091 kollidiert nicht mit den
   MediaMTX-Standardports.
4. **Kamerastreams erfassen:** Die vier verwendeten MediaMTX-Pfade unter `/admin`
   eintragen. Je Kamera Auflösung, Codec, Bildrate, Bitrate und
   Schlüsselbildabstand notieren. Geprüft ist bisher nur ein Teststream mit einem
   Schlüsselbild je Sekunde bei zwei Sekunden Öffnungs-/Lesezeitlimit; sehr lange
   Schlüsselbildabstände oder „Smart Codec“-Modi vorab ausprobieren.
5. **Zeitbezug herstellen:** Serverzeit per NTP synchronisieren (`timedatectl`),
   Kamerazeit auf denselben Zeitserver stellen und die Zeiteinblendung (OSD)
   aktivieren. Das ist die Grundlage der Latenzmessung.
6. **Unabhängige Aufzeichnung prüfen:** Aufzeichnungspfade, Speicherdauer
   (`recordDeleteAfter`, in MediaMTX standardmäßig 24 Stunden) und Platzbedarf
   kontrollieren und je Pfad eine kurze Aufnahme abspielen. Überschlag: sechs Pfade
   mit je 4 Mbit/s benötigen rund 11 GB pro Stunde.
7. **Messung vorbereiten:** CPU und RAM mit Betriebssystemmitteln protokollieren,
   etwa `pidstat -h -u -r -t -C 'python|mediamtx' 10` (Paket `sysstat`) in eine
   Datei. Vorab die Grundlast von MediaMTX allein messen und die synthetische
   Zeitmessung auf `mediamtx18` wiederholen, mit und ohne `OPENCV_FOR_THREADS_NUM=1`:
   `cd /opt/biathlon-target-vision/current && .venv/bin/python -m tests.benchmark_vision`.
8. **Testprotokoll vorbereiten:** Ab `v0.8.4` unter `/admin#sessions` das
   vorausgefüllte Feldprotokoll (PDF) drucken, die Testdiagnose starten und nach
   dem Test das automatische Testprotokoll erstellen; siehe
   [ARBER-TESTPROTOKOLL.md](ARBER-TESTPROTOKOLL.md). Von Hand bleiben
   Referenzstellungen, Kameraaufbau, Wetter, Licht und Bedienbarkeit.
9. **Netz:** Tablets, Monitor und Server in einem getrennten, vertrauenswürdigen
   Netz betreiben. BTV hat noch keine Anmeldung (#24); das ist für den
   beaufsichtigten Entwicklungstest kein Blocker.

### Testprogramm am 21.10.

In dieser Reihenfolge, damit bei Zeitmangel die Kernfragen beantwortet sind:

1. **Geometrie und Kalibrierung:** Je Kamera Abstand, Blickwinkel, Zoom,
   Auflösung und Zahl der Bahnen im Bild festhalten; Scheibendurchmesser und
   Scheibenabstand in Pixeln aus der Kalibrierung (`/api/lanes/N/calibration`)
   ablesen. Je Bahn Erfolg, Fehlermeldung und Zahl der Versuche notieren. Nach
   Möglichkeit eine, zwei, drei und vier Bahnen je Kamera vergleichen.
2. **Erkennungsgüte:** Serien mit null bis fünf gefallenen Scheiben und
   Rückstellung je Bahn. Auswertung je Scheibe und Zustandswechsel: richtig,
   falsch, unbekannt, verpasster Fall, Falschfall, Rückstellung bestätigt oder
   nicht. Zusätzlich den Anteil „Automatik aktiv“ gegenüber „Erkennung läuft /
   unsicher“ beobachten.
3. **Licht, Wetter, Verdeckung:** Wechsel von Sonne, Schatten und Gegenlicht über
   den Nachmittag, Nässe oder Schnee, Personen oder Gewehre im Bild,
   Kameraschwingung. Nicht aufgetretene Bedingungen ausdrücklich als ungetestet
   vermerken.
4. **Latenz:** Zeit zwischen Scheibenfall und Anzeige. Erster Videoframe mit
   gefallener Scheibe (OSD-Zeit in der MediaMTX-Aufzeichnung) gegen `accepted_at`
   des Journalereignisses; `observed_at` trennt den BTV-internen Anteil. Erwartet
   werden mindestens drei Bilder und 250 ms Stabilisierung zuzüglich Encoder-,
   Netz- und Auswertungsverzögerung.
5. **Last:** CPU und RAM mit einer, zwei und vier Kameras sowie steigender
   Bahnzahl, während MediaMTX aufzeichnet.
6. **Ausfälle und Korrekturen:** Kamera oder Pfad trennen und wiederverbinden
   (Grundbeobachtung ohne rückwirkende Fälle), manuelle Korrekturen während
   laufender Erkennung, zwei Tablets, BTV-Neustart mit Replay, Serververbindung
   eines Tablets unterbrechen.
7. **Nebenbei:** Rückmeldungen zu Bedienbegriffen (#20) sowie Bedienbarkeit bei
   Sonnenlicht und mit Handschuhen notieren.

### Sicherung und Auswertung

- `/var/lib/biathlon-target-vision` vollständig sichern (Journale, Korrekturbilder,
  Kalibrierungen, `config.json`). `config.json` kann RTSP-Zugangsdaten enthalten
  und gehört nicht in geteilte Berichte.
- MediaMTX-Aufzeichnungen des Testzeitraums vor der automatischen Löschung sichern,
  ebenso Last-Protokolle, Testprotokoll und Fotos des Aufbaus.
- Journal über `/api/events` oder direkt aus der JSONL-Datei gegen Protokoll und
  Video vergleichen. Befunde, Grenzen und nach Schwere priorisierte Fehler im
  Entwicklungsbericht dokumentieren. Testerfolg und offene Probleme trennen.
- Aufnahmen mit erkennbaren Personen nicht ohne Einverständnis veröffentlichen.

## Offene technische Fragen für den Test

- **Mindestgröße:** Die Kalibrierung verlangt eine ROI von mindestens 100 × 24 px
  je Bahn. Synthetisch scheiterte sie unterhalb von etwa 16 px Scheibendurchmesser,
  bei idealen Kanten. Die reale Mindestgröße ist ein Testergebnis.
- **Bildmerkmale der Anlage:** Die Klassifikation erwartet eine dunkle Öffnung bei
  aufgerichteter und eine helle Klappe bei gefallener Scheibe. Die Kalibrierung
  braucht fünf sichtbar begrenzte Konturen; weiße Klappen ohne Rand können
  abgewiesen werden.
- **Mehrere Bahnen je Kamera:** Jede ROI darf nur eine Fünferreihe enthalten.
  Die zulässige Nachführung ist auf 24 px und 20 % des Scheibenabstands begrenzt;
  kleine Scheiben reagieren deshalb empfindlicher auf Mastbewegung.
- **Rechenzeit und Latenz:** BTV dekodiert jeden Stream vollständig in Software
  und wertet alle Bahnen nacheinander aus, mit einer Pause von 100 ms je
  vollständigem Durchlauf. Eine synthetische Messung auf einem Entwicklungsrechner
  ergab von Bildwechsel bis WebSocket im Median 0,5 s bei 4 Bahnen und 1,6 s bei
  20 Bahnen; die Stabilisierung dauert praktisch zwei Durchläufe. Kamera, Netz und
  RTSP kommen hinzu. Ein ungenutzter OpenCV-Threadpool kostete ein bis zwei Kerne.
  Details und Messskript stehen im
  [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md) (PR #35). Die Rechenzeit wächst
  zusätzlich mit der Zahl ellipsenähnlicher Konturen in der ROI.
- **Kompatibilität der Streams:** Codec, Auflösung und Schlüsselbildabstand der
  realen Kameras über MediaMTX sind ungeprüft.

## Nach dem Praxistest

Die Reihenfolge richtet sich nach den gemessenen Fehlern, nicht nach dem
Issue-Bestand.

1. **#13 auswerten und dokumentieren.** Aufnahmen ohne Programmänderung
   wiederholbar auswerten: eine Aufzeichnung mit `ffmpeg -re -i DATEI -c copy -f rtsp`
   an einen dafür freigegebenen MediaMTX-Pfad senden und eine getrennte
   BTV-Instanz mit eigenem Datenordner und Port daran kalibrieren. Kurze,
   annotierte reale Bildfolgen können danach als Testmaterial dienen, sofern
   Rechte und Einverständnis geklärt sind.
2. **Erkennungsfehler zuerst beheben**, belegt durch diese realen Aufnahmen.
   Schwellwerte nur mit realen Belegen ändern; einfache OpenCV-Verfahren vor
   trainierten Modellen.
3. **Latenz und Last nur bei Messbefund verbessern**, etwa bei ausgelastetem
   Auswertungsthread; keine Vorabarchitektur.
4. **Einrichtung vereinfachen:** #22 mit den Erfahrungen aus den Kalibrierungen,
   #23 danach. Getrennte PRs.
5. **Vor dem ersten Einsatz mit fremden Bedienern oder offenem Netz:** #24 und #25
   in einem PR.
6. **#28** vor einem Einsatz mit tschechischer Jury oder Administration;
   Ergebnisse aus #20 in die Beschriftungen übernehmen.
7. **#14**, im Umfang an den tatsächlich benötigten Auswertungen des Tests
   ausgerichtet; danach #15.
8. **P2/P3 nur bei konkretem Bedarf:** #16, #26, #17, dann #18 + #19.

## Priorisierte offene Issues

| Priorität | Issue | Kleinster sinnvoller nächster Schritt |
|---|---|---|
| **P0** | [#13 – Praxistest Arber](https://github.com/richtertoralf/biathlon-target-vision/issues/13) | Am 21.10. durchführen, sichern, auswerten, Fehler priorisieren. |
| **P1** | [#22 – ROI-Markierung](https://github.com/richtertoralf/biathlon-target-vision/issues/22) | Nach dem Test. Bis dahin nennen Kalibrierungsseite und Fehlermeldung die Eckpunktreihenfolge. |
| **P1** | [#23 – Kameraeingaben vereinfachen](https://github.com/richtertoralf/biathlon-target-vision/issues/23) | Teilweise in `v0.8.1` umgesetzt (Klartexteingabe, bereinigte Anzeige der gespeicherten Adresse, Kennung aus dem Namen). Nach #24 vollständige RTSP-Adresse administrativ anzeigen. |
| **P1** | [#24 – Zugriffsschutz](https://github.com/richtertoralf/biathlon-target-vision/issues/24) | Vor erstem Einsatz außerhalb eines vertrauenswürdigen Netzes; zwei gemeinsame Passwörter, REST und WebSocket serverseitig schützen. |
| **P1** | [#25 – Navigation und öffentlicher Lesezugriff](https://github.com/richtertoralf/biathlon-target-vision/issues/25) | Mit #24 öffentliche Lesewege und Navigation gemeinsam prüfen. |
| **P1** | [#28 – Alle Seiten dreisprachig](https://github.com/richtertoralf/biathlon-target-vision/issues/28) | Nach dem Test; bestehende `translations.js` für Monitor, Administration und Kalibrierung nutzen. |
| **P1** | [#20 – Bedienbegriffe abstimmen](https://github.com/richtertoralf/biathlon-target-vision/issues/20) | Beim Test Rückmeldungen sammeln; bis dahin Beschriftungen unverändert. |
| **P1** | [#14 – Journalansicht und Export](https://github.com/richtertoralf/biathlon-target-vision/issues/14) | Nach der Testauswertung; Filter und Export an tatsächlich benötigten Auswertungen ausrichten. |
| **P1** | [#15 – Kamera-/Bahnzuordnung dokumentieren](https://github.com/richtertoralf/biathlon-target-vision/issues/15) | Nach #14. Für den Test genügt das Testprotokoll. |
| **P2** | [#16 – Schießposition je Einlage](https://github.com/richtertoralf/biathlon-target-vision/issues/16) | Bei konkretem Bedarf, etwa für eine Liveproduktion. |
| **P2** | [#26 – Video-Geometrie-API](https://github.com/richtertoralf/biathlon-target-vision/issues/26) | Zugriffskonflikt mit #24 klären; dann vorhandene Kalibrierungsgeometrie bereitstellen. |
| **P2** | [#17 – Juryvorfälle](https://github.com/richtertoralf/biathlon-target-vision/issues/17) | Erst Bedienkonzept und Trennung von Meldung und Bewertung klären. |
| **P3** | [#18 – Schussbeobachtung](https://github.com/richtertoralf/biathlon-target-vision/issues/18) | Eingabeweg praktisch erproben, danach getrennt von Zielzuständen erfassen. |
| **P3** | [#19 – Staffel-Reservepatronen](https://github.com/richtertoralf/biathlon-target-vision/issues/19) | Auf #18 aufbauend; nichts aus Schussnummer oder Scheiben ableiten. |

**Echte technische Abhängigkeiten:** #19 benötigt #18. Die vollständige
RTSP-Adresse aus #23 und #26 darf erst nach #24 angezeigt werden, weil sie
Zugangsdaten enthalten kann; die Vereinfachung von Kennung und Name in #23 ist
davon unabhängig. #14 bietet Darstellung und Export für #15, #17 und #18, ist aber
keine Voraussetzung für deren Ereignisspeicherung. #22, #28 und #16 sind unabhängig.
Alle übrigen Reihenfolgen sind Empfehlungen, keine technischen Blockaden.

## Offene Entscheidungen und Leitplanken

- **#26 versus #24:** #26 fordert die vollständige RTSP-URL ohne Anmeldung; sie
  kann Benutzername und Passwort enthalten. Empfehlung: öffentliche Geometrie ohne
  Zugangsdaten, vollständige URL nur administrativ. Wo MediaMTX vorhanden ist,
  genügt für externe Anwendungen dessen Pfad.
- **Umfang begrenzen:** #17 und #18/#19 bringen eigene Ereignisarten,
  Korrekturwege und Bedienkonzepte mit. Erst umsetzen, wenn ein konkreter
  Arbeitsablauf belegt ist; keine Statusführung, Rollen oder Adapter auf Vorrat.
- **Sitzungsbezug:** Journalansicht, Zuordnungsprotokoll, Positionen und
  Juryvorfälle beziehen sich eindeutig auf eine Sitzung. Externe Cursor verwenden
  `(session_id, sequence)` gemäß [API](API.md). Archive bleiben schreibgeschützt.
- **Ereignisarchitektur erhalten:** Beobachtung, wirksamer Scheibenzustand und
  manuelle Korrektur bleiben getrennt. Zielzustände erzeugen keine Schuss- oder
  Fehlschussereignisse; Juryvorfälle sind Meldungen, keine Entscheidungen.
- **Entwicklungsphase:** Keine Migrationen früherer Entwicklungsversionen. Daten
  nicht stillschweigend löschen, Formatänderungen dokumentieren, Replay
  deterministisch halten. Vorhandenen Ereigniskern, JSONL-Journal und
  Browserarchitektur nutzen; keine neuen Dienste oder Datenbanken.

## Bereits abgeschlossen

- [#21 – Nachträgliche BIB-Eingabe](https://github.com/richtertoralf/biathlon-target-vision/issues/21): Scheibenzustände bleiben erhalten (PR #27).
- [#29 – Aufzeichnungssitzungen](https://github.com/richtertoralf/biathlon-target-vision/issues/29): Sitzung abschließen und neu starten, Archive erhalten (PR #31).
- [#30 – Erfassungsstatus am Tablet](https://github.com/richtertoralf/biathlon-target-vision/issues/30): Status je Bahn und manuelle Korrekturen sichtbar (PR #32).
