# Architektur – Biathlon Target Vision

Dieses Dokument beschreibt die aktuelle Architektur von Version 0.7.
Projektumfang und Nutzungseinstieg stehen in der [README](../README.md),
Datenfelder und Integrationsregeln in [API.md](API.md), die Entwicklung und
Validierungsgrenzen im [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md).

## Grundkonzept

Ein zentraler Python-Prozess mit FastAPI und Uvicorn hält den gemeinsamen Zustand
aller Schießbahnen. Die Anwendung läuft lokal unter Linux ohne Cloud und benötigt
im Betrieb keinen Internetzugang. HTML, CSS und JavaScript werden ohne
Frontend-Buildsystem ausgeliefert. Es gibt keine zusätzliche Datenbank, verteilten
Dienste oder Wettkampfverwaltung. Die technische Orientierung an
[LiveScore](https://github.com/richtertoralf/LiveScore) beschränkt sich auf benötigte
Konzepte; Erweiterungen erfolgen nur bei konkretem Bedarf.

## Komponenten und Datenfluss

| Komponente | Aktuelle Aufgabe |
|---|---|
| `__main__.py` | Serverstart, Bahnanzahl, Datenordner und Simulationsmodus |
| `app.py` | REST-API, WebSockets, statische Browserseiten und flüchtige Eingabeentwürfe |
| `models.py` | Validierung der Beobachtungs-, Zuordnungs- und Freigabebefehle |
| `sessions.py` | Getrennte Aufzeichnungssitzungen, atomarer aktiver Verweis und Archivzugriff |
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

`data/sessions/SITZUNGS-ID/events.jsonl` enthält einen Versions-/Konfigurationskopf mit der Bahnanzahl
und danach die akzeptierten Befehle in ihrer Reihenfolge. Vor der Veröffentlichung
wird mit `fsync` dauerhaft geschrieben. Ein Dateilock verhindert zwei schreibende
Serverprozesse im selben Datenordner; er ist keine Bahnsperre für Bediener.
Beim Start stellt dieselbe Zustandslogik den Zustand aus dem Journal wieder her.
Nur Journal und Einlagen der aktiven Sitzung werden zusätzlich vollständig im Arbeitsspeicher gehalten.

Schreibfehler verhindern weitere Ereignisse bis zum Neustart. Ein beschädigtes
Journal wird beim Start mit Fehler abgewiesen, nicht automatisch gekürzt.
Betriebshinweise stehen in [API.md](API.md#speicherung-und-fehlerbehandlung).

## Aufzeichnungssitzungen

`sessions.json` enthält die aktive UUID und die Namen sowie UTC-Start-/Endzeiten
aller Sitzungen. Pro UUID liegt ein unverändertes JSONL-Journal mit eigenem
Sequenzraum unter `sessions/UUID/`; dort liegen auch die Korrekturbelege. Gemeinsame
`config.json` und `calibrations/` bleiben außerhalb. Ein datenordnerweiter
`flock` auf `sessions.lock` ergänzt den bestehenden Journal-Lock über Wechsel hinweg.

Ein Wechsel prüft zuerst den erwarteten Sitzungsbezug und verlangt bei Belegung
oder offener Einlage eine ausdrückliche Bestätigung. Danach wird ein neuer
Ereigniskern mit gleicher Bahnanzahl vorbereitet. Nur administrative Quellensperren
werden durch vorhandene `mode`-Befehle übernommen; alle Sportler- und Zielzustände
beginnen leer/unbekannt. Der zentrale Reducer bleibt unverändert.

Der neue Journalstand wird synchronisiert; anschließend veröffentlicht ein
`os.replace` mit `fsync` den vollständigen Sitzungsindex atomar. Die serverseitige
Prüfung, Speicherung und Übernahme enthalten kein `await`. Ein Fehler am Index
sperrt weitere Eingaben bis zum Neustart. Der gespeicherte aktive Verweis entscheidet
beim Start. Fehlt der Index bei vorhandenen Sitzungsordnern oder fehlt das aktive
Journal, startet der Server mit Fehler und erzeugt keinen leeren Ersatz.
Vor Veröffentlichung abgebrochene Vorbereitungen können unreferenzierte Ordner
hinterlassen; sie bleiben unberührt und werden nicht als Sitzungen angeboten.

Der alte Auswertungstask wird abgebrochen, sein bereits gestarteter OpenCV-Thread
kann noch fertig rechnen, aber nichts mehr veröffentlichen. Ein neuer Task mit
leeren Trackern ignoriert Bilder von vor Sitzungsbeginn und stabilisiert neue
Grundbeobachtungen. Jeder veröffentlichende Pfad prüft den Sitzungsbezug.
WebSocket-Entwürfe werden geleert, vollständige Zustände sofort angekündigt.
Archive werden ausschließlich gelesen; Belegung und Einlagen darin werden nicht
nachträglich künstlich abgeschlossen.

Es gibt keine automatische Migration alter Testinstallationen und keine
Übergangsschnittstelle ohne Sitzungskennung. Der einmalige manuelle Schritt steht
in der [README](../README.md#aufzeichnungssitzungen). Das ist eine bewusste
Entscheidung für die aktive Entwicklungsphase ohne produktive Installationen.
Systemlogs bleiben unabhängig davon in journald.

## Quellen und menschliche Priorität

Die Tablet-Bedienung hat keine Betriebsartwahl. Jede Scheibe ist immer manuell
korrigierbar. `automatic_targets` enthält tatsächliche Beobachtungen,
`manual_targets` die aktiven Korrekturen, `targets` den verbindlichen Zustand.
Automatische Einzelereignisse aktualisieren nur ihr Ziel; so können sie weder
andere Korrekturen noch manuell bestätigte Vorbereitung überschreiben. Unbekannte
Werte bleiben sichtbar. Es entstehen keine Schuss-/Fehlschussmeldungen.

Das bisherige API-Feld `mode` bleibt für bestehende Clients und Journale erhalten.
`automatic` und `mixed` erlauben beide automatische Beobachtungen mit manueller
Priorität. `manual` sperrt deren Wirksamkeit administrativ; Beobachtungen werden
weiter gespeichert. Eine Quellensperre erzeugt keine künstlichen manuellen
Übersteuerungen. Nur echte Einzelkorrekturen bleiben nach erneuter Zulassung
vorrangig; andere Ziele folgen wieder der Quelle. `/admin` verwendet den bestehenden Modusbefehl mit einer
Checkbox. Die Voreinstellung benötigt weder Kamera noch Änderung. Bereits
vorhandene Quellensperren werden beim Upgrade nicht ungefragt aufgehoben.

Eine bestätigte Rückstellung beendet alte Korrekturen, setzt alle effektiven
Stellungen auf aufgerichtet und startet eine neue Beobachtungsgrundlage.
Der vorhandene `automatic_baseline_pending`-Marker genügt dabei auch als Hinweis:
Solange noch keine bekannte neue Kamerabeobachtung vorliegt, bleibt die
menschlich bestätigte Stellung wirksam. Eine fehlende Kamera kann die Vorbereitung
somit nicht verhindern. Bekannte Grundbeobachtungen übernehmen wieder die
nicht korrigierten Ziele, ohne rückwirkende Fälle oder Rückstellungen auszulösen.
Aktive Einzelkorrekturen bleiben auch nach Wiederverbindung vorrangig.

Vor einer Belegung erfasste manuelle Werte dürfen bei der späteren BIB-Eingabe
nicht mit Korrekturen des Vorgängers verwechselt werden. Der Kern merkt deshalb
die betroffenen Zielnummern in `unassigned_manual_target_ids`, solange weder eine
aktive Einlage noch eine Belegung besteht. Beim nächsten Einlagenbeginn bleiben
diese Werte erhalten und sind danach gebunden; die übrigen alten Übersteuerungen
werden bereinigt. Eine Rückstellung oder ausdrückliche Freigabe eines einzelnen
Ziels beendet auch diese ungebundene Korrektur. Der Marker entsteht aus denselben
Journalbefehlen wie die Zielwerte, ohne neue Eingabeoption oder Ereignisart.

Bei einer neuen Einlage enden Übersteuerungen des Vorgängers. Ohne zwischenzeitliche
Rückstellung werden zuvor korrigierte Ziele zunächst unbekannt; ein alter
Kamerawert wird nicht als neuer Beleg eingesetzt. Der vorhandene Generationszähler
fordert frische Grundbeobachtungen an und verwirft noch laufende Bildauswertungen.
Es gibt keine zusätzliche Prioritäts-Engine und keine neue Zustandsliste.
Die ausdrückliche Freigabe eines einzelnen Ziels bleibt als API-Befehl erhalten;
im regulären Tablet-Ablauf ist sie nicht erforderlich.

Der kompakte Tablet-Erfassungsstatus wird je Bahn aus dem bestehenden laufenden
Tracker abgeleitet: aktuelle Quellenzuordnung und Freigabe, Kamera-Bildverfügbarkeit,
Tracker-Generation und bestätigte bekannte Werte aller fünf Ziele. Noch unbestätigte
oder unsichere Klassifikationen ergeben keinen aktiven Status; bekannte Journalwerte
nach Neustart ebenfalls nicht. Zwei Bahnen derselben Kamera können unterschiedliche
Status haben. `capture.lanes` transportiert diese flüchtige Ableitung im vorhandenen
REST-/WebSocket-Zustand. Die vorhandene Erfassungsschleife vergleicht die Status
nach jedem Auswertungsschritt mit dem vorherigen Stand. Nur bei Änderungen weckt
sie die bestehenden WebSocket-Empfänger; das Ende der Auswertungsaufgabe meldet
deren Ausfall ebenfalls unmittelbar. Zusätzlich vergleicht sie mit dem zuletzt
ausgelieferten Stand: Ein Status, den ein Client zwischen zwei Durchläufen erhalten
hat, den die Schleife selbst aber nie beobachtet hat, wird so beim Zurückwechseln
ebenfalls korrigiert. Statuswechsel warten somit nicht auf das
Fünf-Sekunden-Lebenszeichen. Es gibt keine zusätzliche Schleife, Bildraten-Pushes,
Zeitgrenzen, persistierten Zustände oder Eingriffe in die Klassifikation. Die Kachel zeigt aktive
Einzelkorrekturen aus `manual_targets` unabhängig vom Erfassungsstatus an.

Manuelle Korrekturen enthalten im Journal den automatischen Vergleichswert,
Beobachtungszeit und vorherigen effektiven Zustand. Nach Möglichkeit speichert
`app.py` den Gesamt-ROI des vorhandenen aktuellen Bildpuffers unter
`sessions/SITZUNGS-ID/corrections/SEQUENZ.jpg` mit JSON-Begleitdatei. Deren Bildempfangszeit ist nicht
zwingend die Zeit der letzten stabilisierten Beobachtung. Fehlende Bilder verhindern
keine Eingabe; Speicher-/Kodierungsfehler werden protokolliert. Kein weiterer
Bildpuffer, Training oder Analysedienst. Manuelle Erfassung und Kamera sind
implementiert; Sensorhardware und Sensoradapter bleiben geplant.

## Einheitlicher Schießstandablauf

`occupy` belegt auch ohne BIB und beginnt oder übernimmt die aktuelle Einlage.
`assign` kann aus Kompatibilitätsgründen weiterhin direkt belegen. Der getrennte
Belegungszähler erhält verspätete BIBs und schützt vor konkurrierenden Zuordnungen.
`release` beendet die Belegung; Rückstellung und Zielkorrektur geben sie nicht frei.
Tablet-Korrekturen senden `start_bout: false` und erzeugen keine Einlagengrenzen.
Ältere Clients können weiterhin durch einen ersten manuellen Fall eine Einlage
beginnen; das ist kein automatisch beobachteter Fall.

Ein tatsächlicher automatischer Fall kann wie bisher eine unzugeordnete Einlage
beginnen. Nach vollständiger Rückstellung und neuem Fall bleibt sie ausdrücklich
ohne BIB, selbst wenn die vorherige Belegung verspätet freigegeben wird. Diese
Trennung schützt vor Zuordnung zum falschen Sportler. Eine Teilrückstellung
beendet die Einlage dagegen nicht mehr. Erst ein Übergang nach oben und fünf
bekannt aufgerichtete automatische Ziele bestätigen die vollständige Rückstellung.
Grundbeobachtungen und Unterbrechungen verwerfen eine unvollständige Bestätigung;
fünf unverändert aufgerichtete Scheiben reichen nicht. Explizites `reset` bezeichnet
wie bisher eine bereits bestätigte vollständige Rückstellung.

Belegung verbraucht die Vorbereitung. `status` wird abgeleitet: Belegung hat
Vorrang (gelb); unbelegt, bestätigt vorbereitet und fünf wirksam aufgerichtete
Scheiben sind bereit (grün); die übrigen freien Bahnen benötigen Rückstellung
(grau). Der API-Snapshot berücksichtigt Kamera-/Erfassungsausfälle sofort für
kameragestützte Bereitschaft. Eine ausdrückliche menschliche Vorbereitung bleibt
ohne Kameranachweis gültig. Die Darstellung enthält stets auch Statuswörter.

Große Scheiben, Belegen/Verlassen und Rückstellbestätigung haben feste Positionen.
Bei unbekannter Stellung bietet ein Tipp zwei beschriftete Auswahlflächen;
bekannte Stellungen lassen sich direkt umschalten. Optionen enthalten die
Einlagenhistorie, keine Moduswahl, Vergleichsreihen oder Unbekannt-Eingabe.
Ein Bedienzähler schützt Korrekturen gegen andere Bediener und Einlagengrenzen,
ohne jedes Kamerabild als Konflikt zu behandeln. Auch Freigabe nach bereits
geschlossener Einlage macht eine noch offene Zielauswahl ungültig.

Neue Journalereignisse tragen `rules_version: 3`. Fehlendes Feld bedeutet die
historischen Regeln (`1`); `2` kennzeichnet den Ablauf aus PR #10. Kleine
Kompatibilitätszweige im selben Reducer erhalten bei alten Ereignissen insbesondere
Teilrückstellungen, Revisionen, Zielwerte und die frühere Bereinigung beim
Einlagenbeginn. Regel `3` übernimmt ungebundene manuelle Eingaben beim Beginn.
Das Journal wird weder migriert noch umgeschrieben. Nach Wiederherstellung gelten
für neue Befehle die neuen Regeln. Details und Downgrade-Grenzen: [API.md](API.md).

## Tablet-Bedienung und Mehrbenutzerbetrieb

`/` liefert die Tablet-Oberfläche. Alle Bedienplätze arbeiten mit demselben
Serverzustand; Sprache und Bahnauswahl liegen je Browser/Origin in `localStorage`.
Die Auswahl ist ein Anzeigefilter und darf sich überschneiden. Große
Bedienelemente und flexible Spalten unterstützen Hoch- und Querformat.
`translations.js` enthält English als Standard sowie Deutsch und Čeština für den
Tablet-Bedienplatz. Sprachwechsel setzen `html.lang` auf `en`, `de` oder `cs`.
Die vier eigenen HTML-Seiten unterbinden zusätzliche automatische
Browserübersetzung mit `translate="no"`, `notranslate` und Google-Metatag.
Monitor, Administration und Kalibrierung sind derzeit deutsch und verwenden
`lang="de"`. Verbindliche Sportbegriffe und ihre offiziellen Fundstellen stehen
im [Terminologieverzeichnis](TERMINOLOGIE.md); technische Zustands- und
Softwarebezeichnungen werden dort von IBU-Terminologie getrennt.

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

`--simulation` aktiviert zusätzliche Übungsdialoge und die reservierte Quelle
`simulator` am Beobachtungseingang. Der Modus wird beim Serverstart festgelegt.
Die Zielsimulation prüft den gesehenen Zustand über die volle Bahnrevision;
reguläre manuelle Korrekturen verwenden den Bedienzähler, Belegungsbefehle den
getrennten Belegungszähler.

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
ein Rückwechsel setzt einen zum Datenformat passenden Programmstand voraus.
Für den Wechsel vom bisherigen Testdatenordner zur Sitzungsablage ist der
manuelle Schritt aus der README erforderlich. Eine Rückwärtskompatibilität zu
älteren Entwicklungsversionen wird nicht zugesichert. Sicherungen und alte
Programmstände werden nicht automatisch gelöscht.
Ein Dateilock verhindert parallele Installationen/Upgrades.

## Kontrollmonitor

`/monitor` liest vollständige Zustände über `/ws` und besitzt keine Bedienfunktionen.
Er zeigt dieselben drei Kachelfarben wie das Tablet, die belegende Startnummer und
alle fünf wirksamen Stellungen. Ein kurzer Hinweis kennzeichnet ausgefallene oder
unklare Erfassung. Automatische Falllisten bleiben für bestehende API-Verbraucher
erhalten; die Übersicht zeigt keine technischen Vergleichswerte oder Fallzählungen.

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
kann bei vollständiger Rückstellung über den Kern die Einlage beenden. Ein Sportlerwechsel während eines
Ausfalls bleibt unbestimmt und benötigt die vorhandene ausdrückliche Bedienung.
`observed_at` ist die serverseitige Bildempfangszeit des bestätigenden Bildes,
kein Schusszeitpunkt. Defekte Kalibrierungen betreffen nur ihre Bahn, werden
protokolliert und in der Kalibrierungs-API sichtbar. Ein unerwartet beendeter
Auswertungstask oder gesperrter Ereignisspeicher macht `/api/health` fehlerhaft.


## Externer Datenvertrag

Die REST-/WebSocket-Schnittstellen verwenden API-Version 2 mit verpflichtendem
Sitzungsbezug für Erfassungsbefehle. Kein KES-Emulator und kein zusätzlicher Port: externe Anzeigen
verwenden dieselben vollständigen Zustände wie die Browser. `api_version` trennt
den Integrationsvertrag von der Anwendungsversion; `instance_id` kennzeichnet
einen Serverstart, `session_id` eine über Neustarts fortgesetzte Aufzeichnung. Technischer Erfassungsstatus und bereinigte Kameradaten stehen
im vorhandenen Zustand, weil eine unveränderte Zielstellung allein keine Aussage
zur Verfügbarkeit erlaubt. Das ergänzt konkret fehlende Integrationsdaten, ohne
einen zweiten Ereigniskanal oder ein Adapterframework einzuführen.

`sequence` bleibt die Reihenfolge dauerhaft akzeptierter Befehle. Lebenszeichen
und Kamerastatus ändern sie nicht. Langsame Empfänger erhalten aktuelle
vollständige Zustände; das Journal kann separat gelesen werden. Der Monitor
kennzeichnet `health: error` ausdrücklich als gestörte Erfassung. Manuelle
Weiterarbeit bleibt bei ausgefallener Optik möglich; ein Speicherfehler verhindert
dagegen weitere Eingaben.
Vertrag, Wiederverbindung und Beispielclient stehen ausschließlich in [API.md](API.md#externe-integration-eigenständige-quelle-btv).
Die spätere GFX-Integration ist in Issue #102 dokumentiert; GFX-Code wurde im
Rahmen dieser Versionen nicht verändert.
