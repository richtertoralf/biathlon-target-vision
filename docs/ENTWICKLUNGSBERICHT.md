# Entwicklungsbericht

Chronologischer Entwicklungsverlauf mit Entscheidungen und damaligen
Testergebnissen. Maßgeblich für den aktuellen Stand von Version 0.2 sind
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
  sichtbar fehlschlagen. Laufende Videoauswertung ist noch nicht implementiert.
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
  wachsender Historie fehlen. systemd-Installation und KES-Ausgabe stehen ebenfalls aus.

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
