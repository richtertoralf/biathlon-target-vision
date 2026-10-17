# Ereigniskern und Schnittstellen, Version 0.7

Die validierten Befehlsmodelle stehen bei laufendem Server unter `/docs` und
`/openapi.json`; Zustandsvertrag und Kamerafelder sind hier dokumentiert. Technische Zustandsbezeichner bleiben englisch. Installation und
Start: [README](../README.md). Komponenten und Datenfluss:
[ARCHITECTURE.md](ARCHITECTURE.md).

REST, WebSockets, RTSP-Kameraeingang und optische Zielzustandsauswertung sind
implementiert. Sensoradapter folgen.

| Schnittstelle | Aufgabe |
|---|---|
| `GET /api/state` | Gemeinsamer Zustand aller Bahnen und Schießeinlagen |
| `GET /api/events?after=0&limit=1000` | Journal nach Sequenznummer, höchstens 1.000 Einträge pro Abruf |
| `POST /api/observations` | Einheitlicher Eingang für Simulator, Kamera und Sensor |
| `PUT /api/lanes/{lane_id}/bib` | Startnummer zuordnen oder ausdrücklich korrigieren |
| `POST /api/lanes/{lane_id}/release` | Bestimmte Einlage freigeben |
| `PUT /api/lanes/{lane_id}/mode` | Betriebsart dieser Bahn wählen |
| `POST /api/lanes/{lane_id}/manual-target` | Ziel manuell erfassen/korrigieren |
| `POST /api/lanes/{lane_id}/override-release` | Ziel wieder automatisch steuern |
| `POST /api/lanes/{lane_id}/reset` | Physische vollständige Rückstellung bestätigen |
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

### Grundbeobachtungen und optische Auswertung

`baseline` ist ein optionales boolesches Feld (Standard `false`) für `kind: target`.
Eine Grundbeobachtung aktualisiert die automatischen Werte und, soweit nicht
manuell übersteuert, `targets`/`last_known_targets`, beginnt/schließt
aber keine Einlage und erhöht nicht `fallen_target_ids`. Damit können erste
Bilder nach Start oder Kameraausfall tatsächliche Stellungen zeigen, ohne einen
neu beobachteten Fall zu behaupten. `baseline: true` mit `kind: reset` ist unzulässig.
Alte Journale bleiben mit dem Standardwert unverändert lesbar. Bei gespeicherten
Ereignissen steht die Kennzeichnung als optionales `event.baseline: true` neben
`command`, damit ältere Programme das weiterhin unveränderte Befehlsformat lesen
können. Externe Journalverbraucher müssen diesen Marker für die Interpretation
von Übergängen berücksichtigen; vollständige Zustände sind davon unabhängig.

Der Kameraadapter verwendet `source: "camera:KENNUNG"` und serverseitige
Bildempfangszeiten. Ein beobachteter Übergang nach unten bleibt eine
Zielbeobachtung `kind: target, state: fallen`, kein `shot`/`miss`-Ereignis.
Rückstellungen werden als bestätigte Rückkehr nach oben über dieselbe Logik
verarbeitet. Verbindungsabbrüche liefern unbekannte Stellungen; nach Wiederkehr
folgen neue Grundbeobachtungen. Während der Unterbrechung liegende Übergänge oder
Einlagengrenzen werden nicht rekonstruiert. Der Monitor zählt ausschließlich
eindeutige beobachtete Fälle innerhalb seiner aktuellen Einlage.

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

## Betriebsart, manuelle Werte und Übersteuerungen

Diese Ergänzungen bleiben im additiven API-Vertrag 1. Bestehende lesende Clients
verwenden weiterhin **`lanes["N"].targets` als verbindlichen Live-Zustand**.
Eine Korrektur ist kein zusätzlicher Schuss oder beobachteter Fall. Clients, die
Journalereignisse lesen, müssen neue `kind`-Werte tolerieren und dürfen keine
Schusszählung aus Zustandseingaben konstruieren.

| Bahnfeld | Bedeutung |
|---|---|
| `mode` | `manual`, `automatic` (Voreinstellung), `mixed` |
| `targets` | Fünf wirksame Zustände, einschließlich manueller Priorität |
| `automatic_targets` | Fünf letzte automatische Beobachtungen; auch bei Übersteuerung aktuell |
| `manual_targets` | Fünf Werte oder `null`; im manuellen Modus Eingaben, sonst aktive Übersteuerungen |
| `observed_at`, `last_observed_at` | Zeit der automatischen Beobachtungen; keine Zeit manueller Eingaben |
| `last_known_targets` | Letzte bekannte wirksame Stellung; ersetzt aktuell `unknown` nicht |
| `automatic_last_known` | Letzte bekannte automatische Stellung, für Rückstellungserkennung |
| `control_revision` | Vergleichszähler für manuelle Ziel-/Modus-/Rückstellbefehle und Einlagengrenzen |
| `automatic_generation`, `automatic_baseline_pending` | Erfassungsinterne Wiederaufnahme; nicht von Clients setzen |

Ein manueller Wert, auch `unknown`, hat Vorrang. Im manuellen Modus werden die
beim Wechsel wirksamen Zustände übernommen. Automatische Beobachtungen ändern
dann nur die Vergleichsdaten. Rückwechsel aus Manuell behält alle manuellen Werte
als Übersteuerungen, bis sie ausdrücklich freigegeben werden. Das gilt auch beim
Wechsel nach Automatisch; neue Korrekturen benötigen Manuell oder Mischbetrieb.
Eine einzelne Korrektur nach oben beendet keine Einlage. Eine bestätigte
Rückstellung oder ausdrücklich neue Einlage entfernt alte Kameraübersteuerungen.
Rein manuelle Stellungen benötigen eine ausdrücklich bestätigte physische
Rückstellung; ein Moduswechsel behauptet keine solche Rückstellung.

Jeder neue Bedienbefehl enthält `lane_id`, optional `event_id` und zwingend den
zuletzt gesehenen `expected_control_revision`. Beispiel bei Revision 0:

```json
{"lane_id":1,"mode":"mixed","expected_control_revision":0}
```

An `PUT /api/lanes/1/mode` senden. Die folgenden Beispiele verwenden jeweils
die **aktuell zurückgelieferte** Revision, hier beispielhaft 1:

```json
{"lane_id":1,"target_id":3,"state":"fallen","expected_control_revision":1}
```

An `POST /api/lanes/1/manual-target` senden. Alle drei Zustände sind zulässig.
Die Korrektur gilt sofort, ohne zweiten Bestätigungsschritt. Im manuellen Betrieb
ist dies reguläre Erfassung ohne `--simulation` und ohne Kamera. Für
`POST /api/lanes/1/override-release` die Felder `lane_id`, `target_id` und
`expected_control_revision` senden. Die letzte automatische Beobachtung wird
sofort wirksam, auch wenn sie `unknown` ist. Es entsteht kein nachträglicher Fall.
Im Modus Manuell ist die Freigabe unzulässig (409).

`POST /api/lanes/1/reset` nimmt `lane_id` und `expected_control_revision`. Nur nach
physisch überprüfter Rückstellung verwenden: Alle Ziele gelten unmittelbar als
aufgerichtet, die Einlage wird geschlossen, die Belegung bleibt bestehen. Alte
Übersteuerungen enden. Die nächste bekannte automatische Beobachtung je Ziel
ist eine Grundbeobachtung, auch wenn ein REST-Adapter `baseline` nicht setzt.
Ein Kameraausfall beziehungsweise `unknown` verbraucht diese Markierung nicht.
Der vorhandene Kameraadapter beginnt beim Rückwechsel zusätzlich seine zeitliche
Stabilisierung neu und verwirft noch laufende Auswertungen des alten Betriebs.

Konkurrierende Bedienung oder Einlagengrenzen ergeben 409. Gewöhnliche automatische
Beobachtungen erhöhen `revision`, aber nicht `control_revision`; dadurch ist
Korrektur auch während laufender Bilder möglich. Einlagenbeginn oder bestätigte
Rückstellung erhöhen den Bedienzähler ebenfalls. Nach 409 Zustand neu laden und
prüfen; kein automatisches Nachsenden. Identische `event_id` bleibt idempotent.
Startnummern- und Freigabebefehle verwenden unverändert ihre bisherigen Modelle.

### Journal und Vergleichsbelege

Neue Befehlsarten: `mode`, `manual_target`, `override_release`, `manual_reset`.
Zeitpunkt ist `accepted_at` des Servers; Bahn/Ziel und manueller Wert stehen im
Befehl. `manual_input` enthält für manuelle Zielbefehle `mode`, `automatic_state`,
`automatic_observed_at`, `previous_effective_state` und `manual_state`.
`effective_targets` enthält den anschließenden wirksamen Bahnzustand. Bei
Beobachtungen kennzeichnet zusätzlich `effective_baseline: true` eine im Kern
wirksame Grundbeobachtung; der bisherige `baseline`-Marker bleibt unverändert.
Eine manuelle Korrektur und die spätere Aufhebung sind getrennte Journalbefehle.
`fallen_target_ids` erhält durch manuelle Eingaben keine neuen Einträge;
automatische Fälle werden nur für automatisch wirksame Ziele erfasst. Für eine
Live-Anzeige immer alle fünf `targets` lesen, niemals aus dieser Liste ableiten.

Optionaler Vergleichsbeleg im Datenordner: `corrections/SEQUENZ.jpg` und `.json`
mit Sequenz, Bahn/Ziel, Kamera, Bildempfangszeit und Vergleichswerten. Kein neuer
öffentlicher Bildendpunkt, keine zugesicherte Bildverfügbarkeit. Der Ausschnitt
stammt aus dem aktuellen Kamerapuffer, nicht notwendigerweise aus dem zur
stabilisierten Beobachtung gehörenden Bild. Ohne aktuelles Bild oder gültige
Kalibrierung wird nur das Journal geschrieben. Dateien mit Betriebssystemrechten
des Diensts wie andere persistente Daten behandeln.

Alte Journale werden ohne Migration gelesen. Neue 0.7-Bedienbefehle sind älteren
Programmständen unbekannt; nach ihrer Nutzung kein Downgrade auf dem laufenden
Journal. Die vor dem Upgrade erstellte Datensicherung bleibt separat erhalten.

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
neue Kalibrierung. Der Standbild-Endpunkt prüft alle fünf Ziele; die laufende Auswertung verwendet
dieselbe feste Basis und eine konservative Teilverdeckungsprüfung.

## Externe Integration: eigenständige Quelle BTV

BTV liefert tatsächliche Zielbeobachtungen und bestätigte Zuordnungen. Es ist
keine KES-Quelle. KES-Telegramme, Einzel-Schuss-/Fehlschussereignisse, Schusszähler,
Anschlag und Ergebnisse werden nicht erzeugt. Die ursprünglich geplante
KES-TCP-Ausgabe ist verworfen. Die Original-KES-Dokumentation bleibt als Referenz
für diese Abgrenzung erhalten. GFX integriert BTV später als eigene Quelle neben
KES und HORA; [Integrationsauftrag #102](https://github.com/richtertoralf/gfx-engine/issues/102).
In diesem Auftrag wurde dort ausschließlich das Issue angelegt, kein Code geändert.

### Stabiler lesender Vertrag (API-Version 1)

Die Anwendungsversion 0.7 und `api_version: 1` sind unterschiedliche Angaben.
Additive Felder sind zulässig; Clients ignorieren unbekannte Felder. Ein künftig
inkompatibler Vertrag erhält eine andere API-Version. Bestehende Befehle und
Endpunkte bleiben erhalten; für externe Live-Anzeigen ist kein Schreibzugriff nötig.

| Eingang | Verwendung |
|---|---|
| `GET /api/state` | Vollständige Momentaufnahme, ohne Eingabeentwürfe |
| `WS /ws` | Vollständiger Anfangszustand, danach Aktualisierungen und spätestens alle fünf Sekunden ein Zustand |
| `GET /api/events?after=N&limit=1000` | Optionales Journal, zum Nachvollziehen akzeptierter Beobachtungen/Befehle |
| `GET /api/health` | HTTP 200 bei betriebsfähigem Kern/Auswertung, sonst 503; `status`, Anwendungsversion und API-Identität |

REST-Zustand, WebSocket-Zustände und Journalantworten enthalten `api_version` und
`instance_id`. Die Instanzkennung wechselt bei jedem Serverstart, auch wenn das
Journal und seine `sequence` erhalten bleiben. Auf einer neuen Verbindung immer
den vollständigen Anfangszustand übernehmen. Nach Instanzwechsel alte
Sequenzvergleiche und flüchtige Daten verwerfen. Innerhalb derselben Instanz dürfen
ältere Befehlsantworten keinen neueren Zustand ersetzen. Gleiche Sequenznummern
nicht pauschal verwerfen: Kamerastatus, Lebenszeichen und Eingabeentwürfe können
sich ohne neues Journalereignis ändern.

Zusätzlich enthalten vollständige Zustände:

| Feld | Bedeutung |
|---|---|
| `sequence` | Letztes dauerhaft akzeptiertes Ereignis, keine Bild- oder Schussnummer |
| `health` | `ok` oder `error`; bei Fehler sind sichtbare Werte nur der letzte gespeicherte Stand |
| `capture.running` | Optische Auswertungsaufgabe läuft; bedeutet nicht, dass jede Kamera verbunden/kalibriert ist |
| `capture.cameras` | Dieselbe bereinigte Liste wie `/api/cameras`, einschließlich `connected` und letzter Bildempfangszeit |
| `capture.calibration_errors` | Aktuell vom Erfassungskern gemeldete beschädigte Kalibrierungen je Bahn |
| `simulation` | Beim Start gewählter Simulationsmodus |

RTSP-Adressen und Zugangsdaten fehlen in diesen Antworten. `captured_at` ist die
Serverzeit beim Bildempfang, keine garantierte Belichtungs- oder Schusszeit. Bei
unveränderten Zielstellungen bleibt deren `observed_at` unverändert; Bildempfang
und technische Verfügbarkeit stehen getrennt im Kamerastatus.

### Daten für einen externen BTV-Adapter

- `lanes["N"].targets`: genau fünf Werte `standing`, `fallen`, `unknown`, von
  links nach rechts (bei Kamera gemäß Kalibrierung). Das sind die wirksamen
  Zustände einschließlich manueller Priorität. Alle fünf direkt anzeigen, unabhängig von
  irgendeinem Zähler. `standing` bedeutet aufgerichtet, niemals Fehlschuss.
- `last_known_targets` ist nur die letzte bekannte mechanische Stellung. Damit
  darf eine aktuell unbekannte Stellung nicht als sichere Anzeige ersetzt werden.
- `current_bout_id` verweist auf die aktuelle Einlage in `bouts`; deren `bib` ist
  die bestätigte Startnummer oder `null`. Ohne Einlage keine Zuordnung erfinden.
- `occupied_bout_id` bezeichnet die noch bestehende Belegung. Eine alte Belegung
  kann nach Rückstellung neben einer neuen, unzugeordneten Einlage bestehen.
  Deren Startnummer darf nicht auf die neue Einlage übertragen werden.
- `bouts[id].fallen_target_ids` enthält eindeutige Positionen, deren Fall in dieser
  Einlage automatisch wirksam beobachtet wurde. Manuelle Korrekturen verändern
  diese historische Liste nicht. Der Monitor zählt sie für `current_bout_id`; ohne
  aktuelle Einlage null. Das ist keine Zahl abgegebener Schüsse und kein Ergebnis.
  Erste Bilder nach einem Ausfall können mehr gefallene Ziele zeigen als diese Liste.
- WebSocket-`drafts` sind unbestätigt und für externe fachliche Anzeigen zu ignorieren.
  `editor_id` ist eine flüchtige Bedienplatznummer, keine Sportler-/Quellenkennung.

Beispiel: Ein erster beobachteter Fall an Ziel 5 wird an Position 5 angezeigt,
auch wenn alle anderen Ziele noch unbekannt sind. Es wird kein Fehlschuss an
Position 1 und kein künstlicher Schusszähler daraus erzeugt. Für die spätere
GFX-Erweiterung muss die interne Verarbeitung deshalb Zielzustandsquellen von
Einzel-Schussquellen unterscheiden; KES-/HORA-Parser und Runner bleiben unverändert.

### Unterbrechungen, Journal und Grenzen

Nach zwölf Sekunden ohne WebSocket-Zustand Verbindung erneuern und die Anzeige
als unterbrochen kennzeichnen. Dafür lokale Empfangszeit verwenden, keine
Synchronität zwischen Client- und Serveruhr voraussetzen. Bei `health: error`
Werte als letzten Stand behandeln. Kameraausfälle erscheinen zusätzlich als
unbekannte Ziele und getrennte Kamerastatus. Eine Wiederverbindung liefert die
aktuelle Wahrheit; physische Übergänge während der Unterbrechung sind nicht
rekonstruierbar und werden nicht erfunden.

Langsame WebSocket-Empfänger dürfen Zwischenzustände überspringen; jede Nachricht
ist vollständig. Das Journal bewahrt die akzeptierten Beobachtungen, jedoch keine
unbeobachteten physischen Vorgänge. Optional seitenweise über die letzte empfangene
Ereignis-`sequence` weiterlesen, bis diese die Antwort-`sequence` erreicht; bei
Instanzwechsel erneut synchronisieren. Keine Schüsse aus nachgeladenen Zuständen
rekonstruieren. `event.baseline: true` bezeichnet eine Grundbeobachtung, keinen
beobachteten Fall oder Einlagenwechsel. Die Journalfolge beschreibt die Annahme-
reihenfolge des Servers. Mehrere Zieländerungen aus demselben Bild können dieselbe
`observed_at` besitzen; ihre physische Reihenfolge ist daraus nicht ableitbar.
Auch Rückstellung und Freigabe sind unterschiedliche Vorgänge.

Ein minimaler lesender Python-Client verwendet die bereits eingesetzte Bibliothek
`websockets` (Version 14–16):

```python
import asyncio
import json
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

async def watch():
    while True:
        try:
            async with connect("ws://SERVER-IP:8091/ws", open_timeout=5) as socket:
                while True:
                    state = json.loads(await asyncio.wait_for(socket.recv(), timeout=12))
                    if state.get("type") != "state":
                        continue
                    if state.get("api_version") != 1:
                        raise RuntimeError("Nicht unterstützte BTV-API-Version")
                    for lane in state["lanes"].values():
                        bout = state["bouts"].get(lane["current_bout_id"])
                        targets = lane["targets"] if state["health"] == "ok" else ["unknown"] * 5
                        print(lane["lane_id"], bout["bib"] if bout else None, targets)
        except (OSError, TimeoutError, ConnectionClosed):
            print("BTV-Verbindung unterbrochen; aktuellen Zustand neu laden")
            await asyncio.sleep(1)

asyncio.run(watch())
```

BTV stellt diese Schnittstellen ohne Anmeldung im vertrauenswürdigen lokalen
Netz bereit. Namens-, Wettkampf- und Ergebnisdaten sind Aufgabe der externen
Anwendung. Der Vertrag verlangt keine zusätzliche Schnittstelle oder Datenbank.

## Kameraverwaltung

- `GET /api/cameras`: Liste mit `id`, `name`, `lane_ids`, `url_configured`,
  `connected`, `captured_at`. Keine RTSP-URL oder Zugangsdaten.
- `POST /api/cameras`: JSON mit `id`, `name`, `url`, `lane_ids`.
- `PUT /api/cameras/{id}`: dieselben Felder; leere `url` erhält die gespeicherte
  Adresse. Kennung bleibt fest. Vollständige RTSP-/RTSPS-Adresse erforderlich.
- `DELETE /api/cameras/{id}`: Kamera und Zuordnungen entfernen; Kalibrierungen
  und Ereignisse bleiben gespeichert, sind ohne passende Quelle nicht verwendbar.
- `GET /api/cameras/{id}/frame`: aktuelles JPEG, `Cache-Control: no-store`;
  503 bei fehlendem/veraltetem Bild, 404 bei unbekannter Kamera.

Schreiboperationen liefern die bereinigte Kameraliste. Ungültige/mehrfache
Zuordnung, unbekannte Bahn und ungültige RTSP-Adresse liefern 422 mit allgemeinem
Text ohne Eingabedaten. Kameraänderungen werden gespeichert und ohne Serverneustart
angewendet. Der Verbindungsstatus kann anschließend über die Liste geprüft werden.

Bei einer kameragebundenen Bahn ergänzt `GET /api/lanes/{id}/calibration`
`camera_id` und `valid_for_camera`. Das gespeicherte Kalibrierungsobjekt enthält
`camera_id` und `camera_url_hash`; weder Hash noch Kennung ersetzen eine Prüfung
der realen Bildgeometrie. Die bisherigen Multipart-Endpunkte und das Standbild-
Werkzeug bleiben erhalten. Die laufende optische Auswertung liefert bestätigte
Zielbeobachtungen über dieselbe Kernverarbeitung.
