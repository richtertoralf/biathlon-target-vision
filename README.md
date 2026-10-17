# Biathlon Target Vision

**Manuelle Schießstanderfassung am Tablet und automatische Kameraerfassung mit
Vorrang für die Entscheidungen der Kampfrichter.**

Biathlon Target Vision (BTV) ist ein herstellerunabhängiges, lokal betreibbares
Open-Source-System für Vereine, Veranstalter, Kampfrichter und Zeitnahmeunternehmen.
Bereits **ohne Kameras und Sensoren** lässt sich ein Schießstand manuell erfassen:
Kampfrichter geben Startnummern und die Zustände der fünf Klappscheiben am Tablet
ein. Mehrere Tablets arbeiten synchronisiert zusammen und können dieselben oder
unterschiedliche Schießbahnen betreuen. Dafür ist kein Simulationsmodus erforderlich.

Im **priorisierten Mischbetrieb** übernimmt die Kamera die laufende Erfassung.
Kampfrichter sehen die Beobachtungen unmittelbar und können jede Scheibe durch
Antippen korrigieren. Die manuelle Korrektur hat Vorrang vor folgenden Kamerabildern;
die übrigen Scheiben werden weiter automatisch erfasst. Der korrigierte Zustand
gilt sofort auf allen Tablets, im Kontrollmonitor und für externe Datenempfänger.

Die dreisprachige Tablet-Bedienung in **Englisch, Deutsch und Tschechisch** ist für
internationale Veranstaltungen und Helferteams vorgesehen. Ein Schwerpunkt sind
mechanische 10-Meter-Luftgewehranlagen bei Schüler- und Nachwuchswettkämpfen,
Training und Gästeschießen.

## Drei Betriebsarten je Schießbahn

| Betriebsart | Erfassung und Bedienung |
|---|---|
| **Manuell** | Kampfrichter erfassen alle fünf Scheiben am Tablet. Keine Kamera, keine Sensoren und kein `--simulation` erforderlich. |
| **Automatisch** | Eine kalibrierte Kamera liefert die Scheibenzustände. |
| **Mischbetrieb** | Automatische Erfassung mit sofortigen manuellen Korrekturen je Scheibe. Die nicht korrigierten Scheiben bleiben automatisch gesteuert. |

Die Betriebsart wird unter **„Optionen“** in jeder Bahnkachel gewählt. Für den
Betrieb ohne Kamera zuerst **„Manuell“** auswählen, anschließend die tatsächliche
Vorbereitung bestätigen. Unterschiedliche Betriebsarten können gleichzeitig an
einem Schießstand verwendet werden.

Versorgt beispielsweise eine Kamera die **Bahnen 4 bis 6** und fällt aus oder
liefert wegen Schneefalls keine zuverlässigen Beobachtungen mehr, können diese
Bahnen auf Manuell umgeschaltet und nach Sicht weitergeführt werden. Startnummern,
laufende Schießeinlagen und bisher erfasste Ereignisse bleiben erhalten. Andere
Bahnen arbeiten unabhängig weiter. Das ermöglicht einen unterbrechungsarmen
Ersatzbetrieb, ohne Kameraerkennung vorauszusetzen.

Beim Rückwechsel bleiben manuelle Werte geschützt, bis der Kampfrichter eine
Scheibe mit `Auto ↩` wieder freigibt, eine Rückstellung bestätigt oder eine neue
Schießeinlage beginnt. Erste Kamerabilder nach einer Unterbrechung liefern
Grundbeobachtungen und erzeugen keine rückwirkenden Treffer.

**Sensorik ist geplant:** Neben der manuellen und der vorhandenen Kameraerfassung
ist ein Sensoradapter als zusätzliche Erfassungsquelle vorgesehen. Sensorhardware
und Sensoranbindung sind noch nicht implementiert. Auch spätere Sensordaten sollen
manuellen Korrekturen untergeordnet sein.

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

Der aktuelle Entwicklungsstand auf `main` umfasst manuelle Erfassung, automatischen und priorisierten
Mischbetrieb, synchronisierte Tablets, einen schreibgeschützten Kontrollmonitor,
RTSP-Kameraverwaltung und browserbasierte Kalibrierung. Startnummern lassen sich
zuordnen und korrigieren; erfasste Zustände und manuelle Übersteuerungen werden
nach einem Neustart wiederhergestellt.

Die Kameraerkennung ist bisher mit synthetischen Bildern und Videofolgen geprüft,
**noch nicht unter realen Schießstandbedingungen validiert**. Ein erster Test an
realen Schießstandanlagen ist für **Ende Oktober 2026 im Arberstadion geplant**.
Dabei sollen automatische Erfassung, priorisierter Mischbetrieb und praktische
Bedienung überprüft werden.

Tschechische Zeitnehmer sollen die Anwendung und ihre Schnittstellen begutachten
und eine mögliche direkte Anbindung an ihre Zeitnahme beurteilen können. Das ist
eine geplante Prüfung einer möglichen Integration, kein bereits bestätigter
Integrations- oder Kompatibilitätsnachweis.

## Ablauf für Kampfrichter am Schießstand

Der Ablauf ist in allen drei Betriebsarten gleich. Nur die Erfassung der
Scheibenstellungen unterscheidet sich:

| Aufgabe | Manuell | Automatisch | Mischbetrieb |
|---|---|---|---|
| Bahn belegen/verlassen | Kampfrichter | Kampfrichter | Kampfrichter |
| BIB erfassen | Kampfrichter | Kampfrichter | Kampfrichter |
| Gefallene Scheiben erfassen | Kampfrichter | Kamera | Kamera + Korrektur durch Kampfrichter |
| Rückstellung erkennen/bestätigen | Kampfrichter | Kamera, soweit zuverlässig erkennbar | Kamera, bei Bedarf Kampfrichter |
| Überwachung | Kampfrichter | Kampfrichter | Kampfrichter |

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
   gefallen.** Im manuellen Betrieb jede gefallene Scheibe einmal antippen;
   erneutes Antippen korrigiert eine Fehleingabe, ohne eine neue Einlage anzulegen.
   Automatisch liefert die Kamera die Stellungen. Im Mischbetrieb kann jede Scheibe
   sofort korrigiert werden; manuelle Werte haben Vorrang, andere Scheiben bleiben
   automatisch gesteuert. `M` markiert eine Übersteuerung, die kleine Auto-Anzeige
   zeigt den Vergleichswert. Antippen von `Auto ↩` gibt nur diese Scheibe frei.
4. **Sportler verlässt die Bahn:** **„Bahn verlassen“** antippen. Die Belegung endet;
   Scheibenstellungen bleiben erhalten. Fehlt die bestätigte Rückstellung, ist die
   Kachel **grau: „Frei – Rückstellung ausstehend“**.
5. **Mechanisch zurückstellen:** Die Scheiben tatsächlich aufrichten, etwa durch
   Ziehen am Seil. Im manuellen Betrieb anschließend **„Alle Scheiben aufgerichtet“**
   antippen. Automatisch oder im Mischbetrieb kann eine zuverlässig erkannte
   vollständige Rückstellung übernommen werden. Ist die Bahn nicht mehr belegt,
   wechselt sie auf Grün und ist für den nächsten Sportler bereit.

Bahnverlassen und Rückstellung dürfen in umgekehrter Reihenfolge erfolgen:
Eine Rückstellung gibt eine belegte Bahn nicht frei; sie bleibt gelb bis
**„Bahn verlassen“** bestätigt wird. Fünf unverändert aufgerichtete Scheiben allein
beweisen keine neue Rückstellung, beispielsweise nach einer Einlage ohne erkannte
gefallene Scheibe. Dann nach tatsächlicher Vorbereitung ausdrücklich
**„Alle Scheiben aufgerichtet“** bestätigen; die Aktion ist auch unter **„Optionen“**
erreichbar. Bei Kameraausfall oder unklarer Sicht gibt es keine automatische
Bereitmeldung. Betroffene Bahnen können manuell weitergeführt werden.

Die Betriebsart ist in jeder Kachel sichtbar. Unter **„Optionen“** liegen die
Betriebsartwahl, Einlagenhistorie und die Sonderfunktion für eine ausdrücklich
unbekannte Scheibenstellung. Unbekannt ist kein Fehlschuss. Je Tablet die betreuten
Bahnen auswählen; Auswahlen dürfen sich überschneiden. Andere Tablets zeigen
unbestätigte Startnummerneingaben getrennt vom verbindlichen Stand. Bei einem
Belegungskonflikt bleibt der eigene Text zur Prüfung erhalten. Eine zuvor ohne BIB
erfasste Einlage kann später über ihre Historie zugeordnet werden.

Der Kontrollmonitor unter `/monitor` zeigt alle Bahnen schreibgeschützt mit
Belegung, Vorbereitung und wirksamen Scheibenstellungen. Automatisch beobachtete
Fälle und aktuell wirksame gefallene Scheiben bleiben getrennt; dies ist keine
Schusszählung oder Ergebniswertung. Sensorhardware und Sensoradapter sind weiter
geplant und übernehmen in diesem Stand keine Erfassungsaufgabe.

## Unter Debian/Ubuntu installieren

Voraussetzung: Debian/Ubuntu mit Python 3.11 oder neuer, systemd und Internet
für die Installation. Installation des aktuellen Stands auf `main`:

```bash
git clone https://github.com/richtertoralf/biathlon-target-vision.git
cd biathlon-target-vision
./install.sh
```

Der Installer nutzt bei Bedarf sudo. Der Dienst startet automatisch als Benutzer
`btv`. Tablet: `http://SERVER-IP:8091/`, Monitor: `http://SERVER-IP:8091/monitor`.

```bash
biathlon-target-vision --version
biathlon-target-vision --status
sudo biathlon-target-vision --upgrade
```

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

## Kameras einrichten

`http://SERVER-IP:8091/admin` öffnen. Kennung, Name, vollständige RTSP-Adresse
(zum Beispiel `rtsp://192.168.95.43/1/h264major`) und Bahnnummern eintragen.
Mehrere Bahnen können dasselbe Kamerabild nutzen; jede automatisch erfasste Bahn
hat genau eine zuständige Kamera. Bei Verbindungsproblemen wird erneut verbunden.

Über „Bahn … kalibrieren“ das aktuelle Kamerabild übernehmen und vier Ecken um
den gesamten Scheibenbereich markieren. Die fünf Scheiben werden automatisch
gesucht; ihre gefundenen Umrisse kontrollieren. Keine einzelne Scheibe muss
manuell markiert werden. Bei Kamera-/Adresswechsel, anderer Auflösung oder
geänderter Ausrichtung neu kalibrieren.

Nach gültiger Kalibrierung beginnt die Auswertung automatisch. Kleine
Bildverschiebungen werden nachgeführt; unklare Sicht oder zu große Bewegung
führt zu unbekannten Beobachtungen. Beim Bearbeiten bleibt eine leer gelassene
RTSP-Adresse erhalten; gespeicherte Zugangsdaten werden nicht an den Browser
zurückgegeben. Administration, Kalibrierung und Monitor sind derzeit deutsch;
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

- [API und Integration](docs/API.md): Schnittstellen, Zuordnungsregeln und Integrationshinweise.
- [Architektur und Betrieb](docs/ARCHITECTURE.md): Komponenten, Speicherung und Upgrades.
- [Terminologie](docs/TERMINOLOGIE.md): bestätigte IBU-/Verbandsbegriffe und technische UI-Bezeichnungen.
- [Entwicklungsbericht](docs/ENTWICKLUNGSBERICHT.md): Entscheidungen, tatsächlich ausgeführte Tests und Grenzen.
