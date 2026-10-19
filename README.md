# Biathlon Target Vision

![Development](https://img.shields.io/badge/Status-Active_Development-orange)
![Production](https://img.shields.io/badge/Production-Not_Ready-red)



> [!WARNING]
> **Under active development – Not production-ready**
> Biathlon Target Vision is undergoing rapid development and has not yet been validated under real competition conditions.
> **Do not use it for official competitions or safety-critical decisions.** Features, interfaces, and data formats may change without notice.

## Mitarbeit / Contributing / Spolupráce

Biathlon Target Vision ist ein offenes Projekt. Entwickler, Zeitnehmer, Kampfrichter und Biathlonvereine sind eingeladen, sich an der Weiterentwicklung zu beteiligen.

**Beiträge und GitHub-Issues sind auf Deutsch, Englisch oder Tschechisch willkommen.**

**[Contributing Guide – How to participate / Jak se zapojit](CONTRIBUTING.md)**


## Was ist BTV? 

**Manuelle Schießstanderfassung und automatische Kameraerfassung mit
Vorrang für die Entscheidungen der Kampfrichter.**

**[Produktkonzept und Weiterentwicklung](docs/PRODUKTKONZEPT.md):** Nutzen für
Kampfrichter, Jury, Zeitnahme und Liveproduktionen sowie klar getrennte vorhandene,
geplante und perspektivische Funktionen.

Biathlon Target Vision (BTV) ist ein herstellerunabhängiges, lokal betreibbares
Open-Source-System für Vereine, Veranstalter, Kampfrichter und Zeitnahmeunternehmen.
Bereits **ohne Kameras und Sensoren** lässt sich ein Schießstand manuell erfassen:
Kampfrichter geben Startnummern und die Zustände der fünf Klappscheiben am Tablet
ein. Mehrere Tablets arbeiten synchronisiert zusammen und können dieselben oder
unterschiedliche Schießbahnen betreuen.

Eine vorhandene, kalibrierte Kamera übernimmt die laufende Erfassung im Hintergrund.
Kampfrichter sehen die Beobachtungen unmittelbar und können jede Scheibe durch
Antippen korrigieren. Die manuelle Korrektur hat Vorrang vor folgenden Kamerabildern;
die übrigen Scheiben werden weiter automatisch erfasst. Der korrigierte Zustand
gilt sofort auf allen Tablets, im Kontrollmonitor und für externe Datenempfänger.

Die dreisprachige Tablet-Bedienung in **Englisch, Deutsch und Tschechisch** ist für
internationale Veranstaltungen und Helferteams vorgesehen. Ein Schwerpunkt sind
mechanische 10-Meter-Luftgewehranlagen bei Schüler- und Nachwuchswettkämpfen,
Training und Gästeschießen.

## Ein Ablauf – mit oder ohne Kamera

Der Kampfrichter bedient immer dieselben Bahnkacheln. Ohne Kameras erfasst er die
fünf Scheiben selbst; eine zugeordnete Kamera liefert ihre Beobachtungen automatisch.
**Jede Scheibe bleibt jederzeit direkt korrigierbar. Menschliche Eingaben haben
Vorrang**, während die anderen Scheiben weiter automatisch erfasst werden. Es gibt
keine Betriebsartwahl am Tablet.

Versorgt eine Kamera beispielsweise die **Bahnen 4 bis 6** und fällt aus oder
liefert wegen Schneefalls keine zuverlässigen Beobachtungen mehr, erfassen die
Kampfrichter dort unmittelbar nach Sicht weiter. Kein Umschalten ist erforderlich;
Startnummern, laufende Schießeinlagen und Ereignisse bleiben erhalten. Andere
Bahnen arbeiten unabhängig weiter. Auch nach Wiederverbindung bleiben einzelne
Korrekturen geschützt. Sie enden mit bestätigter vollständiger Rückstellung oder
einer neuen Schießeinlage. Erste Kamerabilder nach einer Unterbrechung sind
Grundbeobachtungen und erzeugen keine rückwirkenden Fälle oder Rückstellungen.

**Sensorik ist geplant:** Manuelle Erfassung und Kameraerfassung sind vorhanden.
Sensorhardware und Sensoradapter sind noch nicht implementiert. Auch spätere
Sensordaten sollen im Hintergrund helfen und menschlichen Korrekturen unterliegen.
Quellenzuordnung und technische Einstellungen gehören in die Administration.

## Anbindung an Zeitnahme und Anzeigen

BTV stellt aktuelle Schießbahndaten über dokumentierte **REST- und
WebSocket-Schnittstellen** bereit: fünf wirksame Scheibenzustände einschließlich
manueller Korrekturen, bestätigte Startnummern, Schießeinlagen und Bahnbelegung.
Zeitnahmeunternehmen können diese Daten grundsätzlich in ihre bestehenden
Systeme übernehmen. Eine konkrete Anbindung muss für das jeweilige Zeitnahmesystem
entwickelt und geprüft werden; eine Herstellerkompatibilität wird nicht zugesichert.

- Aktueller Zustand: `http://SERVER-IP:8091/api/state`
- Laufende vollständige Zustände: `ws://SERVER-IP:8091/ws`
- [API und Integrationshinweise](docs/API.md#externe-integration-eigenständige-quelle-btv)
  mit Datenfeldern, Wiederverbindung und lesendem Beispielclient.

Alle Schnittstellen verwenden denselben Web-Port wie die Tablets. Die geplante
GFX-Anbindung wird separat in [gfx-engine #102](https://github.com/richtertoralf/gfx-engine/issues/102)
verfolgt. BTV emuliert kein KES und ersetzt keine bestehenden KES-/HORA-Empfänger.

BTV ist **keine Wettkampf-, Zeitnahme- oder Ergebnisverwaltung**. Ergebnisberechnung,
Strafzeiten, Strafrunden und offizielle Ergebnislisten bleiben beim angeschlossenen
System. Eine gefallene Scheibe ist eine Zustandsbeobachtung; BTV erfindet daraus
keine einzelnen Schuss- oder Fehlschussmeldungen. Unbekannte Zustände bleiben
sichtbar unbekannt.

## Entwicklungsstand und geplanter Praxistest

**BTV befindet sich in aktiver Entwicklung und ist noch nicht für den produktiven
Wettkampfbetrieb freigegeben.**

Der aktuelle Entwicklungsstand auf `main` umfasst einen einheitlichen Bedienablauf
mit manueller Priorität, synchronisierte Tablets, einen schreibgeschützten Kontrollmonitor,
RTSP-Kameraverwaltung und browserbasierte Kalibrierung. Startnummern lassen sich
zuordnen und korrigieren; erfasste Zustände und manuelle Übersteuerungen werden
nach einem Neustart wiederhergestellt.

Die Kameraerkennung ist bisher mit synthetischen Bildern und Videofolgen geprüft,
**noch nicht unter realen Schießstandbedingungen validiert**. Ein erster Test an
realen Schießstandanlagen ist für **Ende Oktober 2026 im Arberstadion geplant**.
Dabei sollen automatische Erfassung, unmittelbare menschliche Korrekturen und
praktische Bedienung überprüft werden.

Tschechische Zeitnehmer sollen die Anwendung und ihre Schnittstellen begutachten
und eine mögliche direkte Anbindung an ihre Zeitnahme beurteilen können. Das ist
eine geplante Prüfung einer möglichen Integration, kein bereits bestätigter
Integrations- oder Kompatibilitätsnachweis.

## Ablauf für Kampfrichter am Schießstand

![Screenshot Stand 18.10.2026](<Bildschirmfoto vom 2026-10-18 20-52-46.png>)

Die Kamera erfasst ausschließlich Scheibenzustände und zuverlässig beobachtete
vollständige Rückstellungen. Betreten, Startnummer, Beaufsichtigung und Verlassen
bleiben Aufgaben der Kampfrichter. Die mechanischen Scheiben müssen tatsächlich
aufgerichtet werden; eine Schaltfläche bewegt sie nicht.

0. **Bahn frei und vorbereitet:** Kein Sportler auf der Bahn, alle fünf Scheiben
   tatsächlich aufgerichtet und die Vorbereitung bestätigt. Die Kachel ist
   **grün: „Frei – bereit“**. Ein unbekannter Ausgangszustand gilt noch nicht als bereit.
1. **Sportler betritt die Bahn:** **„Bahn belegen“** antippen. Die Kachel wird sofort
   **gelb: „Belegt“**, auch ohne bekannte Startnummer. Die Kamera entscheidet nicht
   über Betreten oder Verlassen einer Bahn.
2. **Startnummer erfassen:** Neben „Startnummer“ auf **„Eingeben“** tippen, die BIB
   über das Zahlentastenfeld eingeben und bestätigen. Die Nummer erscheint groß
   auf allen verbundenen Tablets. Verspätete Eingabe und Korrektur bleiben möglich.
3. **Schießeinlage verfolgen:** **Schwarz bedeutet aufgerichtet, weiß bedeutet
   gefallen.** Die Kamera aktualisiert automatisch, soweit vorhanden. Fehlt sie
   oder stimmt eine Anzeige nicht, die betreffende Scheibe antippen: Schwarz wird
   weiß, erneutes Antippen korrigiert die Eingabe. Bei **„?“** öffnet Antippen die
   eindeutige Auswahl **„Aufgerichtet“ / „Gefallen“**. Eine Einzelkorrektur beginnt
   oder beendet keine Einlage und wird nicht durch unveränderte Kamerabilder
   überschrieben.
4. **Sportler verlässt die Bahn:** **„Bahn verlassen“** antippen. Die Belegung endet;
   Scheibenstellungen bleiben erhalten. Fehlt die bestätigte Rückstellung, ist die
   Kachel **grau: „Frei – Rückstellung ausstehend“**.
5. **Mechanisch zurückstellen:** Die Scheiben tatsächlich aufrichten, etwa durch
   Ziehen am Seil, dann **„Alle Scheiben aufgerichtet“** bestätigen. Diese Aktion ist
   immer sichtbar und funktioniert auch ohne Kamera. Alternativ kann eine Kamera
   eine zuverlässig beobachtete vollständige Rückstellung bestätigen. Ist die
   Bahn nicht mehr belegt, wechselt die Kachel auf Grün.

| Kachel | Bedeutung | Nächste Aufgabe |
|---|---|---|
| **Grün – Frei, bereit** | Unbelegt, alle Scheiben aufgerichtet, Vorbereitung bestätigt | Nächsten Sportler mit „Bahn belegen“ erfassen |
| **Gelb – Belegt** | Sportler auf der Bahn, unabhängig von Scheibenstellungen | BIB und Scheiben beaufsichtigen, dann „Bahn verlassen“ |
| **Grau – Frei, Rückstellung ausstehend** | Unbelegt, Vorbereitung fehlt oder Scheiben gefallen/unbekannt | Mechanisch zurückstellen und bestätigen |

Bahnverlassen und Rückstellung dürfen in umgekehrter Reihenfolge erfolgen:
Eine Rückstellung gibt eine belegte Bahn nicht frei. Fünf unverändert aufgerichtete
Scheiben beweisen keine neue Rückstellung, etwa nach einer Einlage ohne gefallene
Scheibe oder nach Kameraneustart. Dann die tatsächliche Vorbereitung ausdrücklich
bestätigen. Unsichere Kameradaten machen eine Bahn nicht automatisch bereit;
eine menschliche Rückstellbestätigung gilt auch bei ausgefallener Kamera.

Unter **„Optionen“** liegt die Einlagenhistorie für verspätete BIB-Zuordnungen.
Jede Bahnkachel zeigt außerdem **„Automatik aktiv“**, **„Erkennung läuft / unsicher“**
oder **„Nur manuell“**. Erst bestätigte Kamerabeobachtungen aller fünf Scheiben
ergeben „Automatik aktiv“; eine verbundene Kamera allein genügt nicht. Bei fehlender
oder unsicherer Erfassung nach Sicht eingeben. Einzelne manuelle Korrekturen sind
mit **„Manuell“** an der Scheibe gekennzeichnet und behalten Vorrang. Bei getrennter
Serververbindung ist auch der Erfassungsstatus unbekannt; Eingaben sind dann gesperrt.

Je Tablet die betreuten Bahnen auswählen; Auswahlen dürfen sich überschneiden.
Andere Tablets zeigen unbestätigte Startnummerneingaben getrennt vom verbindlichen
Stand. Bei einem Belegungskonflikt bleibt die eigene Eingabe zur Prüfung erhalten.

Der Jury-/Kontrollmonitor unter `/monitor` zeigt alle Bahnen schreibgeschützt mit
denselben drei Hintergrundfarben, bestätigter Startnummer und fünf wirksamen
Scheibenstellungen. Hinweise auf unzuverlässige Erfassung fordern zur Sichtprüfung
auf. Technische Vergleichswerte und Quellenverwaltung stehen unter `/admin`.

## Unter Debian/Ubuntu installieren

Voraussetzung: Debian/Ubuntu mit Python 3.11 oder neuer, systemd und Internet
für die Installation. Installation eines veröffentlichten Versionstags, hier des
Entwicklungsreleases `v0.8.4` für den Praxistest:

```bash
git clone --branch v0.8.4 https://github.com/richtertoralf/biathlon-target-vision.git
cd biathlon-target-vision
./install.sh
```

Ohne `--branch` wird der aktuelle, ungetaggte Stand von `main` installiert.

Der Installer nutzt bei Bedarf sudo. Der Dienst startet automatisch als Benutzer
`btv`. Tablet: `http://SERVER-IP:8091/`, Monitor: `http://SERVER-IP:8091/monitor`.

```bash
biathlon-target-vision --version
sudo biathlon-target-vision --status
sudo biathlon-target-vision --upgrade
```

`--status` zeigt Version, Dienst- und API-Zustand, konfigurierte Serveradresse,
die im Netzwerk verwendbaren URLs, Bahnen, Kameras mit Verbindungsstatus,
kalibrierte Bahnen, die aktive Sitzung und das Datenverzeichnis. Ohne sudo ist die
geschützte Konfiguration nicht lesbar; dann werden nur tatsächlich antwortende
Adressen genannt. Exitcode `0`: in Ordnung, `1`: Dienst oder API nicht verfügbar,
`2`: API meldet eine Störung.

Upgrades verwenden den neuesten veröffentlichten Versionstag und erhalten
Konfiguration, Kalibrierungen und Ereignisse. Änderungen auf `main` können dem
letzten Versionstag voraus sein; `--upgrade` lädt ausschließlich veröffentlichte
Versionstags. Betrieb und Speicherorte beschreibt
[ARCHITECTURE.md](docs/ARCHITECTURE.md#installation-und-upgrades).

## Lokal installieren und starten

Voraussetzung: Linux, Python 3.11 oder neuer und `python3-venv`.
Im Repository-Verzeichnis:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m biathlon_target_vision
```

Tablet-Bedienung: <http://127.0.0.1:8091/> ·
Kalibrierung: <http://127.0.0.1:8091/calibration> ·
Interaktive API: <http://127.0.0.1:8091/docs>

Für den Zugriff im lokalen Netz `--host 0.0.0.0` ergänzen und auf den Tablets
`http://SERVER-IP:8091/` öffnen. Sprache und Bahnauswahl bleiben je Browser und
Serveradresse gespeichert. Die Anwendung benötigt im Betrieb keine Cloud und
keinen Internetzugang; sie ist ohne Anmeldung für ein vertrauenswürdiges lokales
Netz ausgelegt.

Voreingestellt sind 20 Schießbahnen. Beispiel mit anderer Bahnanzahl, Port und
eigenem Datenordner:

```bash
.venv/bin/python -m biathlon_target_vision --lanes 8 --port 8092 --data-dir data-test
```

Die Bahnanzahl wird beim ersten Start gespeichert. Für eine andere Anzahl einen
neuen Datenordner verwenden. Genau einen Serverprozess je Datenordner betreiben.

## Aufzeichnungssitzungen

Unter `/admin` lässt sich die aktuelle Sitzung benennen und mit **„Sitzung
abschließen und neue starten“** beenden. Den Namen der nächsten Sitzung eingeben
und den Abschluss ausdrücklich bestätigen. Die Seite warnt vor noch belegten
Bahnen oder offenen Schießeinlagen. Ein bestätigter Abschluss archiviert den
bisherigen Stand; er behauptet keine mechanische Rückstellung und kein Verlassen.

Die neue Sitzung hat keine Startnummern, Belegungen oder Schießeinlagen. Alle
Bahnen beginnen grau und müssen erneut vorbereitet werden. Tablets und Monitor
wechseln automatisch; offene Eingaben aus der alten Sitzung werden geschlossen.
Die Kameras, Bahnzuordnungen, Kalibrierungen und administrativen Quellensperren
bleiben erhalten. Erste Kamerabilder sind Grundbeobachtungen, keine rückwirkenden
Fälle oder Rückstellungen. Identische BIBs in verschiedenen Sitzungen sind unabhängig.

Journal und Korrekturbelege bleiben je Sitzung unter `sessions/SITZUNGS-ID/` im
Datenordner erhalten. Abgeschlossene Sitzungen sind in der Administration mit
ihrer Journal-API verlinkt; eine zeitbezogene Journalansicht und Exportoberfläche
sind weiterhin geplant. Archive werden nicht automatisch gelöscht. Neustarts
setzen die aktive Sitzung fort. Die Administration setzt derzeit weiterhin ein
vertrauenswürdiges lokales Netz voraus; Benutzerrollen sind noch nicht umgesetzt.

**Einmaliger Wechsel alter Testinstallationen:** Alte Stände speicherten direkt
`events.jsonl` und `corrections/` im Datenordner. Dieser Bestand wird weder
umgeschrieben noch gelöscht; der neue Server verlangt vorherige manuelle
Archivierung. Server stoppen, den vollständigen bisherigen Datenordner unter
einem eindeutig benannten Archivpfad aufbewahren und einen neuen Datenordner
anlegen. Nur `config.json` und `calibrations/`, soweit vorhanden, aus der Sicherung
kopieren. Bei systemd liegt der Datenordner unter `/var/lib/biathlon-target-vision`;
Eigentümer `btv:btv`, Verzeichnisrechte `0750`, Konfigurationsrechte `0600` und
Schreibrechte des Dienstbenutzers auch für kopierte Kalibrierungen wiederherstellen.
Lokal kann stattdessen ein neuer `--data-dir` verwendet werden. Administrative
Quellensperren aus dem alten Journal bei Bedarf erneut setzen.

Bisher benötigte jede neue Veranstaltung einen eigenen Datenordner und einen
Serverneustart. Für neu angelegte Sitzungen entfällt das. Ältere
Entwicklungsversionen und API-Schreiber ohne Sitzungskennung werden nicht
unterstützt; siehe [Sitzungsvertrag](docs/API.md#aufzeichnungssitzungen-api-version-2).
Keinen älteren Programmstand mit dem neuen Datenordner betreiben. Für einen
bewussten Rückwechsel den separat aufbewahrten alten Testbestand verwenden.

### Praxistest: Feldprotokoll, Testdiagnose und Testprotokoll

Unter `/admin#sessions` stehen für Praxistests drei optionale Funktionen bereit.
Eine normale Sitzung funktioniert ohne sie vollständig.

1. **„Feldprotokoll (PDF) herunterladen“:** ein druckfertiges A4-Formular für
   alles, was BTV nicht selbst erfassen kann: Kameraaufbau und Abstände, Wetter,
   Licht, unabhängige Referenz der Scheibenstellungen und Bedienbarkeit. Es ist mit
   Sitzung, Version, Kameras, Bahnen und Kalibrierungsstand vorausgefüllt.
2. **„Testdiagnose starten“ / „beenden“:** BTV misst etwa alle fünf Sekunden
   Prozess- und Systemlast, Kameraverbindungen, Bildauflösung, Erfassungsstatus
   je Bahn und Verarbeitungszeiten. Optional lassen sich Kameraabstände, Wetter,
   Licht und Beobachtungen eintragen.
3. **„Testprotokoll erstellen“:** ein Markdown-Bericht aus Sitzung,
   Ereignisjournal, Konfiguration, Kalibrierungen, Messwerten und
   MediaMTX-Aufzeichnungsdateien; auch für abgeschlossene Sitzungen. Die
   Messwerte gibt es zusätzlich als JSON.

Die Daten liegen unter `sessions/SITZUNGS-ID/diagnostics/` im Datenordner. Eine
laufende Testdiagnose wird nach einem Neustart von BTV fortgesetzt und beim
Sitzungsabschluss beendet. Gemessen werden Verarbeitungszeiten in BTV, keine
physische Ende-zu-Ende-Latenz. Ablauf, erfasste Werte und Grenzen beschreibt
[ARBER-TESTPROTOKOLL.md](docs/ARBER-TESTPROTOKOLL.md).

## Kameras einrichten

`http://SERVER-IP:8091/admin` öffnen. Die Administration hat drei Bereiche:
**Kameras**, **Bahnen** und **Sitzungen**. Unter „Kameras“ → „Neue Kamera anlegen“
Name, vollständige RTSP-Adresse (zum Beispiel `rtsp://192.168.95.43/1/h264major`)
eintragen und die Bahnen antippen. Die Kennung wird aus dem Namen vorgeschlagen und
bleibt danach fest. Mehrere Bahnen können dasselbe Kamerabild nutzen; jede
automatisch erfasste Bahn hat genau eine zuständige Kamera. Bei
Verbindungsproblemen wird erneut verbunden.

Über „Bahn … kalibrieren“ das aktuelle Kamerabild übernehmen und vier Ecken um
den gesamten Scheibenbereich markieren. Die fünf Scheiben werden automatisch
gesucht; ihre gefundenen Umrisse kontrollieren. Keine einzelne Scheibe muss
manuell markiert werden. Bei Kamera-/Adresswechsel, anderer Auflösung oder
geänderter Ausrichtung neu kalibrieren.

Nach gültiger Kalibrierung beginnt die Auswertung automatisch. Der Bereich
„Bahnen“ zeigt alle Bahnen als Raster mit Kamera und Erfassungsstatus. Nach Antippen
einer Bahn lässt sich eine fehlerhafte Quelle administrativ sperren oder wieder
zulassen; dort stehen auch automatische Zielzustände und aktive Korrekturen.
Für den normalen Ablauf oder einen Kameraausfall ist diese Einstellung unnötig.
Quellensperren bleiben über Neustarts und Sitzungswechsel erhalten.

Kleine Bildverschiebungen werden nachgeführt; unklare Sicht oder zu große Bewegung
führt zu unbekannten Beobachtungen. Beim Bearbeiten zeigt die Administration die
gespeicherte Adresse ohne Zugangsdaten; eine neue Adresse ersetzt sie vollständig.
Gespeicherte Zugangsdaten werden nicht an den Browser zurückgegeben. Administration, Kalibrierung und Monitor sind derzeit deutsch;
die Tablet-Sprachauswahl ist davon unabhängig.

<img src="./biathlon-target_Luftgewehr.jpg" alt="Mechanische Luftgewehr-Scheibenanlage" width="400">

## Übungen und Weiterentwicklung

Für Übungen einen separaten Datenordner verwenden. Der zusätzliche Simulator
ist von der regulären manuellen Erfassung unabhängig:

```bash
.venv/bin/python -m biathlon_target_vision --simulation --data-dir data-simulation --host 0.0.0.0
```

Im gekennzeichneten Simulationsbetrieb lassen sich Scheibenzustände und
Rückstellungen durchspielen. Übungen werden gespeichert; Training und
Veranstaltung deshalb getrennt halten. Den Simulator für die Kommandozeile
beschreibt die [API-Dokumentation](docs/API.md#simulator-für-die-kommandozeile).
Neben Praxistests und externer Integration sind Sensoradapter und ein physisches
Tastenfeld geplante Erweiterungen.

## Weiterführende Dokumentation

- [Testprotokoll Praxistest](docs/ARBER-TESTPROTOKOLL.md): Feldprotokoll, Testdiagnose und automatisches Testprotokoll.
- [Roadmap](docs/ROADMAP.md): priorisierte Issues, nächste Schritte und offene Entscheidungen für den Arberstadion-Praxistest.
- [API und Integration](docs/API.md): Schnittstellen, Zuordnungsregeln und Integrationshinweise.
- [Architektur und Betrieb](docs/ARCHITECTURE.md): Komponenten, Speicherung und Upgrades.
- [Terminologie](docs/TERMINOLOGIE.md): bestätigte IBU-/Verbandsbegriffe und technische UI-Bezeichnungen.
- [Entwicklungsbericht](docs/ENTWICKLUNGSBERICHT.md): Entscheidungen, tatsächlich ausgeführte Tests und Grenzen.
