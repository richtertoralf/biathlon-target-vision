# Entwicklungsbericht

Chronologischer Entwicklungsverlauf mit Entscheidungen und damaligen
Testergebnissen. Maßgeblich für den aktuellen Stand von Version 0.6 sind
[ARCHITECTURE.md](ARCHITECTURE.md) und [API.md](API.md).
Die folgende redaktionelle Konsolidierung übernimmt vorhandene Testergebnisse;
sie ist kein erneuter Testlauf.

## 2026-10-17 – Version 0.1: Ereigniskern und Standbild-Kalibrierung

### Ausgangslage und Entscheidungen

Zu Beginn enthielt das Repository Konzept, Architektur und Abbildungen, aber
keinen Programmcode. Umgesetzt wurden der Ereigniskern und die zusätzlich
beauftragte Kalibrierung einzelner Bilder. Die vollständige Tablet-Bedienung
war damals noch offen und wurde anschließend in Version 0.2 ergänzt.

Ein FastAPI-/Uvicorn-Prozess, lokale JSONL-Speicherung und die Standardbibliothek
für Tests hielten den Kern einfach; OpenCV und NumPy kamen ausschließlich für
die Kalibrierung hinzu. Die Entscheidungen waren:

- Akzeptierte Befehle dauerhaft speichern, bevor ein neuer Zustand veröffentlicht
  wird; Wiederherstellung mit derselben Zustandslogik. Ein Dateilock verhindert
  mehrere schreibende Serverprozesse. Schreibfehler stoppen weitere Änderungen,
  beschädigte Journale werden nicht automatisch gekürzt. Das vermeidet stille
  Datenlöschung und ermöglicht eine nachvollziehbare manuelle Reparatur.
- Einlagenkennung, beobachtete Ziele und Belegung trennen. Rückstellung und
  Freigabe erfüllen unterschiedliche Aufgaben; eine verspätete Freigabe darf
  die nächste Einlage nicht dem vorherigen Sportler zuordnen. Frühere
  unzugeordnete Einlagen und Korrekturen benötigen eine ausdrückliche Auswahl.
- Simulator und künftige Erfassungsadapter verwenden denselben Beobachtungseingang.
  Veraltete Beobachtungen und widersprüchliche Ereigniswiederholungen werden
  abgewiesen. Es werden keine Schuss- oder Fehlschussmeldungen erfunden.
- Vollständige WebSocket-Zustände statt einer clientseitigen Ereignisrekonstruktion;
  das Journal bleibt separat abrufbar, langsame Browser blockieren die Erfassung nicht.
- Die letzte bekannte mechanische Stellung trotz `unknown` behalten:
  `fallen → unknown → standing` beendet die Einlage,
  `fallen → unknown → fallen` erfindet keinen neuen Übergang.

### Kalibrierungsreferenz und Erkenntnisse

Als Referenz wurden [README](https://github.com/richtertoralf/gameclock-vision/blob/main/README.md),
[autofit.py](https://github.com/richtertoralf/gameclock-vision/blob/main/tafeluhr/autofit.py)
und [alignment.py](https://github.com/richtertoralf/gameclock-vision/blob/main/tafeluhr/alignment.py)
von gameclock-vision gelesen. Übernommen wurden die Konzepte einer manuell
markierten Gesamt-ROI, perspektivischer Entzerrung, automatischer Geometrieprüfung,
sichtbarer Kontrollbereiche und begrenzter Nachführung relativ zur Grundkalibrierung.
Es wurde kein Code und keine Siebensegmentlogik übernommen.

Die erste Canny-Kantensuche zeigte in dunklen, kleinen synthetischen Bildern
unterbrochene Konturen. Sie wurde durch geglättete adaptive Schwellwertbildung
ersetzt. Ellipsenform, Winkelabdeckung, vergleichbare Größe, gemeinsame Linie
und regelmäßige Abstände werden gemeinsam geprüft. Eine zweite plausible
Fünferreihe wird abgewiesen; die Geometrie ergänzt keine unsichtbaren Ziele.

Fünf sichtbar abgrenzbare runde oder elliptische Konturen sind erforderlich.
Weiße Klappen ohne sichtbaren Rand können daher eine bewusste Ablehnung ergeben.
Die erneute Erkennung zur Nachführung wird immer mit der gespeicherten Basis
verglichen, damit sie nicht schrittweise auf ein Nachbarziel wandert. Andere
Zielzustände sind zulässig, solange die äußeren Konturen erkennbar bleiben.
Die separate Standbildansicht blieb deutsch; sie öffnet keine Videoquellen.

### Damals ausgeführte Prüfungen

Am 17.10.2026 mit Python 3.12.3:

- **38 Python-Tests erfolgreich**, einschließlich realem Uvicorn-Prozess,
  Simulator über HTTP, WebSocket-Nachrichten und Serverneustart mit identischem
  Zustand. Geprüft wurden normale Belegung, fünf unabhängige Ziele, späte
  Zuordnung vor/nach Rückstellung, Korrektur, alte Freigabe bei neuer Einlage,
  konkurrierende Startnummernvergabe, Wiederholungen, alte Beobachtungen,
  Verdeckung, Schreibfehler, beschädigtes Journal und exklusive Dateisperre.
  Kalibrierungstests prüften außerdem beschädigte Dateien und den Erhalt einer
  bestehenden Kalibrierung bei Schreibfehlern.
- **288 synthetische Bilder / 1.440 Ziele**: alle 32 Zustandskombinationen,
  drei Perspektiven und je drei Kombinationen aus Skalierung und Beleuchtung,
  zusätzlich Helligkeitsverlauf, Unschärfe und deterministisches Rauschen.
  Zentrumsfehler im Originalbild: Mittel **0,030 px**, Maximum **0,076 px**.
  Flächenüberdeckung (Intersection over Union): Mittel **0,919**, Minimum **0,875**.
  Testgrenzen: maximal 2,5 px Zentrumsfehler und mindestens 0,78 Flächenüberdeckung.
- Negative Bildtests prüften fehlende/unsichtbare Ziele, Leerbilder, Rauschen,
  Rechtecke, mehrdeutige Reihen, ungültige ROIs, große Bewegung und andere Auflösung.
- `tests/browser_smoke.cjs` mit Playwright/Chromium erfolgreich: Standbild laden,
  vier Gesamt-ROI-Ecken anklicken, fünf Polygone anzeigen, speichern und wieder
  laden, Nachführung mit anderen Zielzuständen sowie verständlicher Fehler bei
  fehlendem Ziel unter Erhalt der vorherigen Kalibrierung.
  Kontrollbild: `.test-artifacts/calibration-browser.png` (nicht versioniert).
- `pip check` und JavaScript-Syntaxprüfung erfolgreich. API-/Netzwerktests mussten
  wegen der damaligen Socketbeschränkung außerhalb der Ausführungssandbox laufen.

## 2026-10-17 – Version 0.2: Erste Tablet-Bedienung und Simulation

### Umsetzung und damalige Entscheidungen

Die Startseite wurde zum Tablet-Bedienplatz mit Bahnbelegung, Startnummer,
aktueller Einlage und fünf Zielstellungen einschließlich Form-/Textkennzeichnung.
Flexible Spalten, mindestens 48 Pixel hohe Hauptschaltflächen, ein eigenes
Zahlentastenfeld und eine beim Scrollen sichtbare Verbindungsanzeige unterstützten
Hoch- und Querformat. Zuordnung, Korrektur, Freigabe und historische Einlagen
verwendeten die vorhandenen Befehle.

Bahnauswahl und Sprache wurden je Browser/Origin gespeichert; auch eine leere
Auswahl war zulässig. Die beauftragten Sprachen EN als Standard sowie DE/CS
wurden zentral in `translations.js` hinterlegt. Die Kalibrierungsansicht blieb
deutsch. Eine ausdrückliche Serveroption `--simulation` aktivierte simulierte
Zielbedienung und Rückstellungen am vorhandenen Beobachtungseingang. Der zusätzliche
Header `X-Lane-Revision` schützte manuelle Simulation vor veralteten Zielständen.

WebSocket-Lebenszeichen und Wiederverbindung wurden ergänzt. Bei unklarer
HTTP-Bestätigung wurde der Serverzustand neu übernommen, ohne den Befehl
automatisch zu wiederholen. Ältere HTTP-Antworten durften neuere
WebSocket-Zustände nicht zurücksetzen.

**Überholt und im folgenden Entwicklungsschritt ersetzt:** Um zunächst Kern und
Modelle unverändert zu lassen, sperrte dieser Zwischenstand offene Dialoge bei
jeder Bahnrevision und bei einer Verbindungsunterbrechung. Dadurch konnte schon
ein weiterer Treffer ein Schließen und Neuöffnen verlangen. Diese Regel gilt
nicht für die abgeschlossene Version 0.2. Der CLI-Simulator blieb auch bei der
anschließenden Korrektur unverändert.

### Damals ausgeführte Prüfungen

- **41 Python-Tests erfolgreich**, einschließlich der bisherigen Kern-,
  Kalibrierungs- und echten Server-/Simulatorprüfungen. Neu geprüft wurden der
  standardmäßig deaktivierte Simulator, aktivierte Simulation mit Revisionsprüfung
  und idempotenter Wiederholung sowie WebSocket-Lebenszeichen ohne Journaländerung.
- `tests/tablet_browser.cjs` mit Playwright/Chromium erfolgreich: zwei unabhängige
  Browserprofile, 20 Bahnen, lokale Auswahl mit Neuladen und leere Auswahl, alle
  drei Sprachen mit vollständigen Übersetzungsschlüsseln und Platzhaltern.
  Geprüft wurden Zahlentastenfeld, Korrektur, Freigabe, drei Zielzustände, Treffer
  vor Startnummer, aufeinanderfolgende Einlagen, alte Freigabe bei neuer Einlage,
  historische Korrektur, doppelte Startnummer und konkurrierende Eingabe.
  Hinzu kamen Netzwerkunterbrechung bei offener Eingabe, Übernahme einer
  zwischenzeitlich geänderten Startnummer, verlorene HTTP-Bestätigung nach
  gespeicherter Änderung, Hoch-/Querformat und deaktivierte Simulation im Wettkampfmodus.
- Die Kalibrierungs-Browserprüfung, JavaScript-Syntaxprüfung und `git diff --check`
  waren erfolgreich. Kontrollbilder lagen unversioniert unter
  `.test-artifacts/tablet-landscape.png` und `.test-artifacts/tablet-portrait.png`.

## 2026-10-17 – Version 0.2: Korrektur der Mehrbenutzerbedienung

### Praktische Entscheidung

Die Bindung jeder Startnummerneingabe an die volle Bahnrevision war für den
Wettkampfbetrieb ungeeignet: Weitere Treffer während einer verspäteten Eingabe
sind normal. Sie dürfen nicht mit konkurrierenden Belegungsänderungen gleichgesetzt
werden. Für die Zusammenarbeit wurden vier Möglichkeiten abgewogen:

| Möglichkeit | Bewertung |
|---|---|
| Nur bestätigte Nummern zeigen | Parallele Erfassung wird zu spät bemerkt. |
| Ein gemeinsames überschreibbares Eingabefeld | Eingaben vermischen sich; bei Touch-Bedienung und WLAN-Verzögerung schlecht nachvollziehbar. |
| Bahn beim Öffnen reservieren | Ein liegen gebliebenes Tablet oder Funkloch behindert andere Kampfrichter; zusätzliche Freigabeverwaltung wäre nötig. |
| Getrennte sichtbare Entwürfe, ausdrückliche Bestätigung | Gewählt: unabhängige Bedienung mit gegenseitiger Sichtbarkeit, ohne Reservierung. |

Die verbindungsbezogene Tablet-Nummer macht gleichzeitige Eingaben unterscheidbar,
ohne eine nicht vorhandene Personenidentifikation vorzutäuschen. Es wurden keine
Anmeldung, Sitzungsdatenbank oder Besitzerwechsel eingeführt. Die lokale Auswahl
bleibt unabhängig; fremde Entwürfe erzeugen keine zusätzlichen Bahnkarten.

### Änderungen und Begründungen

- Ein zusätzlicher Belegungszähler trennt bestätigte Zuordnungen/Freigaben von
  Zielbeobachtungen. Die atomare Prüfung im Kern schützt auch während des
  HTTP-Transports, ohne Treffer als Belegungskonflikte zu behandeln.
- Die feste Revisionsbindung des Startnummerndialogs und das erzwungene Neuöffnen
  entfielen. Die Oberfläche vergleicht die betroffene Einlage, offizielle Nummer
  und Belegung. Unabhängige historische Korrekturen und übereinstimmende Nummern
  sind im offenen Eingabedialog kein Widerspruch. Bei einem Revisionsrennen lädt
  sie den Zustand neu und prüft den tatsächlichen Konflikt; kein Befehl wird
  automatisch erneut gesendet.
- Bei einer anderen Zuordnung oder betroffenen Freigabe bleiben Text und
  Zahlentastenfeld nutzbar. „Aktuellen Zustand prüfen“ aktualisiert nur die
  Vergleichsgrundlage; anschließend muss ausdrücklich bestätigt werden.
  Das verleiht keinen Vorrang gegenüber weiteren Bedienern.
- Auch Freigaben nutzen den Belegungszähler; die Historienauswahl wird erneuert.
  Manuelle Zielsimulation behält ihren Schutz durch die volle Bahnrevision,
  weil dort der Zielzustand selbst Gegenstand der Änderung ist.
- Offline bleibt die offene Startnummer bearbeitbar, aber nicht bestätigbar.
  Wiederverbindung übernimmt den Serverzustand und gleicht ihn mit der Eingabe
  ab. Ohne Belegungskonflikt ist keine erneute Prüfung nötig.
- Einlagenbezüge bleiben über Rückstellungen hinweg fest. Ohne bekannte Einlage
  beim Öffnen gilt die erste danach begonnene Einlage, auch bei Beobachtungen
  während HTTP-Transport oder Unterbrechung. Damit wechselt der Text nicht
  stillschweigend zum nächsten Sportler. Der abgeschlossene Status wird angezeigt;
  eine nachträgliche Zuordnung belegt keine neue Einlage. Bereits vorher vorhandene
  unzugeordnete abgeschlossene Einlagen benötigen weiterhin eine ausdrückliche Auswahl.
- Entwürfe bleiben außerhalb von Kern und Journal. Zeitbegrenzte Erneuerung
  entfernt überholte Anzeigen bei stillen WLAN-Ausfällen, ohne Locks einzuführen.
  Fokuswechsel innerhalb des Zahlentastenfelds bleibt Bearbeitung; Verlassen oder
  Verbindungsende bestätigt niemals eine Nummer. WebSocket-Zustände werden beim
  Senden gemeinsam mit den Entwürfen frisch aufgebaut, damit deren Änderungen
  keine offizielle Buchung aus einer zusammengefassten Nachricht verdrängen.
- Neue Befehlsfelder sind optional. Alte Journale bleiben ohne Migration lesbar;
  Zähler und Einlagenbeginn entstehen beim Wiederabspielen. Normalisierte
  Standardwerte erhalten die Idempotenz älterer Ereignisse.

Es gab und gibt keine serverseitigen Bahnsperren. Der Dateilock schützt allein
gegen mehrere schreibende Serverprozesse. Aktuelle Felder, Zeitgrenzen und
Integrationsregeln sind zentral in [API.md](API.md) dokumentiert.

### Damals ausgeführte Prüfungen

- **49 Python-Tests erfolgreich.** Zusätzlich geprüft: mehrere Treffer während
  eines vorbereiteten Zuordnungsbefehls; Rückstellung und nächste Einlage vor
  dessen Verarbeitung; konkurrierende Bestätigungen; Freigabe nach Treffern und
  Rückstellung mit Replay; alte Journalfelder; getrennte WebSocket-Entwürfe
  einschließlich Schutz gegen vorgegebene Absendernummern; Ablauf veralteter
  Entwürfe und Ablehnung ungültiger Entwürfe ohne Journaländerung.
- Erweiterter Tablet-Browsertest mit zwei unabhängigen Profilen erfolgreich:
  überlappende Bahnauswahl, gegenseitig sichtbare verschiedene Eingaben und
  eindeutige Tablet-Nummern; unveränderte Belegung und Sequenz während der Eingabe;
  gleiche Nummer ohne Konflikt und andere Nummer mit erhaltenem Text und Prüfung
  im selben Dialog. Drei Treffer während der Eingabe sowie ein weiterer während
  des HTTP-Transports wurden derselben Einlage zugeordnet und erfolgreich bestätigt.
  Rückstellung plus nächste Einlage lenkten den Text nicht um. Ebenfalls geprüft:
  Freigabe einer unzugeordneten Einlage, Fokusverlust, Schließen des Entwurfs,
  Freigabedialog während Zielbeobachtung, Offline-Weiterbearbeiten,
  Wiederverbindung mit/ohne Belegungsänderung und verlorene HTTP-Bestätigung.
  Alle bisherigen Sprach-, Auswahl-, Simulations- und Formatprüfungen blieben enthalten.
- Kalibrierungs-Browsertest und die 288 synthetischen Bilder / 1.440 Ziele weiterhin
  erfolgreich, mit unveränderten Fehler- und IoU-Werten aus Version 0.1.
- `pip check`, JavaScript-Syntaxprüfungen und `git diff --check` erfolgreich.
  Playwright wurde extern bereitgestellt; es wurden keine zusätzlichen
  Laufzeitabhängigkeiten oder Frontend-Werkzeuge eingeführt.

## Bekannte Einschränkungen des aktuellen Stands

- Die synthetischen Bilder verwenden idealisierte Öffnungen und Klappen mit
  sichtbarem Rand. Die kleinen Positionsfehler belegen nur diesen Generator.
  Reale Aufnahmen bei Sonne, Schatten, Schrägsicht, Verdeckung und Kameravibration
  müssen unabhängig annotiert und geprüft werden. Besonders relevant sind weiße
  Klappen ohne Rand und Rückstellungen über mehrere Bilder. Unklare Bilder sollen
  sichtbar fehlschlagen. Laufende Videoauswertung wurde mit Version 0.5 ergänzt; reale Aufnahmen fehlen weiterhin.
- Ohne Freigabe oder erkennbare Rückstellung kann aus Zielzuständen kein
  Sportlerwechsel abgeleitet werden. Zeitliche Stabilisierung und
  Quellenzuständigkeit gehören später in die Kamera-/Sensoradapter.
- Geprüft wurden zwei Chromium-Profile mit Touch-Unterstützung und
  Tablet-Auflösungen, keine physischen Tablets bei Sonnenlicht oder mit Handschuhen,
  kein Safari und kein Langzeitlasttest mit 20 Geräten. `dialog`, WebSockets und
  moderne Browser-APIs werden benötigt.
- Die Anwendung hat keine Anmeldung. Der Bahnfilter ist keine Zugriffsbeschränkung,
  die Simulator-Deaktivierung keine Authentifizierung von Kameras. Die Tablet-Nummer
  ändert sich nach Wiederverbindung; mehrere Tabs sind getrennte Bedienplätze.
- Offene Texte überleben eine Netzunterbrechung, aber kein Neuladen oder Schließen
  der Seite. Es gibt keine Offline-Befehlswarteschlange. Fremde Entwürfe können
  bei einem stillen Funkloch bis zum Ablauf verzögert verschwinden.
- Journal und Einlagen liegen zusätzlich zur Datei vollständig im Arbeitsspeicher;
  automatische Archivierung, Speicherbegrenzung und Prüfung der Netzlast bei
  wachsender Historie fehlen. Die systemd-Installation wurde mit Version 0.3 ergänzt; die KES-Ausgabe wurde verworfen.

## Prüfungen nachvollziehen

Die folgenden Aufrufe dienen zum Wiederholen der Prüfungen, nicht als Nachweis
einer erneuten Ausführung bei dieser Dokumentationsbereinigung.
Nach der Installation aus der [README](../README.md):

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tests.synthetic
```

Der letzte Aufruf erzeugt `.test-artifacts/calibration.png` für die manuelle
Standbildansicht. Vier Ecken um den gesamten hellen Scheibenbereich markieren.
Die Tests nutzen temporäre Datenordner; der Servertest startet einen echten
lokalen Server mit Simulator, WebSockets und Neustart.

Optionale Browserprüfungen benötigen Node.js, `@playwright/test` und installiertes
Chromium. Eine externe Playwright-Installation lässt sich über `PLAYWRIGHT_MODULE`
angeben:

```bash
node tests/tablet_browser.cjs
node tests/browser_smoke.cjs
```

## 2026-10-17 – Vollständigen Stand 0.2 sichern

Anwendung, statische Browserdateien, Tests und Abhängigkeitslisten werden erstmals
vollständig versioniert. Virtuelle Umgebung, Laufzeitdaten, Testartefakte und
lokale Codex-Sitzungsprotokolle bleiben ausgeschlossen. GitHub Actions führt die
Python-Tests mit Python 3.11 aus.

Erneut geprüft: 49 Python-Tests, Tablet-Browsertest mit zwei Profilen und drei
Sprachen, Kalibrierungs-Browsertest sowie `pip check` erfolgreich. Die Netz- und
Browserprüfungen liefen wegen der Socketbeschränkung außerhalb der Sandbox.


## 2026-10-17 – Version 0.3: Installation und Kontrollmonitor

Verbindliche Architekturkorrektur: BTV ist eine Zielzustandsquelle, keine
KES-Quelle. Die ursprünglich geplante KES-Ausgabe ist überholt und entfällt.
Version 0.6 stabilisiert REST/WebSocket und deren Integration. In gfx-engine wurde
nur Issue #102 angelegt; KES-/HORA-Code bleibt unberührt. Der geprüfte GFX-Stand
führt HORA noch als nicht verfügbaren Platzhalter.

Installation verwendet Git-Archiv, venv, systemd und einen festen Dienstbenutzer.
Programmstände werden vor dem kurzen Dienststopp vorbereitet; API-Prüfung mit
Versionsnummer und Rückschalten des Programmlinks ermöglichen einen einfachen
Rollback. Persistente Daten bleiben außerhalb des Programms. Kein eigener
Paketmanager, keine automatische Datenmigration oder Archivbereinigung.

Der schreibgeschützte Monitor verwendet die vorhandenen WebSocket-Zustände.
Eindeutige beobachtete Zielpositionen je Einlage werden beim Journal-Replay
rekonstruiert. Alte gefallene Ziele zählen nicht in eine neu zugeordnete Einlage.

Prüfungen: 57 Python-Tests erfolgreich, einschließlich Git-Archiv ohne unversionierte
Dateien, Rechte des Programmstands, Konfigurationsrechte, erfolgreicher Umschaltung,
Startfehler-/Sicherungsfehler-Rollback und Datenerhalt. Neuer Monitor-Browsertest und
bestehender Tablet-Browsertest erfolgreich. Shell-/JavaScript-Syntax und
`git diff --check` erfolgreich. Keine Installation in das laufende Hostsystem:
systemd-Aufrufe sind in den Installationstests isoliert ersetzt. Die Unit wurde
mit systemd-analyze gelesen; die erwartete Meldung zum noch nicht installierten
ExecStart-Pfad ersetzt keinen realen Debian-/Ubuntu-Installationstest.

Die CI auf Python 3.11 zeigte anschließend ein Abbruchrennen beim parallelen
WebSocket-Verbindungsabbau. Die Bereinigung sammelt eigene Tasks nun in einem
abgeschirmten AnyIO-CancelScope ein (AnyIO ist bereits FastAPI-Abhängigkeit).
Ein zusätzlicher Test wiederholt 30 parallele Verbindungszyklen. Alle 14 API-Tests
sind lokal erfolgreich; die CI wird vor dem Merge erneut vollständig ausgeführt.


## 2026-10-17 – Version 0.4: RTSP-Kameraverwaltung

Je Kamera ein OpenCV-/FFmpeg-Thread und ein aktuelles Bild halten die Architektur
bei einem Python-Prozess. Vorschau und spätere Auswertung teilen den Decoder.
Serverkonfiguration bleibt JSON im persistenten Datenordner. Bahnzuordnung wird
auf Eindeutigkeit geprüft, native Logs und Validierungsdetails mit möglichen
Zugangsdaten werden unterdrückt; der allgemeine Verbindungsstatus bleibt sichtbar.

Die bestehende Gesamt-ROI-Kalibrierung erhielt einen Kamerabild-Knopf und Links
für ausgewählte Bahnen. Kamerakennung/URL-Hash verhindern die stillschweigende
Weiterverwendung nach Quellenwechsel. Keine Einzelzielmarkierung, kein separates
Frontend oder zusätzlicher Dienst im Produkt. Für lokale Integrationstests sind
MediaMTX und FFmpeg ausschließlich externe Testwerkzeuge.

Prüfungen: vollständige Suite mit 64 Python-Tests erfolgreich; anschließend sieben
gezielte Kameratests mit zusätzlicher Wiederverbindung und Prüfung nativer Logs
auf Zugangsdaten erfolgreich (insgesamt jetzt 65 Tests). Lokaler MediaMTX-/FFmpeg-
Stream wurde tatsächlich dekodiert; Ausfall und Wiederverbindung sowie eine
parallel nicht erreichbare Kamera wurden geprüft. Der synthetische Stream liefert
jede Sekunde ein Schlüsselbild, damit der Verbindungsaufbau innerhalb des
Lesezeitlimits möglich ist. Bestehender Kalibrierungs-Browsertest und neuer
Kamera-Browsertest mit realem RTSP-Transport erfolgreich. Syntax-/Diff-Prüfung
fehlerfrei. In CI wird der optionale RTSP-Test ohne externe Testwerkzeuge explizit
übersprungen; keine realen Kameras oder Schießstandaufnahmen getestet.


## 2026-10-17 – Version 0.5: Optische Zielzustände

Die automatische Auswertung verwendet vorhandene Konturen, feste Grundkalibrierung
und lokale Helligkeitsverhältnisse. Drei Bilder über mindestens 250 ms bestätigen
Änderungen. Ein Zusatz zur Nachführung erlaubt Teilverdeckung im Inneren einer
Reihe; beide Endkonturen müssen sichtbar bleiben, damit eine große Verschiebung
nicht als Nachbarzielreihe akzeptiert wird. Fehlende Endanker ergeben konservativ
eine vollständig unbekannte Reihe.

Ein konkretes fehlendes API-Merkmal war die Unterscheidung zwischen neu
beobachtetem Fall und erstem sichtbaren Zustand nach einem Ausfall. Optionales
`baseline` ergänzt dafür die bestehenden Beobachtungen, ohne neues Protokoll oder
zusätzlichen Ereigniseingang. Grundbeobachtungen ändern weder Einlagengrenzen noch
die Zahl beobachteter Fälle. Alte Journale bleiben replayfähig. Kameraausfälle
setzen unbekannt; Schuss-/Fehlschusszeitpunkte werden nicht abgeleitet.

Die gesamte Validierung bleibt synthetisch. Die Helligkeitsklassifikation setzt
dunkle Öffnungen und helle, sichtbar begrenzte Klappen voraus. Gleich aussehende
Verdeckungen, starkes Sonnenlicht, Reflexionen, abweichende Mechanik und periodisch
identische Nachbargeometrien benötigen reale Aufnahmen und unabhängige Prüfung.
Keine Aussage zur Praxistauglichkeit vor dem ersten Schießstandtest.

Prüfungen: 70 Python-Tests erfolgreich. Zusätzlich zur bisherigen Kalibrierung
prüfen 192 klassifizierte Bilder alle 32 Zustände in drei Perspektiven und zwei
Beleuchtungen mit Rauschen. Videofolgen prüfen drei Bahnen aus zwei Kameras,
unterschiedliche Zielreihenfolgen, Verdeckung, kleine/große Bildbewegung,
Rückstellung, Ausfall, Wiederaufnahme als Grundbeobachtung und Journal-Replay.
Der neue Browser-Integrationstest führt zwei synthetische laufende Kameras durch
Erfassung, Persistenz und WebSocket bis zur unveränderten Tablet-Seite und zum
Kontrollmonitor. Er prüft insbesondere, dass drei sichtbare gefallene Ziele nach
einem Ausfall nicht zu drei behaupteten beobachteten Fällen werden.
Alle Prüfungen verwenden synthetisches Bildmaterial. Der RTSP-Transport bleibt
zusätzlich durch die lokalen Integrationstests aus 0.4 geprüft.

Abschließend 71 Python-Tests erfolgreich, einschließlich unverändertem Replay
mit dem tatsächlichen `core.py`/`models.py` aus Tag `v0.4.0`. Der Baseline-Marker
steht deshalb als zusätzliche Ereignismetadaten neben dem für ältere Leser
strikten Befehl. Ältere Programme öffnen das Journal mit ihren damaligen
Einlagenregeln; erneutes Replay unter 0.5 berücksichtigt die Grundbeobachtungen.
Der Optik-Browsertest und die Kamera-/Kalibrierungs-Browserregression sind auch
nach dieser Speicheranpassung erfolgreich.


## 2026-10-17 – Version 0.6: Stabile externe Datenausgabe

Die ursprünglich beauftragte KES-TCP-Emulation entfällt gemäß verbindlicher
Architekturkorrektur. Vor der Implementierung wurden die tatsächlich benötigten
Daten des zukünftigen GFX-Adapters geprüft: fünf Zielstellungen, bestätigte
Startnummer, aktuelle Einlage und getrennte Belegung sind bereits vorhanden.
Für die sichere Wiederverbindung fehlten eine Vertragsversion und Serverinstanz;
für die Unterscheidung „unverändert“/„Erfassung gestört“ fehlte der technische
Status im laufenden Kanal. Deshalb ergänzen bestehende Zustände `api_version`,
`instance_id`, `health` und `capture`; keine zusätzlichen Integrationsendpunkte.
Journalantworten und Health enthalten dieselbe API-Identität.

Die Dokumentation beschreibt einen vollständigen lesenden Adapter einschließlich
unbekannter Werte, Grundbeobachtungen, übersprungener Zwischenzustände und
Instanzwechsel. Kein künstlicher Schuss-/Fehlschusszähler; alle fünf Ziele werden
unabhängig von beobachteten Fällen angezeigt. Die bekannte GFX-Anzeigeabweichung
ist dort im separaten Issue #102 festgehalten. Keine Änderungen am GFX-Arbeitsbaum,
an dessen KES-/HORA-Komponenten oder an laufenden Diensten.


Die abschließende Installationsprüfung ergänzt echte lokale Serverprozesse für
Upgrade, Startfehler und Rückschalten bei bytegleich erhaltenen Daten. Dabei fiel
ein konkreter Installerfehler auf: Die vorbereitete Versionsnummer wurde aus dem
Arbeitsbaum statt aus demselben Git-Commit wie das Archiv gelesen. Beide werden
nun aus einer festen Revision ermittelt; ein Test prüft abweichende uncommittete
Dateien. Programmverzeichnisrechte und umask werden unabhängig von der
aufrufenden Root-Shell gesetzt; der Dienstbenutzer erhält explizit seine eigene
Gruppe. Keine Systempakete oder Dienste des Hosts wurden dafür verändert.


Die Integrationsprüfung berücksichtigt zudem eine kurze RTSP-Unterbrechung
vollständig zwischen zwei Auswertungsschritten. Eine interne Verbindungsnummer
im vorhandenen Decoder unterbricht auch dann die Beobachtungskette und erzwingt
Grundbeobachtungen. Ohne diesen Marker könnte eine neue Verbindung unbemerkt als
kontinuierliche Bildfolge gelten. Synthetische Parallelfolgen und der tatsächliche
lokale RTSP-Wiederverbindungstest prüfen dies; kein zusätzlicher öffentlicher Kanal.

Abnahme: 77 Python-Tests erfolgreich, einschließlich REST-/WebSocket-Vertrag,
Neustartkennung, Journalpagination, langsamer Empfänger, Speicher-/Erfassungsfehler,
Geheimnisschutz, tatsächlichem lokalem RTSP-Ausfall/Wiederaufbau, optischen Folgen
und echten isolierten Server-Upgrades mit Rollback und bytegleichem Datenerhalt.
Alle fünf Browserprüfungen (Tablet, Monitor, Standbild, Kameraadministration/RTSP
und Optik bis Tablet/Monitor) sowie `pip check`, Shell-/JS-Syntax und Diff-Prüfung
sind erfolgreich. GFX-Arbeitsbaum unverändert. Frische Betriebssysteminstallation
mit echtem systemd sowie reale Kameras/Schießstandaufnahmen bleiben Praxistests;
synthetische Tests werden ausdrücklich nicht als Praxistauglichkeitsnachweis gewertet.

## 2026-10-18 – Version 0.7: Manuell, automatisch und priorisierter Mischbetrieb

Die bisherigen Kamera-/Tablet-/Journalwege wurden zuerst geprüft. Der Kern bleibt
zentral; zwei Listen je Bahn trennen automatische Beobachtungen von manuellen
Werten. `targets` ist weiterhin der wirksame Zustand für bestehende Verbraucher.
Betriebsart und Übersteuerungen werden im vorhandenen Journal gespeichert, nicht
zusätzlich in Kamerakonfiguration oder Browserpräferenzen. Kein zusätzlicher
Dienst, keine Datenbank, keine Prioritäts-Engine.

Reguläre manuelle Erfassung funktioniert ohne Kamera und ohne Simulation.
Mischbetrieb verwendet dieselben Kacheln und erlaubt unmittelbare Korrekturen
mit einem Antippen. Ein separater Bedienzähler verhindert Konkurrenz zwischen
Bedienern, ohne jede neue Kamerabeobachtung als Bedienkonflikt zu behandeln.
Einlagenwechsel und Freigabe der aktuellen Einlage machen alte Bedienbefehle
ungültig. Unbekannt ist ausdrücklich wählbar. Übersteuerungen lassen sich je Ziel
aufheben; technische Verfügbarkeit, Vergleichswert und wirksamer Wert sind getrennt
sichtbar. Der Monitor ergänzt seine bisherige historische Fallzählung um die
aktuell wirksame Anzahl, ohne manuelle Eingaben als beobachtete Fälle auszugeben.

Beim Rückwechsel aus Manuell bleiben vorhandene Werte geschützt. Eine neue
Erfassungsgeneration unterbricht die alte Bildfolge und verwirft noch laufende
CPU-Auswertungen. Die ersten bekannten Beobachtungen sind Grundbeobachtungen.
Automatische Rückstellungen beziehen sich auf automatische Vorwerte; manuelles
Korrigieren nach oben beendet keine Einlage. Im manuellen Modus bestätigt der
Kampfrichter die tatsächliche vollständige Rückstellung. Es werden keine Schuss-,
Treffer- oder Fehlschussmeldungen aus Korrekturen erzeugt.

Das Journal enthält bei manuellen Eingaben den automatischen Vergleichswert mit
Beobachtungszeit, vorherigen wirksamen und neuen manuellen Wert. Bildbelege nutzen
nach Möglichkeit den bestehenden aktuellen Kamerapuffer und die Gesamt-ROI. Die
Begleitdatei nennt die Bildempfangszeit, da es nicht zwingend das Bild der letzten
stabilisierten Beobachtung ist. Fehlende Belege verhindern keine Erfassung;
Speicher-/Kodierungsfehler werden sichtbar protokolliert. Keine automatische
Auswertung, kein Training und keine neue Bildverwaltung.

Alte Journale einschließlich eines tatsächlich mit dem Code aus `v0.6.0`
erzeugten Journals werden ohne Migration gelesen. Neu eingeführte Bedienbefehle
benötigen beim Replay mindestens 0.7; der frühere pauschale Hinweis auf mögliche
Programm-Downgrades ist entsprechend eingeschränkt. Der Installer behält seine
Sicherung und seinen Rückwechsel bei einem Startfehler. Nach produktiver Nutzung
neuer Befehle wird niemals automatisch eine alte Datensicherung zurückgespielt.

Prüfstand: vollständig synthetisch und lokal. Kameraerkennung ist weiter nicht
unter realen Schießstandbedingungen validiert. Die manuelle Erfassung ist ein
regulärer Betriebsweg; eine Kamera ist dafür nicht erforderlich. Sensorhardware
und Sensoradapter sind weiterhin nicht implementiert. GFX und dessen KES-/HORA-
Verarbeitung wurden nicht verändert. Der anschließende eigenständige Auftrag zur
IBU-konformen Prüfung der GUI-Terminologie wird in einem separaten PR bearbeitet.

Abnahme 0.7: **92 Python-Tests erfolgreich**. Hinzugekommen sind 15 Tests für
manuelle Einlagen ohne Kamera, Zielpriorität und unabhängige automatische Ziele,
Übersteuerungsfreigabe, konkurrierende Bedienung und Freigabegrenzen,
Kameraausfall/Rückwechsel, Rückstellung, Journal-Replay einschließlich Original-
0.6-Journal, Bildbelege samt Speicherfehler sowie drei parallele Bahnen aus zwei
Kameras und verworfene Bildauswertung während einer Rückstellung. Alle sechs
Browserprüfungen erfolgreich: bisherige Tablet-, Monitor-, Kalibrierungs-,
RTSP-Administrations- und Optikprüfungen sowie die neue Betriebsartenprüfung mit
zwei Touch-Profilen, manuell ohne Kamera/Simulation und gemischtem Livebetrieb.
Kontrollbilder des manuellen und gemischten Betriebs wurden visuell geprüft;
keine Testartefakte werden versioniert. `pip check`, Shell-/JavaScript-Syntax und
`git diff --check` sind fehlerfrei. CI ergänzt fünf Browserprüfungen ohne externe
RTSP-Testwerkzeuge; der tatsächliche RTSP-Transport wurde lokal zusätzlich geprüft.

## 2026-10-18 – Originaltexte und Schutz vor doppelter Browserübersetzung

Zuerst wurden alle ausgelieferten HTML-/JavaScript-Dateien durchsucht. Keiner der
vier gemeldeten Fehlbegriffe kommt im Original vor. Chromium zeigt ohne zusätzliche
Browserübersetzung die vorhandenen Originaltexte korrekt. Das stützt die Vermutung
einer automatischen Chrome-Übersetzung, reproduziert aber nicht den unbekannten
Zustand des betroffenen Geräts. Die vier eigenen HTML-Seiten erhielten die drei
verlangten Schutzmerkmale; die bestehende Tablet-Sprachwahl setzt bereits `lang`
korrekt und wurde dafür nicht umgebaut. Die übrigen drei Seiten sind deutsch,
nicht dreisprachig; eine neue Übersetzungsbibliothek wurde nicht eingeführt.

Die von IBU bzw. Český svaz biatlonu veröffentlichten PDFs wurden heruntergeladen
und auf ihre tatsächlichen Begriffe geprüft: Englisch Version September 2026,
Deutsch Version Juli 2025, tschechische Verbandsfassung Version 2025 mit Änderungen.
Fassungen, direkte Quellen und Artikel-/PDF-Fundstellen stehen im neuen,
ausdrücklich beauftragten [Terminologieverzeichnis](TERMINOLOGIE.md).

`Schießbahn`, `Schießstand`, `Schießeinlage`, `střelecký stav`, `střelecká položka`
und das englische `Bib` sind belegt und bleiben erhalten. Deutsche
Scheibenbeschriftungen verwenden konsistent `Scheibe`, einschließlich
Kalibrierungsmeldungen und zugänglicher Monitorbeschriftungen. Im tschechischen
Freigabedialog wurde ein Satz umgestellt, damit die eingefügte nominative
Einlagenbeschriftung keinen falschen Akkusativ erzeugt. Die übrigen Originaltexte
wurden geprüft, ohne sie pauschal neu zu übersetzen. Mechanische Stellungen,
Unsicherheit und Bedienvorgänge werden ausdrücklich nicht als offizielle
IBU-Schaltflächen ausgegeben. Es werden keine Kleinkaliber-Wettkampfvorgaben auf
die technischen Eigenschaften einer 10-Meter-Luftgewehranlage übertragen.

Keine Änderung an Ereigniskern, Befehlen, Journalformat, Erkennung oder
Quellenpriorität. In `calibration.py` wurden ausschließlich ausgegebene
Meldungstexte und der Dateikommentar angepasst. Der neue Browsercheck prüft alle
vier Seiten, Vererbung des Übersetzungsschutzes, EN/DE/CS-Originaltexte, Sprachwahl
und Wiederladen sowie Startnummern-, Einlagen-, Freigabe- und Rückstelldialoge.
Sprachwechsel/Dialogprüfungen dürfen die Journalfolge nicht verändern. Zwei kleine
Python-Checks prüfen sämtliche eigenen HTML-Dateien und verhindern die erneute
Einführung der gemeldeten Fehlbegriffe in den Original-Browserdateien. Der
Browsercheck wird auch in CI ausgeführt; kein Test beansprucht Kontrolle über den
externen Google-Dienst oder beliebige Browsererweiterungen.

Prüfergebnis: **94 Python-Tests erfolgreich**. Neuer Übersetzungs-Browsercheck,
bestehender Tablet-Test mit zwei Profilen und drei Sprachen, Standbildkalibrierung
sowie Kameraadministration mit tatsächlichem lokalem RTSP-Transport erfolgreich.
JavaScript-Syntax und `git diff --check` fehlerfrei. Die CI führt zusätzlich die
bestehenden Betriebsarten-, Monitor- und Optik-Browserregressionen aus.

## 2026-10-18 – README auf manuellen Nutzen und Mischbetrieb ausrichten

Nach Abschluss der Terminologieprüfung beschreibt die README zuerst reguläre
manuelle Erfassung und synchronisierte Tablets sowie manuelle Priorität im
Mischbetrieb. Der Ersatzbetrieb für Bahnen 4–6 bei Kameraausfall/Schneefall wird
an einem konkreten Beispiel erklärt. Zielgruppe Zeitnahmeunternehmen, vorhandene
REST-/WebSocket-Ausgabe und noch zu prüfende konkrete Anbindungen sind getrennt.
Der Arberstadion-Termin Ende Oktober 2026 und die mögliche Begutachtung durch
tschechische Zeitnehmer sind entsprechend dem Auftrag als geplant bezeichnet.

Installationsbefehle und technische Betriebshinweise bleiben erhalten;
Dopplungen und das ältere Tablet-Konzeptbild wurden entfernt. Begriffe folgen
dem Terminologieverzeichnis. Geprüft wurden lokale Links/Anker, Bildverweis,
identische Shell-Beispiele und die Beschränkung auf Dokumentationsdateien.
Keine Anwendungscodeänderung und keine neue Aussage über reale Validierung.

## 2026-10-18 – Ergonomie und einheitlicher Schießstandablauf

Vor der Änderung wurden Belegung, Startnummer, Einlage und Scheiben im Kern,
in Tablet und API geprüft. Bisher konnte nur eine Startnummernzuordnung belegen;
eine bloße manuelle Scheibeneingabe konnte unbeabsichtigt eine Einlage eröffnen.
Ein neuer `occupy`-Befehl nutzt den vorhandenen Belegungszähler und erlaubt sofortige
Belegung ohne BIB. Verspätete Zuordnung, historische Korrektur, Freigabe und
WebSocket-Veröffentlichung bleiben auf den bisherigen Wegen. Der neue
Tablet-Ablauf sendet `start_bout: false` bei Einzelkorrekturen. Der bisherige
Standardwert erhält ältere API-Clients und Journale, ohne eine neue Schnittstelle
für dieselbe Zielkorrektur einzuführen.

Ein boolesches Vorbereitungsmerkmal und ein Marker für noch unvollständige
automatische Rückstellung genügen für den GRÜN-GELB-GRAU-Ablauf. Belegung verbraucht
die vorherige Vorbereitung. Einlagenende bei tatsächlich beobachteter einzelner
Rückkehr nach oben bleibt erhalten; erst vollständige Rückstellung bestätigt
Bereitschaft und beendet alte Übersteuerungen. Unveränderte Fünferbilder und
Grundbeobachtungen bestätigen keine neue Rückstellung. Kameraausfall oder
beendete Auswertung verhindern im gemeinsamen Snapshot eine Bereitmeldung.
Manuelle Bahnen bleiben unabhängig. Neue Befehle benötigen diesen Stand für
Replay; der ältere Tag `v0.7.0` kann neue `occupy`-/`start_bout`-Befehle nicht lesen.
Alte Journale bleiben lesbar. Kein automatisches Zurückspielen von Laufzeitdaten.

Alle drei Betriebsarten verwenden dieselbe Kachelstruktur, denselben farbigen
Hintergrund samt Statuswort und dieselben Hauptaktionen. Scheiben sind schwarz
oder weiß, mit ausreichend großen Touchflächen in einer Reihe. Einzelkorrekturen,
Betreten, Verlassen und ausdrücklich beschriftete Vorbereitung sind unmittelbar.
Moduswahl, Historie und Unbekannt-Sonderfunktion stehen unter Optionen. Manuelle
Übersteuerungen tragen `M`; darunter bleibt der kleine automatische Vergleichswert
mit direkter Rückgabe sichtbar. Diese Bedienvorgänge sind im Terminologieverzeichnis
als technische UI-Beschreibungen gekennzeichnet, nicht als erfundene IBU-Begriffe.

Die erste visuelle Prüfung zeigte auf kleinen Tablets zu viel Platzbedarf in der
Kopfzeile und durch Erfolgsmeldungen verschobene Touch-Ziele. Kopfzeile und
Beschriftungen wurden gekürzt; Erfolgsmeldungen erscheinen kurz außerhalb des
Layouts. Feste Höhen von Statuszeile, Scheiben und Hauptaktion verhindern
Verschiebungen bei Status-/Moduswechseln. Lange Statuswörter dürfen umbrechen,
die Bahnnummer bleibt zusammen. Geprüfte Abbildungen liegen unversioniert in
`.test-artifacts/workflow-*.png`.

README beschreibt jetzt den vollständigen Ablauf, die Aufgabenverteilung und
die Auswahl von Manuell vor der ersten Vorbereitung ohne Kamera. Die Kamera erfasst Scheiben und zuverlässig erkannte Rückstellung, niemals
Betreten, BIB oder Verlassen. Der Installationspfad beschreibt bewusst den
aktuellen `main`, weil der neue Ablauf noch nicht in Tag `v0.7.0` enthalten ist.
`--upgrade` bleibt auf veröffentlichte Tags beschränkt. Sensorik bleibt geplant;
keine GFX-Änderung, keine Ergebnisverwaltung oder künstliche Schussmeldung.

Abnahme lokal: **107 Python-Tests erfolgreich**, darunter 13 neue Ablauf-/API-Tests
für Belegen ohne BIB, beide Reihenfolgen von Verlassen/Rückstellung, unveränderte
Fünferbilder, Korrekturen ohne Einlagenbeginn, automatische Teil-/Vollrückstellung,
Mischpriorität, unterbrochene Rückstellung, Replay, zwei Tablets und sofortige
Sperre veralteter Bereitmeldungen bei Kamera-/Erfassungsausfall. Der bestehende
Misch-Rückstelltest beginnt nun mit fünf bekannten automatischen Stellungen;
eine Teilrückstellung bei ansonsten unbekannten Scheiben bestätigt keine
vollständige Vorbereitung.

Sieben Browserprüfungen erfolgreich: bestehende Tablet-, Betriebsarten-,
Übersetzungs-, Monitor-, Kalibrierungs- und Optikprüfungen sowie der neue
Ablauftest. Dieser benutzt echte lokale Server und zwei unabhängige Touch-Profile
mit 600×960 und 960×600 Pixeln, prüft EN/DE/CS, tatsächliche Hintergrund-/Scheibenfarben,
Touchflächen ab 48 Pixeln und unveränderte Aktionspositionen. Die Darstellungen
wurden zusätzlich als Bilder visuell geprüft. CI führt den neuen Ablauftest mit
aus. `pip check`, Shell-/JavaScript-Syntax, lokale README-Links/Anker und
`git diff --check` erfolgreich. Keine neue Laufzeitabhängigkeit.

Praxistestgrenzen bleiben: synthetische Kamerabilder und Chromium, keine realen
Schießstandaufnahmen, keine physischen Tablets bei Sonne/Schnee/Handschuhen und
keine Sensorhardware. Der geplante Arberstadion-Test wird nicht als bereits
durchgeführte Validierung dargestellt.

## 2026-10-18 – Ein Kampfrichterablauf und weniger Sonderwege

Ausgangspunkt ist `main` nach PR #9 (`39674032`). Zwei gleichrangige Ziele sind
vereinfachte Bedienung und einfachere Implementierung. Die bisherigen
Betriebsartkonzepte aus 0.7/PR #9 sind für die normale Tablet-Bedienung überholt.

Die Prüfung fand konkrete fachliche Probleme: Automatisch sperrte manuelle
Korrekturen; eine manuelle Vorbereitung blieb von Kameranachweisen abhängig;
Quellensperren kopierten alle fünf Werte als vermeintlich manuelle Korrekturen;
beim Löschen von Übersteuerungen konnten alte Kamerawerte wieder wirksam werden.
Bereits die erste Teilrückstellung schloss eine Einlage. Außerdem machte Verlassen
nach einer bereits abgeschlossenen Rückstellung eine offene Zielauswahl eines
zweiten Tablets nicht ungültig. Diese Fälle sind korrigiert und gezielt geprüft.

Ein Tipp auf eine bekannte Scheibe korrigiert direkt. Ein unbekanntes Ziel bietet
zwei große, ausdrücklich beschriftete Auswahlflächen für aufgerichtet/gefallen.
Belegen/Verlassen und vollständige Rückstellbestätigung sind immer sichtbar.
Moduswahl, fünf Vergleichsanzeigen, permanente Auto-Freigaben und die Funktion
„Unbekannt setzen“ entfallen. Kameraausfall verlangt keine Umschaltung. Der
Monitor übernimmt dieselben ganzen Kachelfarben, Startnummer und fünf effektive
Stellungen; technische Zähler entfallen. Vergleichswerte und die bisherige
administrative Quellensperre liegen unter `/admin`, ohne neue Konfigurationsdatei.

Die Vereinfachung betrifft tatsächliche Verarbeitungswege:

- Alle regulären Scheiben nutzen dieselbe manuelle Korrektur. Die vorher getrennten
  schreibgeschützten/bedienbaren Zielkacheln, Übersteuerungsreihe, Modus-Handler und
  Unbekannt-Menü entfallen samt CSS und ungenutzten Übersetzungen.
- Direkte Aktionen und Dialogeingaben verwenden einen gemeinsamen HTTP-Ablauf für
  Übermittlung, Fehler, Zustandsabgleich und Wiederverbindung. Der alte
  Freigabe-Bestätigungsdialog und sein eigener Konfliktabgleich sind entfernt.
- Alle REST-Bahnendpunkte teilen die Prüfung von URL-/Befehlsbahn und Veröffentlichung.
  Jeder Einlagenbeginn bereinigt alte Übersteuerungen am selben vorhandenen Ort.
- `automatic` und `mixed` haben dieselbe Bedeutung: zugelassene automatische Daten
  mit menschlicher Priorität. Eine administrative Sperre erzeugt keine fünf
  künstlichen manuellen Werte mehr. Korrekturbilder hängen nicht mehr vom Modus ab.
- Nur das tatsächlich beobachtete Ziel wird neu berechnet. Das verhindert zugleich,
  dass ein fremdes Zielereignis manuell bestätigte Vorbereitung durch alte oder
  unbekannte Vergleichswerte ersetzt. Erfolgsmeldungen starten nicht mehr bei
  jedem Rendern weitere Timer.

Notwendige Informationen bleiben bewusst getrennt: tatsächliche automatische
Beobachtung, manuelle Übersteuerung und wirksamer Zustand; Belegung, BIB und Einlage;
letzte bekannte Stellung trotz Unklarheit; Vorbereitung gegenüber bloß fünf
stehenden Scheiben. Der Generations-/Baseline-Schutz verhindert alte CPU-Ergebnisse
und rückwirkende Ereignisse nach Wiederverbindung. Getrennte Belegungs- und
Bedienzähler sind durch reale Mehrtablett-/HTTP-Rennen begründet. Öffentliche
Historienfelder und vorhandene Quellenbefehle bleiben aus API-Kompatibilitätsgründen
erhalten. Es entsteht kein zusätzliches Zustandsfeld je Bahn und kein Framework.

Die korrigierte Vollrückstellregel darf historische Einlagengrenzen und Revisionen
nicht ändern. Deshalb kennzeichnen neue Ereignisse ihre Regeln mit
`rules_version: 2`; wenige Zweige im selben Reducer erhalten die alte Verarbeitung
für unmarkierte Ereignisse. Ein tatsächlich mit PR #9 erzeugtes Journal wird
bytegleich gelesen, einschließlich alter Teilrückstellung, manueller Vorbereitung,
Revisionen und idempotenter Wiederholung. Anschließende neue Befehle und erneutes
Replay werden geprüft. Eine alte bestätigte Vorbereitung bleibt auch beim ersten
neuen Belegen erhalten. Kein generischer Kompatibilitätsadapter oder zweiter Kern.
Nach neuen Ereignissen ist Downgrade auf PR #9 unsicher, selbst wenn ältere Leser
den Marker ignorieren. Auswirkungen und Sicherungsgrenzen stehen in API.md.

Prüfungen: **119 Python-Tests erfolgreich**, ausgehend von 107; zwölf neue Prüfungen
betreffen u. a. drei Sportler ohne Kamera/Quellenwahl, null/eine/mehrere gefallene
Scheiben, Einzelkorrektur ohne Einlagengrenze, volle statt teilweiser Rückstellung,
direkte manuelle Weiterarbeit und Wiederverbindung, echte gegenüber künstlichen
Übersteuerungen, veraltete Auswahl nach Freigabe, unbekannte Stellungen,
ausgefallene Optik und historisches Replay. Die bestehenden API-, Speicher-,
Upgrade-/Rollback-, RTSP- und synthetischen Optiktests bleiben erfolgreich.
Angepasste ältere Tests erwarten ausdrücklich keine Korrektursperre im Modus
`automatic` und keine Einlagengrenze bei bloßer Teilrückstellung mehr.

Acht lokale Browserprüfungen erfolgreich: Übersetzung, Tablet, Erfassung,
Schießstandablauf, Monitor, Standbildkalibrierung, Optik und Kameraadministration
mit tatsächlichem lokalem RTSP-Stream. Zwei unabhängige Touch-Profile prüfen
600×960/960×600 und größere Tablets, alle drei Sprachen, sichtbare Zustände,
Korrekturen, Ausfall, administrative Quellenwahl und Synchronisierung. Verglichen
werden echte Hintergrund-/Scheibenfarben, Touchflächen und Aktionspositionen.
Tablet, unbekannte Auswahl, Monitor und Administration wurden zusätzlich anhand
von Browserbildern visuell geprüft. Bilder bleiben unversionierte Testartefakte.
JavaScript-/Shell-Syntax, `pip check` und `git diff --check` sind fehlerfrei.
Die erste CI-Prüfung zeigte ein Rennen bei der Browser-Layoutmessung während
einer Live-Aktualisierung. Die Prüfung misst die Hauptaktion jetzt atomar relativ
zur Kachel; sie hängt damit weder an einem ersetzten DOM-Element noch am Scrollstand.

Die optische Validierung bleibt synthetisch. Reale Schießstandbilder, Schnee,
Lichtwechsel, Handschuhe, physische Tablets und WLAN unter Veranstaltungsbedingungen
müssen im geplanten Arberstadion-Test überprüft werden. Sensorik bleibt geplant.
Keine GFX-Änderung, KES-Emulation, Schussmeldung oder neue Veröffentlichungsversion.

### Umfang der Produktänderungen

Physische Zeilen einschließlich Kommentaren/Leerzeilen, verglichen mit PR #9;
Tests und Dokumentation sind nicht mitgezählt. Eine niedrigere Zahl ist kein
alleiniger Qualitätsnachweis. Der Kern wächst für die fachlichen Korrekturen und
das nachgewiesene historische Replay; entfernt wurden vor allem parallele
Bedien-/Übermittlungswege und abgeleitete UI-Sonderfälle.

| Produktdatei | Vorher | Nachher | Differenz |
|---|---:|---:|---:|
| `app.py` | 443 | 434 | -9 |
| `core.py` | 407 | 439 | +32 |
| `static/admin.html` | 17 | 19 | +2 |
| `static/admin.js` | 31 | 57 | +26 |
| `static/monitor.css` | 4 | 3 | -1 |
| `static/monitor.js` | 49 | 50 | +1 |
| `static/tablet.css` | 112 | 100 | -12 |
| `static/tablet.js` | 569 | 511 | -58 |
| `static/translations.js` | 135 | 114 | -21 |
| **Summe** | **1767** | **1727** | **-40** |
