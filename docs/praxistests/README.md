# Tests und Testergebnisse

Chronologische Übersicht aller Tests von Biathlon Target Vision – von Labor- und
Simulationstests über Trainings bis zu Wettkämpfen. Aufgeführt werden nur nachweisbare
Ergebnisse; fehlgeschlagene Prüfungen und negative Befunde gehören ausdrücklich dazu.
Fehlende Angaben sind als „nicht dokumentiert“ gekennzeichnet.

**Status:** *geplant* = noch nicht durchgeführt · *durchgeführt* = Daten liegen vor,
Auswertung offen · *ausgewertet* = Ergebnisse dokumentiert.

| Kennung | Datum | Testart | Status |
|---|---|---|---|
| [T1](#t1--labor--und-simulationstests-und-inbetriebnahme) | 17.–20.10.2026 | Labor-/Simulationstests, Inbetriebnahme auf dem Testserver ohne Schießanlage | ausgewertet |
| [T2](#t2--praxistest-am-arber) | 21.10.2026 | Technischer Feldtest im Schießtraining | durchgeführt |

Wie BTV einen Test selbst dokumentiert (Feldprotokoll, Testdiagnose, automatisches
Testprotokoll), beschreibt [ARBER-TESTPROTOKOLL.md](../ARBER-TESTPROTOKOLL.md).

## T1 – Labor- und Simulationstests und Inbetriebnahme

**Datum:** 17.–20.10.2026 · **Status:** ausgewertet ·
**Issues:** [#13](https://github.com/richtertoralf/biathlon-target-vision/issues/13),
PR [#35](https://github.com/richtertoralf/biathlon-target-vision/pull/35)

**Ziel:** Funktion von Erfassung, Bedienablauf, Schnittstellen und optischer Erkennung
mit synthetischen Daten nachweisen; BTV auf dem Testserver installieren, reale
Kamerastreams anbinden und die Last vor dem Feldtest bestimmen.

**Hard- und Software:**

- Entwicklungsrechner AMD Ryzen 7 2700 (8 Kerne), Python 3.12, OpenCV 4.14; GitHub
  Actions (Ubuntu, Python 3.11, Chromium über Playwright).
- Testserver `mediamtx18`: Intel Core i5-11400T (6 Kerne/12 Threads), 16 GB RAM,
  Ubuntu 24.04, MediaMTX 1.21.2, BTV 0.8.0 bis 0.8.4.
- Vier IP-Kameras IPC_NT98566_N8S (4K, 16 mm) und eine 1080p-Kamera, über MediaMTX
  angebunden, ohne Blick auf eine Schießanlage.

**Durchgeführte Prüfungen und Ergebnisse:**

| Prüfung | Ergebnis | Nachweis |
|---|---|---|
| Automatisierte Tests: Ereigniskern, API, Sitzungen, Tablet-Ablauf, Kalibrierung, Erkennung, Installation/Upgrade (mit ersetztem systemd), Testdiagnose | Release 0.8.4: alle Python-Tests und zehn Browserprüfungen in CI bestanden. Erneuter Lauf am 20.10. auf `mediamtx18`: 158 von 159 bestanden; `test_unreadable_configuration_never_invents_addresses` scheitert dort, weil der laufende BTV-Dienst die vom Test erwartete freie Standardadresse belegt (Umgebung, kein Programmfehler) | [Entwicklungsbericht](../ENTWICKLUNGSBERICHT.md), [CI](https://github.com/richtertoralf/biathlon-target-vision/actions) |
| Kalibrierung mit synthetischen Bildern (288 Bilder, 1.440 Scheiben: 32 Zustandskombinationen, 3 Perspektiven, Skalierung, Beleuchtung, Unschärfe, Rauschen) | Alle Scheiben gefunden; Zentrumsfehler im Mittel 0,030 px (max. 0,076 px), Flächenüberdeckung im Mittel 0,919 (min. 0,875). Negativfälle (fehlende Scheiben, Leerbilder, mehrdeutige Reihen, große Bewegung) korrekt abgewiesen. Kalibrierung scheitert unter etwa 16 px Scheibendurchmesser | [Entwicklungsbericht 0.1](../ENTWICKLUNGSBERICHT.md#2026-10-17--version-01-ereigniskern-und-standbild-kalibrierung), [Roadmap](../ROADMAP.md#offene-technische-fragen-für-den-test) |
| Klassifikation „aufgerichtet/gefallen“ (192 synthetische Bilder: 32 Zustände, 3 Perspektiven, 2 Beleuchtungen, Rauschen) | Alle 192 Bilder je Scheibe richtig klassifiziert; Teilverdeckung ergibt „unbekannt“ statt eines falschen Zustands | [Entwicklungsbericht 0.5](../ENTWICKLUNGSBERICHT.md#2026-10-17--version-05-optische-zielzustände) |
| Laufende Erkennung in synthetischen Videofolgen (3 Bahnen, 2 Kameras, Verdeckung, Bildbewegung, Rückstellung, Kameraausfall) | Zustandswechsel nach drei Bildern bestätigt; einzelne Störbilder erzeugen keine Ereignisse; nach Ausfall nur Grundbeobachtungen, keine erfundenen Fälle; Journal-Replay unverändert | [Entwicklungsbericht 0.5](../ENTWICKLUNGSBERICHT.md#2026-10-17--version-05-optische-zielzustände) |
| Zeitmessung Bildwechsel → WebSocket, Entwicklungsrechner, 4 synthetische 1080p-Kameras | Median 0,5 s (4 Bahnen) bis 1,6 s (20 Bahnen); ein ungenutzter OpenCV-Threadpool kostete 1–2 Kerne | [Entwicklungsbericht](../ENTWICKLUNGSBERICHT.md#2026-10-19--zeitverhalten-der-optischen-erfassung-synthetische-messung) |
| Installation und Upgrades auf `mediamtx18` | Erstinstallation 0.8.0 am 19.10., Upgrades auf 0.8.1–0.8.4 bis 20.10.; jeder Start erfolgreich, Datensicherung je Upgrade angelegt | Dienstlog des Servers (nicht veröffentlicht) |
| Reale Kamerastreams über MediaMTX (20.10., ca. 6 h) | 4K-Streams nach Vereinheitlichung: H.264 3840×2160, 15 fps, Schlüsselbild alle 2 s, CBR 4,4–5,5 Mbit/s, Smart Codec und Ton aus, Uhrzeit per NTP. Kein Verbindungsabbruch; etwa stündlich je Kamera einzelne RTP-Paketverluste (kurze Bildfehler). Eine sechste Kamera war nie erreichbar | MediaMTX-Log (nicht veröffentlicht) |
| Last von BTV mit 5 Live-Streams ohne kalibrierte Bahn | ca. 480–500 % CPU eines Kerns (≈ 5 Kerne nur für die Dekodierung), 1,7 GB RAM | Prozessmessung, nicht archiviert |
| Zeitmessung auf `mediamtx18` unter dieser Live-Last, Standard und mit `OPENCV_FOR_THREADS_NUM=1` | Median 0,54 / 0,55 s (4 Bahnen) bis 1,27 / 1,29 s (20 Bahnen); Benchmark-CPU 122–214 % → 49–79 %. Daraufhin für den Dienst `OPENCV_FOR_THREADS_NUM=1` gesetzt | [Standard](T1-labor/benchmark-mediamtx18-standard.txt), [1 Thread](T1-labor/benchmark-mediamtx18-opencv-1-thread.txt) |
| Speicherbedarf der Aufzeichnung | 5 Streams ≈ 10,5 GB/h; bei Daueraufzeichnung mit 7 Tagen Aufbewahrung wäre der Datenträger nach etwa 14 h voll. Aufnahmen gelöscht, Kameras werden erst kurz vor einem Test eingeschaltet | Dateiliste (nicht veröffentlicht) |

**Grenzen der Simulation:** Die Erkennungsergebnisse gelten nur für den
Bildgenerator: idealisierte Scheiben mit dunkler Öffnung, heller Klappe und sichtbarem
Rand. Weiße Klappen ohne Rand, Sonne, Schatten, Gegenlicht, Reflexionen, Schnee,
Schrägsicht realer Anlagen, Personen im Bild und Mastschwingung sind nicht geprüft.
Es gibt daher **keine Aussage zur Erkennungsgüte an einer realen Anlage**. Die
Zeitmessungen verwenden 1080p-Testbilder; Kamera, Netz und RTSP-Dekodierung sind
darin nicht enthalten, der Einfluss echter 4K-Bilder ist nicht gemessen.

**Nicht geprüft:** physische Tablets, Stadion-WLAN, Safari, Bedienung mit Handschuhen,
physische Ende-zu-Ende-Latenz, Rechnerneustart mit automatischem Dienststart, Abspielen
der Aufzeichnungen, Deinstallation.

**Negative Befunde:**

| Befund | Einordnung |
|---|---|
| Statusanzeige am Tablet bis zu 5 s veraltet nach schnellem Statuswechsel (in CI gefunden) | Softwarefehler, behoben in PR #36 |
| Manuell erfasste Scheiben gingen bei erster nachträglicher Startnummer verloren | Softwarefehler, behoben ([#21](https://github.com/richtertoralf/biathlon-target-vision/issues/21)) |
| Tablet-Eingaben bei Verbindungsverlust gesperrt, keine Offline-Erfassung | Softwarefehler, offen ([#42](https://github.com/richtertoralf/biathlon-target-vision/issues/42), nach T2) |
| `test_unreadable_configuration_never_invents_addresses` scheitert auf `mediamtx18` | Testumgebung: Der laufende BTV-Dienst belegt die Adresse, die der Test als frei erwartet; der Test ist nicht vom Host isoliert. In CI bestanden |
| Einzelne RTP-Paketverluste etwa stündlich je 4K-Kamera | Ursache ungeklärt (Kamera, Netz oder MediaMTX) |
| Sechste Kamera nie erreichbar („no route to host“) | Testumgebung: Kamera nicht im Netz; nicht weiter untersucht |
| Datenträger wäre bei Daueraufzeichnung nach etwa 14 h voll | Testumgebung: MediaMTX-Aufbewahrung von 7 Tagen passt nicht zu 10,5 GB/h; kein BTV-Fehler |

## T2 – Praxistest am Arber

**Datum:** 21.10.2026, ab ca. 15:00 Uhr · **Status:** durchgeführt ·
**Issue:** [#13](https://github.com/richtertoralf/biathlon-target-vision/issues/13)

**Testart:** technischer Feldtest während eines etwa einstündigen Schießtrainings im
Hohenzollern-Skistadion am Arber, **keine Wettkampfsimulation**. Ohne Kampfrichter; ein
Tester bedient das Tablet gelegentlich selbst. Die Sportler schießen unregelmäßig.

**Ziele:** Kameraerkennung an realen mechanischen Klappscheiben bei Tageslicht,
Kalibrierung realer Bahnen, grundlegende manuelle Bedienung und Korrektur, Stabilität
von Kameraverbindungen und Server, Last mit realen Streams. Referenz für die spätere
Auswertung sind die Videoaufzeichnungen.

**Geplanter Aufbau:**

- Server `mediamtx18` mit BTV 0.8.4 (`OPENCV_FOR_THREADS_NUM=1`) und MediaMTX; MediaMTX
  zeichnet alle Kamerastreams unabhängig von BTV in 10-Minuten-Segmenten auf.
- Vier 4K-Kameras mit 16-mm-Objektiv und zwei Weitwinkelkameras; Bahnzuordnung und
  Kalibrierung erst vor Ort.
- Erfassung: BTV-Ereignisjournal, Testdiagnose (alle 5 s), Feldprotokoll und Notizen des
  Testers, MediaMTX- und Dienstlogs.

**Aufbau vor Ort (21.10.):**

- Kameras mit 16-mm-Objektiv etwa 20 m vor den Scheiben (nicht auf den Meter genau). cam81 erfasst die
  10-m-Bahnen 1–3 (je eine Platte liegend und stehend); im Bild sind außerdem die
  50-m-Scheiben sichtbar. Bei 3840×2160 liegen die Lochmitten etwa 41 px auseinander;
  der erkannte Lochumriss ist 13–14 px breit.
- BTV 0.8.5 mit den Kalibrierkorrekturen vom 21.10. (Branch `fix/calibration-upload`,
  siehe [Entwicklungsbericht](../ENTWICKLUNGSBERICHT.md)) statt 0.8.4.
- Kalibriert wird je Bahn eine Platte im zurückgestellten Zustand (alle Löcher
  schwarz); geprüft wird nur die Erkennung schwarz/weiß.
- Wetter: leichter Regen, bedeckter Himmel. Die 50-m-Scheiben sind beleuchtet, die
  10-m-Scheiben nicht und dadurch etwas dunkler; gegen 17:35 Uhr schon sichtbar
  geringerer Kontrast an den 10-m-Platten.

**Erkenntnisse vor Ort (21.10.):**

- Fest montierte Bullet-Kameras müssen vor Ort ausgerichtet werden. PTZ-Kameras wären
  praktischer, weil Ausrichtung und Zoom aus der Ferne möglich sind.
- Alternative: Kameras direkt an der Schusslinie unterhalb des Sportlers, nur 10 m
  vor den Scheiben. Rechnerisch verdoppelt das bei gleichem Objektiv den
  Abbildungsmaßstab (Lochabstand etwa 82 statt 41 px); eine Kamera erfasst dann aber nur
  etwa halb so viele Bahnen.

**Beobachtungen zur Erkennung vor Ort (21.10., vorläufig, nicht gegen das Video
geprüft):**

- Kalibriert: Bahn 2 und 3, jeweils Liegend-Platte. Bahn 1 am rechten Bildrand nicht
  kalibrierbar (Farbsäume und Verzerrung des Objektivs; je ein Loch knapp über der
  Formgrenze).
- „Aufgerichtet“: nach dem Zurückstellen 14 von 15 Scheiben erkannt. Ausnahme Bahn 2
  Scheibe 3: Helligkeit eindeutig dunkel (Verhältnis 0,20), aber Streuung im
  Innenbereich 49 bei Grenze 46. Bei etwa 13 px Lochdurchmesser reicht der
  Messbereich schon bei 1–2 px Versatz an den hellen Rand.
- „Gefallen“: meist nicht erkannt, sondern „unbekannt“. Die Nachführung findet weiße
  Klappen nicht und verlangt mindestens drei wiedergefundene Scheiben einschließlich
  1 und 5. Die Helligkeit an den kalibrierten Positionen war dagegen korrekt
  (Bahn 2: weiß 0,97–1,05, schwarz 0,11).
- Verdeckung (vermutlich eine Person vor Bahn 3): korrekt „unbekannt“. Eine Messung
  ohne Nachführung hätte hier für vier Scheiben fälschlich „gefallen“ ergeben
  (Verhältnis 0,87–1,16).
- Schießeinlage 18:08 ohne Bediener (Tester: Bahn 2 fünf Treffer, Bahn 3 ein Fehler).
  Aufzeichnung alle 3 s für eine Minute. Helligkeit an den kalibrierten Positionen:
  Bahn 2 Treffer von links nach rechts bis `FFFFF`, Bahn 3 bis `SFFFF` (Fehler auf
  Scheibe 1) – stimmt mit Tester und Kamerabild überein. BTV meldete während der
  Einlage auf Bahn 2 durchgehend und auf Bahn 3 ab dem dritten Treffer alle Ziele
  „unbekannt“, nach dem Zurückstellen wieder „aufgerichtet“ (Bahn 2 Scheibe 3
  zeitweise „unbekannt“). Beim Zurückstellen war die Platte von Bahn 3 kurz verdeckt.
- Schießeinlage 18:13 (Tester: Bahn 2 fünf Treffer, Bahn 3 drei Fehler): Helligkeit
  an den Positionen Bahn 2 `FFFFF`, Bahn 3 `SSSFF` – übereinstimmend. BTV wieder
  „unbekannt“ während der Einlage, danach „aufgerichtet“ (Bahn 2 Scheibe 3 zeitweise
  „unbekannt“). Um 18:13:32 verdeckte eine Person beim Zurückstellen Bahn 3; die
  Messung an den Positionen ergab dabei fälschlich `FFFFF`, BTV korrekt „unbekannt“.
- cam83 (etwa 16 m vor den Scheiben, nicht auf den Meter genau) ab 18:20 für Bahn 4 und 5, jeweils Liegend-Platte
  kalibriert, gleiches 16-mm-Objektiv. Lochabstand 51 px (cam81 bei etwa 20 m: 41 px,
  passt ungefähr zum Abstandsverhältnis 20/16). Der erkannte Lochumriss ist mit etwa 23 px
  deutlich breiter als bei cam81 (13–14 px), vermutlich weil diese Platten einen
  dunklen Rand um die Löcher haben (nicht geprüft).
  Schießeinlage 18:21 (Tester: Bahn 5 alles getroffen): Helligkeit an den Positionen
  `FFFFF`, BTV „unbekannt“, nach dem Zurückstellen „aufgerichtet“. Bahn 4 (nicht
  beschossen, alle Löcher schwarz) zeitweise ganz „unbekannt“: Scheibe 5 wurde in
  einzelnen Bildern nicht wiedergefunden, und ohne äußere Scheibe verwirft die
  Nachführung die ganze Bahn.
- Bahn 1: Das weiße Seil des Aufzugs der Stehend-Platte verdeckt laut Tester
  Scheibe 2 der Liegend-Platte. In den Kamerabildern von cam81 (18:00–18:15) ist es
  vor Scheibe 2 nicht zu erkennen.

**Zusammenfassung (Testende 21.10., vor der Videoauswertung):**

Der Feldtest war positiv: Er hat unter realen Bedingungen gezeigt, was funktioniert,
und die Schwachstellen so eindeutig eingegrenzt, dass die nächsten Schritte klar sind.

Bestätigt:

- Server, Kamerastreams und Weboberfläche liefen ohne Ausfall; Neustarts gab es nur
  geplant für die Korrekturen. Zwei 4K-Kameras (cam81, cam83) waren angebunden.
- Kalibrierung realer Bahnen nach Korrekturen vor Ort (Uploadfehler im Dienst,
  Uploadgrenze, Formprüfung kleiner Löcher, Anzeige der Scheibenbereiche): Bahn 2, 3,
  4 und 5 kalibriert, die Bereiche lagen jeweils genau auf den Löchern.
- Die Schwarz/Weiß-Unterscheidung an den kalibrierten Positionen stimmte in allen
  beobachteten Schießeinlagen mit den Angaben des Testers überein (Bahn 2 zweimal
  fünf Treffer, Bahn 3 ein und drei Fehler, Bahn 5 fünf Treffer).
- „Aufgerichtet“ wurde nach dem Zurückstellen weitgehend zuverlässig erkannt.
- Verdeckungen durch Personen führten korrekt zu „unbekannt“; es entstanden keine
  erfundenen Treffer.

Erkannte Schwachstellen und Konsequenzen:

- Die Nachführung findet weiße Klappen nicht wieder. BTV meldet getroffene Scheiben
  deshalb meist als „unbekannt“ statt „gefallen“. Nächster Schritt: Nachführung an
  Merkmalen ausrichten, die sich beim Treffer nicht ändern (z. B. Plattenkanten),
  Verdeckung weiter erkennen.
- Einzelne nicht wiedergefundene Scheiben (Bahn 4 Scheibe 5) oder eine knapp
  überschrittene Streuungsgrenze (Bahn 2 Scheibe 3) setzen Scheiben oder ganze Bahnen
  auf „unbekannt“.
- Bei etwa 20 m und 16 mm Brennweite sind die Löcher sehr klein im Bild; am Bildrand
  (Bahn 1) verhindern Farbsäume die Kalibrierung. Größerer Abbildungsmaßstab (kürzerer
  Abstand, PTZ-Kameras) ist der wirksamste Hebel.
- Pro Bahn gibt es Liegend- und Stehend-Platte; BTV kennt bisher nur eine. Vorschlag:
  Umschaltung am Tablet durch den Bediener (noch zu prüfen).

**Ergebnisse:** Abgleich mit den Videoaufzeichnungen steht aus; Erkennungsquoten werden
erst danach angegeben.

## Eigene Tests beitragen

Andere Anwender sind eingeladen, ihre Tests und Erfahrungen beizusteuern – als
[GitHub-Issue](https://github.com/richtertoralf/biathlon-target-vision/issues) oder per
Pull Request, auf Deutsch, Englisch oder Tschechisch. Einen neuen Eintrag mit der
nächsten Kennung in die Übersicht und einen Abschnitt mit Datum, Testart, Ziel, Hard-
und Software, durchgeführten Prüfungen, Ergebnissen und Grenzen sowie Nachweisen
ergänzen. Belegdateien wie das BTV-Testprotokoll (`testprotokoll-*.md`) in einen Ordner
`T<Nummer>-<ort>/` legen. Erkennungsquoten nur angeben, wenn sie gegen eine unabhängige
Referenz (zum Beispiel das Video) geprüft wurden.

Nicht in das Repository gehören:

- **Videoaufzeichnungen:** zu groß für Git; bei Bedarf extern ablegen und verlinken.
- **Aufnahmen oder Bilder mit erkennbaren Personen** ohne deren Einverständnis.
- **`config.json`, Kamera-Zugangsdaten und vollständige RTSP-Adressen.**
