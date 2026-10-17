# Architektur – Biathlon Target Vision

Dieses Dokument beschreibt die aktuelle Architektur von Version 0.6.
Projektumfang und Nutzungseinstieg stehen in der [README](../README.md),
Datenfelder und Integrationsregeln in [API.md](API.md), die Entwicklung und
Validierungsgrenzen im [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md).

## Grundkonzept

Ein zentraler Python-Prozess mit FastAPI und Uvicorn hält den gemeinsamen Zustand
aller Schießbahnen. Die Anwendung läuft lokal unter Linux ohne Cloud und benötigt
im Betrieb keinen Internetzugang. HTML, CSS und JavaScript werden ohne
Frontend-Buildsystem ausgeliefert. Es gibt keine zusätzliche Datenbank, verteilten
Dienste oder Sitzungsverwaltung. Die technische Orientierung an
[LiveScore](https://github.com/richtertoralf/LiveScore) beschränkt sich auf benötigte
Konzepte; Erweiterungen erfolgen nur bei konkretem Bedarf.

## Komponenten und Datenfluss

| Komponente | Aktuelle Aufgabe |
|---|---|
| `__main__.py` | Serverstart, Bahnanzahl, Datenordner und Simulationsmodus |
| `app.py` | REST-API, WebSockets, statische Browserseiten und flüchtige Eingabeentwürfe |
| `models.py` | Validierung der Beobachtungs-, Zuordnungs- und Freigabebefehle |
| `core.py` | Gemeinsamer Bahnzustand, Einlagen, Konfliktprüfung, Ereignisjournal und Wiederherstellung |
| `simulator.py` | Zielbeobachtungen über denselben öffentlichen Eingang wie künftige Erfassungsadapter |
| `static/tablet.*`, `static/translations.js` | Tablet-Bedienung und zentrale Übersetzungen |
| `calibration.py`, `static/calibration.*` | Gemeinsame Standbild-/Kamerakalibrierung und Nachführung |
| `config.py`, `cameras.py`, `static/admin.*` | Persistente Kamerakonfiguration, RTSP-Eingang, Administration |
| `vision.py` | Bestätigte optische Zielbeobachtungen und Grundzustände |
| `static/monitor.*` | Schreibgeschützte Gesamtübersicht |
| `deployment.py`, `install.sh`, `systemd/` | Installation, Status, Upgrade und Dienstbetrieb |

Bestätigte Bedienbefehle und simulierte Zielbeobachtungen gelangen über REST und
die Befehlsvalidierung in den Ereigniskern. Optische Beobachtungen verwenden
dieselben Befehlsmodelle und dieselbe Veröffentlichung innerhalb des Prozesses. Dieser prüft sie am gemeinsamen
Zustand, speichert akzeptierte Ereignisse dauerhaft und veröffentlicht erst danach
den neuen Zustand. REST-Antworten und vollständige WebSocket-Zustände versorgen
die Bedienplätze. Langsame Empfänger erhalten den neuesten Stand; das Journal
bewahrt auch die in der Anzeige übersprungenen Zwischenereignisse.

Unbestätigte Texte nehmen einen getrennten Weg: Browser → WebSocket → flüchtige
Entwürfe in `app.py` → andere Browser. Sie erreichen weder Ereigniskern noch
Journal. Die Kalibrierung verarbeitet einzelne Bilder und speichert Ergebnisse
separat; sie erzeugt keine Zielbeobachtungen.

## Ereigniskern und Speicherung

Eine Bahn besitzt fünf unabhängige Zielzustände. Beobachtung, aktuelle
Schießeinlage und noch bestehende Belegung sind getrennt: Eine Rückstellung
beendet die Einlage, eine Freigabe beendet die Belegung. Damit können Treffer vor
der Startnummerneingabe sowie verspätete Zuordnungen und Freigaben verarbeitet
werden. Unbekannte Zielzustände löschen die letzte bekannte mechanische Stellung
nicht. Es entstehen keine erfundenen Schuss- oder Fehlschussereignisse.

Belegungsänderungen werden getrennt von Zielbeobachtungen auf Konkurrenz geprüft.
Die Prüfung und Übernahme eines Befehls erfolgen gemeinsam im Kern. Eine Eingabe
behält ihren Einlagenbezug auch über Rückstellungen hinweg; sie darf nicht
unbemerkt auf den nächsten Sportler wechseln. Die konkreten Zähler, Kennungen
und Auswahlregeln sind in [API.md](API.md#startnummern-und-freigabe) definiert.

`data/events.jsonl` enthält einen Versions-/Konfigurationskopf mit der Bahnanzahl
und danach die akzeptierten Befehle in ihrer Reihenfolge. Vor der Veröffentlichung
wird mit `fsync` dauerhaft geschrieben. Ein Dateilock verhindert zwei schreibende
Serverprozesse im selben Datenordner; er ist keine Bahnsperre für Bediener.
Beim Start stellt dieselbe Zustandslogik den Zustand aus dem Journal wieder her.
Journal und Einlagen werden zusätzlich vollständig im Arbeitsspeicher gehalten.

Schreibfehler verhindern weitere Ereignisse bis zum Neustart. Ein beschädigtes
Journal wird beim Start mit Fehler abgewiesen, nicht automatisch gekürzt.
Betriebshinweise stehen in [API.md](API.md#speicherung-und-fehlerbehandlung).

## Tablet-Bedienung und Mehrbenutzerbetrieb

`/` liefert die Tablet-Oberfläche. Alle Bedienplätze arbeiten mit demselben
Serverzustand; Sprache und Bahnauswahl liegen je Browser/Origin in `localStorage`.
Die Auswahl ist ein Anzeigefilter und darf sich überschneiden. Große
Bedienelemente und flexible Spalten unterstützen Hoch- und Querformat.
`translations.js` enthält English als Standard sowie Deutsch und Čeština.

Pro WebSocket-Verbindung gibt es höchstens einen getrennt sichtbaren Entwurf.
Die Tablet-Nummer unterscheidet Verbindungen, ist aber keine Anmeldung oder
permanente Gerätekennung. Es gibt keine exklusiven Bahnsperren oder Reservierungen.
Verlassen des Eingabebereichs, Trennung oder ausbleibende Erneuerung entfernen die fremde Anzeige,
ohne den Text als offizielle Startnummer zu übernehmen.

Treffer und Rückstellungen unterbrechen keine laufende Startnummerneingabe.
Bei einem Belegungskonflikt bleibt der Text bearbeitbar; der Bediener prüft den
aktuellen Stand und bestätigt danach ausdrücklich. Offline sind Bestätigungen
deaktiviert. Nach Wiederverbindung wird der aktuelle Serverzustand übernommen
und mit der offenen Eingabe abgeglichen. Es gibt keine automatische Wiederholung
von Befehlen und keine dauerhaft gespeicherten Offline-Eingaben.
Protokoll, Zeitgrenzen und Wiederverbindung beschreibt
[API.md](API.md#synchronisierung).

`--simulation` aktiviert die Zielbedienelemente und die reservierte Quelle
`simulator` am Beobachtungseingang. Der Modus wird beim Serverstart festgelegt.
Manuelle Zielbedienung prüft den gesehenen Zielzustand weiterhin über die volle
Bahnrevision; Belegungsbefehle verwenden den getrennten Belegungszähler.

## Standbild-Kalibrierung

Die deutsche Browserseite `/calibration` verwendet OpenCV und NumPy ohne
trainiertes KI-Modell. Der Bediener markiert die vier Ecken der Gesamt-ROI.
Nach perspektivischer Entzerrung werden fünf sichtbare Zielkonturen anhand ihrer
Geometrie und regelmäßiger Abstände geprüft und von links nach rechts zugeordnet.
Die Ansicht zeigt die erkannten Zielbereiche zur Kontrolle und meldet unsichere
Erkennung als Fehler. Unsichtbare Ziele werden nicht aus dem Raster ergänzt.

Die Grundkalibrierung wird separat und atomar gespeichert. Die Nachführung erkennt
die Reihe im neuen Standbild erneut und vergleicht mit dieser festen Basis, damit
sie nicht schrittweise auf Nachbarziele wandert. Kameraanbindung und laufende Auswertung verwenden dieselben Funktionen.

## Weitere Anbindungen

- Spätere Sensoradapter sollen denselben Beobachtungseingang nutzen.
- Ein physisches Tastenfeld soll die vorhandene zentrale Bahnverwaltung bedienen.
- Externe Anwendungen lesen REST und WebSockets. BTV emuliert kein KES und
  erzeugt keine Schuss-/Fehlschussmeldungen. Die zukünftige GFX-Quelle BTV wird
  separat umgesetzt; siehe [gfx-engine #102](https://github.com/richtertoralf/gfx-engine/issues/102).

## Installation und Upgrades

`install.sh` installiert unter Debian/Ubuntu Git, Python-venv und native
Voraussetzungen. `deployment.py` übernimmt ausschließlich Git-versionierte Dateien
in `/opt/biathlon-target-vision/releases/`, erzeugt eine eigene venv und prüft
Abhängigkeiten/Importe vor dem Dienststopp. `current` verweist auf den aktiven Stand.
Der unprivilegierte Benutzer `btv` schreibt ausschließlich in
`/var/lib/biathlon-target-vision/` (Verzeichnis 0750, neue Dateien über UMask 0077).
Dort bleiben `config.json`, Kalibrierungen und Ereignisjournal bei Upgrades bestehen.
Die Konfiguration enthält zunächst `host` und `port`; die Installation bindet an
`0.0.0.0:8091`, der lokale Entwicklungsstart weiterhin an `127.0.0.1:8091`.

Der Dienst startet über systemd, Logs liegen im Journal (`journalctl -u
biathlon-target-vision`). Der Starter unter `/usr/local/bin/biathlon-target-vision`
bietet `--version`, `--status` und `--upgrade`. Ohne Leserecht auf die geschützte
Konfiguration prüft Status die Standardadresse; einen abweichenden Port explizit
mit `--status --port PORT` angeben oder Status mit sudo aufrufen. Upgrade lädt den höchsten stabilen
Git-Versionstag, bereitet ihn vor, stoppt den Dienst, sichert den Datenordner unter
`/opt/biathlon-target-vision/backups/` und schaltet atomar den Programmlink um.
Bleibt die neue API nicht mit passender Versionsnummer erreichbar, wird der
vorherige Programmstand gestartet. Daten werden dabei nicht zurückgespielt;
Upgrades müssen deshalb das Journalformat rückwärtskompatibel halten. Neue
Grundbeobachtungen speichern ihren Marker als zusätzliche Ereignismetadaten;
Version 0.4 kann das Journal weiterhin öffnen. Ältere Programme kennen diese
Kennzeichnung nicht und verwenden bei einem Rollback ihre damaligen
Einlagenregeln. Version 0.5 stellt beim erneuten Replay die neuere Bedeutung wieder her. Sicherungen
und alte Programmstände werden bewusst nicht automatisch gelöscht.
Ein Dateilock verhindert parallele Installationen/Upgrades.

## Kontrollmonitor

`/monitor` liest vollständige Zustände über `/ws`, zeigt ausschließlich bestätigte
Daten und besitzt keine Bedienfunktionen. Der Kern führt je Einlage die eindeutig
beobachteten gefallenen Zielpositionen als `fallen_target_ids`; Replay berechnet
sie auch für alte Journale. Das ist keine Anzahl abgegebener Schüsse. Eine
Verdeckung löscht diese Beobachtungen nicht, eine neue Einlage beginnt bei null.


## RTSP-Kameras und Administration

`config.json` enthält neben Serveradresse/Port eine Liste `cameras` mit `id`,
`name`, vollständiger `url` und `lane_ids`. Die validierte Konfiguration erlaubt
jede Bahn höchstens einmal und wird atomar mit Modus 0600 gespeichert. Ungültige
Konfigurationen werden mit einer allgemeinen Fehlermeldung abgewiesen, damit keine
RTSP-Zugangsdaten im Fehlertext erscheinen.

`cameras.py` betreibt je Kamera einen OpenCV-/FFmpeg-Decoder in einem Thread des
zentralen Prozesses, RTSP über TCP, Öffnungs-/Lesezeitlimit jeweils zwei Sekunden.
Nur das letzte Bild samt Empfangszeit/Nummer bleibt erhalten; Vorschau und später
Auswertung teilen es. Kein Frame-Journal und kein Streamingdienst. Fehler führen
zu getrenntem Status und Wiederverbindung nach einer Sekunde; nach spätestens
drei Sekunden gilt ein Bild als veraltet. Native Decoderlogs sind wegen möglicher
Zugangsdaten deaktiviert. API/Tablet bleiben bei Verbindungsausfällen unabhängig.

`/admin` verwaltet Kameras, Bahnzuordnung und JPEG-Vorschau. Die vorhandene Seite
`/calibration?lane=N` übernimmt ein aktuelles Kamerabild als eingefrorenes Standbild.
Kalibrierungen enthalten Kamerakennung und URL-Hash; eine andere Quelle verlangt
Neukalibrierung. Bildgröße und begrenzte Nachführung prüfen die Bildgeometrie.
Beim Bearbeiten kann eine leere URL die vorhandene übernehmen; öffentliche
Kameraantworten enthalten ausschließlich Namen, Kennung, Bahnen und Status.


## Laufende optische Erfassung

`vision.py` verarbeitet aktuelle Kamerabilder in einer Async-Aufgabe; CPU-Arbeit
läuft im vorhandenen Threadpool. Bilder werden nicht aufgestaut, jedes Bild je
Bahn höchstens einmal betrachtet. Alle bestätigten Befehle gehen im zentralen
Eventloop durch dieselbe Veröffentlichung und persistente Kernlogik wie REST.

Vorhandene `align`-Nachführung prüft zunächst alle fünf Konturen gegen die feste
Grundkalibrierung. Bei Teilverdeckung dürfen mindestens drei konsistente Anker,
darunter beide Endziele, eine kleine Translation bestätigen. Fehlende Innenziele
werden unbekannt. Ohne beide Endanker bleibt die ganze Reihe unbekannt: Eine
Verschiebung um einen Zielabstand darf keine Nachbarposition vortäuschen.
Große Bewegung, andere Auflösung oder fehlende Kalibrierung ergeben unbekannte
Zustände. Die feste Basis verhindert schrittweise Drift; die Grenzen wiederholter
identischer Zielgeometrie bleiben im realen Aufbau zu prüfen.

Die Klassifikation vergleicht Zielinneres und lokalen Hintergrund: dunkle Öffnung
= `standing`, helle Klappe mit erkennbarer Kontur = `fallen`; Zwischenwerte,
uneinheitliches Inneres oder fehlende Kontur = `unknown`. Drei verschiedene
Bilder und mindestens 250 ms bestätigen eine Änderung. Das sind einfache
OpenCV-Verfahren für die bislang synthetisch modellierte dunkle Öffnung/helle
Klappe, kein trainiertes Modell und kein Nachweis an beliebigen Anlagen.

`baseline` kennzeichnet Grundbeobachtungen nach Start, Quellen-/Kalibrierwechsel
oder Verbindungsunterbrechung. Sie aktualisieren sichtbare und zuletzt bekannte
Stellungen, erzeugen aber keinen neuen Fall, keine neue Einlage und keine
rückwirkende Rückstellung. Ausfälle setzen Ziele unmittelbar auf unbekannt und
unterbrechen die zeitliche Kontinuität. Eine interne Verbindungsnummer je Decoder
erkennt auch Ausfälle, die zwischen zwei Auswertungsschritten vollständig
überbrückt wurden. Normale kurzzeitige Bildunsicherheit
bewahrt die letzte Stellung; eine anschließend bestätigte Rückkehr nach oben
beendet über den vorhandenen Kern die Einlage. Ein Sportlerwechsel während eines
Ausfalls bleibt unbestimmt und benötigt die vorhandene ausdrückliche Bedienung.
`observed_at` ist die serverseitige Bildempfangszeit des bestätigenden Bildes,
kein Schusszeitpunkt. Defekte Kalibrierungen betreffen nur ihre Bahn, werden
protokolliert und in der Kalibrierungs-API sichtbar. Ein unerwartet beendeter
Auswertungstask oder gesperrter Ereignisspeicher macht `/api/health` fehlerhaft.


## Externer Datenvertrag

Version 0.6 stabilisiert die vorhandenen REST-/WebSocket-Schnittstellen als
API-Version 1. Kein KES-Emulator und kein zusätzlicher Port: externe Anzeigen
verwenden dieselben vollständigen Zustände wie die Browser. `api_version` trennt
den Integrationsvertrag von der Anwendungsversion; `instance_id` kennzeichnet
einen Serverstart. Technischer Erfassungsstatus und bereinigte Kameradaten stehen
im vorhandenen Zustand, weil eine unveränderte Zielstellung allein keine Aussage
zur Verfügbarkeit erlaubt. Das ergänzt konkret fehlende Integrationsdaten, ohne
einen zweiten Ereigniskanal oder ein Adapterframework einzuführen.

`sequence` bleibt die Reihenfolge dauerhaft akzeptierter Befehle. Lebenszeichen
und Kamerastatus ändern sie nicht. Langsame Empfänger erhalten aktuelle
vollständige Zustände; das Journal kann separat gelesen werden. Der Monitor
kennzeichnet `health: error` ausdrücklich als gestörte Erfassung mit letztem Stand.
Vertrag, Wiederverbindung und Beispielclient stehen ausschließlich in [API.md](API.md#externe-integration-eigenständige-quelle-btv).
Die spätere GFX-Integration ist in Issue #102 dokumentiert; GFX-Code wurde im
Rahmen dieser Versionen nicht verändert.
