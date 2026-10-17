# Ereigniskern und Schnittstellen, Version 0.3

Die vollständigen JSON-Schemata stehen bei laufendem Server unter `/docs` und
`/openapi.json`. Technische Zustandsbezeichner bleiben englisch. Installation und
Start: [README](../README.md). Komponenten und Datenfluss:
[ARCHITECTURE.md](ARCHITECTURE.md).

REST und WebSockets sind implementiert. Kamera-/Sensoradapter
sind noch nicht vorhanden; der Beobachtungseingang kann bereits integriert werden.

| Schnittstelle | Aufgabe |
|---|---|
| `GET /api/state` | Gemeinsamer Zustand aller Bahnen und Schießeinlagen |
| `GET /api/events?after=0&limit=1000` | Journal nach Sequenznummer, höchstens 1.000 Einträge pro Abruf |
| `POST /api/observations` | Einheitlicher Eingang für Simulator, Kamera und Sensor |
| `PUT /api/lanes/{lane_id}/bib` | Startnummer zuordnen oder ausdrücklich korrigieren |
| `POST /api/lanes/{lane_id}/release` | Bestimmte Einlage freigeben |
| `WS /ws` | Anfangszustand und vollständige Zustände nach Änderungen |
| `GET /api/lanes/{lane_id}/calibration` | Gespeicherte Grundkalibrierung oder `null` |
| `POST /api/lanes/{lane_id}/calibration` | Standbild erkennen und erfolgreiche Kalibrierung speichern |
| `POST /api/lanes/{lane_id}/calibration/align` | Zielbereiche in neuem Standbild nachführen |

Beobachtungs-, Zuordnungs- und Freigabebefehle senden JSON. Erfolgreiche Befehle
liefern `{"event": ..., "state": ...}` mit dem gespeicherten Ereignis und dem
aktuellen Zustand. Die `lane_id` im Befehl muss bei Bahnendpunkten zur URL passen.
Jedes Journalereignis enthält `sequence`, den serverseitigen Zeitpunkt
`accepted_at` und den gespeicherten Befehl `command`.
`bib` ist eine positive Ganzzahl; das Tablet beschränkt die Eingabe auf 15 Ziffern,
damit JavaScript sie exakt darstellen kann.

## Beobachtungen

Beispiel für `POST /api/observations`:

```json
{
  "event_id": "kamera-1-bild-123-ziel-3",
  "kind": "target",
  "lane_id": 1,
  "target_id": 3,
  "state": "fallen",
  "source": "kamera-1",
  "observed_at": "2026-10-17T12:00:01.123Z"
}
```

Ziele sind 1–5 von links nach rechts im kalibrierten Kamerabild. Zustände:
`standing`, `fallen`, `unknown`; initial sind alle fünf Ziele `unknown`.
`unknown` bedeutet fehlende/unsichere Beobachtung,
nicht Fehlschuss. `last_known_targets` bewahrt die letzte bekannte Stellung,
damit eine Verdeckung keine künstliche neue Einlage erzeugt oder eine Rückstellung
verschluckt. Es gibt keine automatische Ableitung von `shot`, `hit` oder `miss`.

Eine bestätigte vollständige Rückstellung verwendet `kind: "reset"` und lässt
`target_id` sowie `state` weg. Sie setzt alle fünf Zustände auf `standing`.
Eine einzelne Rückkehr von bekannt `fallen` zu `standing` beendet ebenfalls die
aktuelle Einlage, verändert aber ausschließlich dieses Ziel.

Quellen senden bestätigte Zustandsbeobachtungen, keine Videoframes oder geschätzten
Schusszeitpunkte. Die Beobachtungszeit braucht eine Zeitzone. Sie muss pro Bahn
aufsteigend sein; verschiedene Ziele dürfen dieselbe Bildzeit haben. Für dasselbe
Ziel muss eine neue Beobachtung zeitlich später liegen. Verspätete Pakete werden
mit HTTP 409 abgelehnt und niemals nachträglich einer anderen Einlage zugerechnet.
Quellen einer Bahn müssen deshalb eine gemeinsame Zeitbasis und geordnete
Übermittlung verwenden. Bildstabilisierung und Auswahl der zuständigen Quelle
sind Aufgaben der späteren Erfassungsadapter.

Die reservierte Quelle `simulator` ist nur mit der Startoption `--simulation`
zulässig (sonst HTTP 403). Andere Quellen nutzen denselben Beobachtungseingang.
Der optionale Header `X-Lane-Revision` enthält die beim Öffnen der manuellen
Zielbedienung bekannte Bahnrevision. Bei Abweichung wird der Befehl mit 409
abgelehnt. Identische Wiederholungen einer bereits akzeptierten Ereigniskennung
bleiben idempotent, auch wenn die Revision inzwischen erhöht wurde.
Der Tablet-Simulator verwendet eine aufsteigende Beobachtungszeit: das Maximum
aus Tablet-Uhrzeit und letzter Bahnbeobachtung plus einer Millisekunde.

Alle Befehle akzeptieren eine `event_id`. Wiederholungen mit identischem Inhalt
und derselben Kennung liefern das ursprüngliche Ereignis, ohne nochmals zu buchen.
Anderer Inhalt bei gleicher Kennung ergibt 409. Für zuverlässige Wiederholungen
muss der Client die Kennung und den gesamten ursprünglichen Befehl aufbewahren;
ohne Kennung erzeugt der Server eine UUID.

### Simulator für die Kommandozeile

Bei laufendem Server mit `--simulation` in einem zweiten Terminal ausführen:

```bash
.venv/bin/python -m biathlon_target_vision.simulator reset 1
.venv/bin/python -m biathlon_target_vision.simulator hit 1 3
.venv/bin/python -m biathlon_target_vision.simulator standing 1 3
.venv/bin/python -m biathlon_target_vision.simulator unknown 1 5
```

`hit 1 3` sendet ausschließlich „Ziel 3 auf Bahn 1 gefallen“. `reset` benötigt
keine Zielnummer; die anderen Aktionen benötigen eine Nummer von 1 bis 5.
`--url http://127.0.0.1:8092` wählt einen anderen Server.

## Startnummern und Freigabe

`GET /api/state` enthält `lanes` (Schlüssel beispielsweise `"1"`) und `bouts`.
Jede Bahn hat `revision`, `assignment_revision`, `current_bout_id` und `occupied_bout_id`.
Eine Einlage entsteht bei expliziter Belegung oder der ersten neu beobachteten
gefallenen Scheibe. Ihre Kennung entspricht der auslösenden `event_id`.
`observations` verweist auf unveränderliche Journalereignisse; `bib` ist die
aktuelle, gegebenenfalls korrigierte Zuordnung. `started_sequence` bezeichnet das
Journalereignis, das diese Einlage begonnen hat.

Für aktuelle Integrationen denselben Belegungsabgleich wie das Tablet verwenden:

1. Zustand laden und die Zähler der Bahn sowie die globale `sequence` übernehmen.
2. Bei noch fehlender Einlage beispielsweise `PUT /api/lanes/1/bib` mit
   `{"lane_id":1,"bib":42,"expected_revision":0,"expected_assignment_revision":0,"bout_after_sequence":0}` senden.
3. Für eine bekannte Einlage deren `bout_id` angeben; für eine Korrektur etwa
   `{"lane_id":1,"bib":43,"bout_id":"EINLAGENKENNUNG","expected_revision":1,"expected_assignment_revision":1}`.
4. Freigeben über `POST /api/lanes/1/release` mit
   `{"lane_id":1,"bout_id":"EINLAGENKENNUNG","expected_revision":2,"expected_assignment_revision":2}`.

Die Zahlen sind Beispiele für aufeinanderfolgende Befehle ohne Beobachtungen;
Clients müssen den tatsächlich gesehenen Stand senden. `revision` steigt mit
jedem akzeptierten Bahnereignis, `assignment_revision` nur bei bestätigten
Zuordnungen und Freigaben. Ist `expected_assignment_revision` gesetzt, prüft der
Kern diesen Zähler anstelle von `expected_revision`. Treffer und Rückstellungen
lösen dadurch auch während des HTTP-Transports keinen Revisionskonflikt aus.

Für ältere Clients bleibt `expected_revision` allein zulässig. Dann wird weiterhin
jede zwischenzeitliche Bahnänderung berücksichtigt. Das Feld ist auch bei Nutzung
des neuen Belegungszählers im Befehl erforderlich. Bestehende Journale bleiben
lesbar; optionale Standardwerte werden beim Vergleich identischer
Ereigniswiederholungen berücksichtigt.

Die Prüfung und Verarbeitung erfolgen gemeinsam im Ereigniskern. Bei 409 den
Zustand erneut laden und die gewünschte Änderung prüfen. Ein anderer Client darf
nicht unbemerkt überschrieben werden. Dieselbe Startnummer darf nicht gleichzeitig
mehrere Bahnen belegen. Der Browser gleicht offene Eingaben anhand ihrer konkreten
Einlage, deren offizieller Startnummer und der betroffenen Belegung ab; Änderungen
an einer anderen historischen Einlage machen den Entwurf nicht ungültig.

Ohne `bout_id` wird nur die eindeutig aktuelle Einlage zugeordnet, andernfalls
eine neue begonnen. Gibt es eine frühere geschlossene Einlage ohne Startnummer,
ist eine ausdrückliche Auswahl erforderlich. Korrekturen vorhandener Startnummern
benötigen ebenfalls `bout_id`. Eine abgeschlossene Einlage kann nachträglich
zugeordnet werden, ohne die aktuelle Belegung zu verändern.

Beginnt die Eingabe bei noch fehlender Einlage, sendet das Tablet alternativ
`bout_after_sequence` mit der globalen `sequence` beim Öffnen. Der Befehl betrifft
die erste danach begonnene Einlage dieser Bahn, nicht die zum Empfang zufällig
neueste. Sobald deren Kennung bekannt ist, sendet das Tablet stattdessen `bout_id`.
Die Anzeige nennt die ausgewählte Einlage und ob sie inzwischen abgeschlossen
ist. Ohne zwischenzeitlichen Beginn wird weiterhin eine Einlage angelegt.
Bereits beim Öffnen vorhandene unzugeordnete abgeschlossene Einlagen müssen
weiterhin ausdrücklich aus der Historie gewählt werden.

Rückstellung und Freigabe sind getrennt: Die Rückstellung schließt die Einlage,
lässt `occupied_bout_id` jedoch bestehen. Die nächste Einlage bleibt ohne
Startnummer, bis die alte Belegung freigegeben wurde. Die verspätete Freigabe
der alten Kennung schließt die neue Einlage nicht. Eine Freigabe verändert keine
Zielstellungen. Ohne Rückstellung oder Freigabe kann das System einen tatsächlichen
Sportlerwechsel nicht erkennen; es errät keine Grenzen aus Zeitabständen.

## Synchronisierung

WebSocket-Nachrichten entsprechen dem REST-Zustand plus `"type":"state"`,
`editor_id` und `drafts` (siehe unten).
Das zusätzliche Feld `simulation` gibt den beim Serverstart gewählten Modus an.
`sequence` ist die letzte persistierte globale Ereignisnummer. Langsame Browser
erhalten den neuesten vollständigen Zustand; Zwischenstände dürfen zusammenfallen.
Das verlustfreie Ereignisprotokoll wird bei Bedarf über `/api/events` nachgeladen.
Nach Verbindungsabbruch neu verbinden; die erste Nachricht enthält den aktuellen Stand.
Auch ohne Änderungen wird spätestens alle fünf Sekunden ein Zustand gesendet;
dadurch ändern sich weder Sequenz noch Bahnrevision. Die Tablet-Anwendung prüft
dieses Lebenszeichen: Nach zwölf Sekunden ohne Zustand erneuert sie die Verbindung.
Auch die Rückkehr aus einem Hintergrund-Tab löst eine neue Verbindung aus.
Bei Verbindungsverlust sind Bestätigungen deaktiviert; erneute Versuche erfolgen
mit 0,5 bis maximal 5 Sekunden Abstand. Ein neuer Verbindungsanfang ersetzt
den gesamten Browserzustand; ältere HTTP-Antworten dürfen einen neueren Zustand
innerhalb derselben Verbindung nicht zurücksetzen.

Startnummerntexte bleiben während einer Unterbrechung lokal erhalten und
bearbeitbar. Nach Wiederverbindung werden offizielle Zuordnung und Belegung mit
dem beim Öffnen beziehungsweise zuletzt ausdrücklich geprüften Stand verglichen.
Ein Konflikt erhält den Text und verlangt „Aktuellen Zustand prüfen“ sowie eine
anschließende ausdrückliche Bestätigung. Zielbeobachtungen erfordern das nicht.
Es werden keine Befehle automatisch nachgesendet. Texte überleben kein Neuladen
der Seite; `localStorage` enthält ausschließlich Sprache und Bahnauswahl.

### Flüchtige Eingabeentwürfe

Jede WebSocket-Verbindung erhält eine serverseitige `editor_id`. Sie dient als
sichtbare Tablet-Nummer, nicht als Anmeldung oder dauerhafte Gerätekennung.
Ein aktiver Eingabebereich sendet bei Änderungen und spätestens alle fünf Sekunden:

```json
{"type":"draft","lane_id":1,"bout_id":null,"value":"42"}
```

`value` ist eine Zeichenkette mit höchstens 15 ASCII-Ziffern, auch leer;
`bout_id` ist `null` oder eine bestehende Einlage derselben Bahn. Die zugehörige
`editor_id` setzt ausschließlich der Server. Jeder Verbindung gehört höchstens
ein Entwurf. Andere Verbindungen können ihn weder ersetzen noch löschen.
`drafts` in jedem WebSocket-Zustand enthält die aktuellen Entwürfe einschließlich
`editor_id`, `lane_id`, `bout_id`, `value`. Clients zeigen nur Entwürfe ihrer lokal
ausgewählten Bahnen und kennzeichnen sie ausdrücklich als unbestätigt.

Beim Verlassen des Eingabebereichs oder Schließen des Dialogs sendet der Browser
`{"type":"draft_clear"}`. Bestätigung, Verbindungsende oder mehr als 15 Sekunden
ohne Erneuerung entfernen den Entwurf ebenfalls. Der Ablauf wird spätestens beim
nächsten Fünf-Sekunden-Zustand sichtbar. Die Zeitbegrenzung entfernt lediglich
alte Anzeigen; sie ist kein Lock und keine Reservierung. Nach Wiederverbindung
hat das Tablet eine neue Nummer und sendet seinen weiterhin offenen Text erneut,
solange der Eingabebereich aktiv ist. Fehlerhafte Entwurfsnachrichten beenden die
Verbindung mit WebSocket-Code 1008.

Entwürfe verändern weder `sequence`, Bahnrevisionen, Belegung noch Ereignisjournal.
`GET /api/state` enthält ausschließlich den offiziellen Zustand und den Simulationsmodus.

## Speicherung und Fehlerbehandlung

Ereignisse liegen im gewählten Datenordner in `events.jsonl`, Kalibrierungen unter
`calibrations/`. Die Bahnanzahl wird beim ersten Start gespeichert; eine spätere
widersprechende Angabe wird abgelehnt. Pro Datenordner ist genau ein Serverprozess
zulässig. Für eine neue Veranstaltung einen neuen Datenordner verwenden und den
alten aufbewahren. Speicheraufbau und Wiederherstellung beschreibt
[ARCHITECTURE.md](ARCHITECTURE.md#ereigniskern-und-speicherung).

Ungültige Befehlsfelder liefern HTTP 422, fachliche Konflikte HTTP 409 mit einer
Erklärung in `detail`. Bei einem Konflikt den aktuellen Zustand laden und die
beabsichtigte Änderung prüfen, statt sie ungeprüft zu wiederholen.

Bei Schreibfehlern liefert die API 503 und nimmt bis zum Neustart keine weiteren
Ereignisse an. Bei beschädigtem oder abgebrochenem Journal startet der Server mit
einer Fehlermeldung nicht; er verwirft keine Daten automatisch. Zur Reparatur den
Server stoppen, den gesamten Datenordner sichern und die gemeldete Zeile prüfen.
Eine unvollständige letzte Zeile nur nach Prüfung an der Sicherung entfernen;
vollständige Ereignisse nicht löschen.

## Kalibrierung

Die POST-Endpunkte nehmen Multipart-Daten an: `image` als Bilddatei, zur ersten
Kalibrierung zusätzlich `quad` als JSON-Liste mit vier Originalbildkoordinaten
in der Reihenfolge oben links, oben rechts, unten rechts, unten links.
Die Browseransicht exportiert genau die angezeigten Pixel, damit EXIF-Ausrichtung
keine abweichenden Koordinaten verursacht. Grenze: 10 MiB und 20 Megapixel.

Erfolg liefert fünf nummerierte Polygone und Mittelpunkte im Originalbild.
Die Grundkalibrierung liegt atomar gespeichert in `data/calibrations/lane-N.json`.
Fehler liefern 422 mit Erklärung und überschreiben keine gültige Kalibrierung.
`align` liefert automatisch neu gefundene Zielbereiche samt Versatz relativ zur
Grundkalibrierung. Es verändert diese nicht. Zulässig sind höchstens 24 Pixel
beziehungsweise 20 % des Zielabstands, je nachdem, was kleiner ist. Größere oder
uneinheitliche Bewegungen, andere Auflösung und unklare Zielreihen benötigen eine
neue Kalibrierung. Das ist eine Standbildprüfung; ein laufender Kameratreiber
kann dieselbe Funktion später pro geeigneter Beobachtung verwenden.

## Externe Integration: eigenständige Quelle BTV

BTV liefert ausschließlich tatsächliche Zielbeobachtungen und bestätigte
Zuordnungen. Es ist keine KES-Quelle. KES-Telegramme, Schuss-/Fehlschussereignisse,
Schusszähler, Anschlag und Ergebnisse werden nicht erzeugt. Die geplante
KES-TCP-Ausgabe ist verworfen. Die Original-KES-Dokumentation bleibt als Referenz
für die Abgrenzung erhalten. GFX integriert BTV später als eigene Quelle neben
KES und HORA; [Integrationsauftrag #102](https://github.com/richtertoralf/gfx-engine/issues/102).

`GET /api/health` liefert `status: "ok"` und `version` für Start-/Upgradeprüfung.
Einlagen enthalten zusätzlich `fallen_target_ids`: eindeutige Zielpositionen,
deren Fall während dieser Einlage beobachtet wurde, unabhängig von späterer
Unsicherheit. Alte Journale erhalten das Feld durch Replay. Der Monitor zeigt
die Anzahl für `current_bout_id`; ohne aktuelle Einlage null. Es ist kein
Schusszähler und keine Ergebnisberechnung.
