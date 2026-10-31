# Biathlon Target Vision

[![Version](https://img.shields.io/badge/version-0.8.5-blue)](biathlon_target_vision/__init__.py)
[![Release](https://img.shields.io/github/v/release/richtertoralf/biathlon-target-vision?include_prereleases&sort=semver&label=release)](https://github.com/richtertoralf/biathlon-target-vision/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Tests](https://github.com/richtertoralf/biathlon-target-vision/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/richtertoralf/biathlon-target-vision/actions/workflows/tests.yml)

> [!WARNING]
> **Under active development – not production-ready.** Biathlon Target Vision has not yet
> been validated under real competition conditions. Do not use it for official competitions
> or safety-critical decisions. Interfaces and data formats may still change.

*English summary:* Biathlon Target Vision (BTV) records the state of mechanical biathlon
targets on tablets – fully usable without cameras – and can optionally be supported by IP
cameras. Judges' corrections always take priority. Lane data is provided to timing and
live graphics systems via REST and WebSocket. Tablet UI in English, German and Czech.

## Was ist BTV?

Biathlon Target Vision erfasst am Schießstand die Startnummern und die Zustände der fünf
Klappscheiben jeder Schießbahn und stellt sie in Echtzeit bereit – für Kampfrichter,
Jury, Zeitnahme und Livegrafik. Das System läuft lokal auf einem Linux-Rechner im
Veranstaltungsnetz, ohne Cloud und ohne Internetverbindung im Betrieb.

BTV ist Teil unserer Softwareentwicklung für Sportveranstaltungen und Live-TV-Produktionen,
in der wir Wettkampferfassung, Zeitnahme und Livegrafik verbinden. Begriffe und Abläufe
orientieren sich an den Wettkampfregeln der IBU (Event and Competition Rules) und den
Anforderungen internationaler Verbände wie IBU und FIS. Eine Zertifizierung oder
Zulassung durch einen Verband besteht nicht.

## Funktionen und Vorteile

- **Manuelle Schießstanderfassung als Kernfunktion:** Kampfrichter erfassen Belegung,
  Startnummer und Scheibenzustände am Tablet – vollständig ohne Kameras oder Sensoren.
  Mehrere Tablets arbeiten synchronisiert; jedes betreut frei wählbare Bahnen.
- **Optionale Kameraunterstützung:** Kalibrierte RTSP-IP-Kameras erfassen die
  Scheibenzustände automatisch. Eine Kamera kann mehrere Bahnen versorgen. Die
  Kameraerkennung ist bisher nur mit synthetischen Bildern geprüft; der erste Praxistest
  an einer realen Anlage läuft im Oktober 2026.
- **Mensch vor Automatik:** Jede Scheibe ist jederzeit durch Antippen korrigierbar. Die
  Korrektur hat Vorrang und gilt sofort auf allen Tablets und Ausgängen. Fällt eine
  Kamera aus, wird ohne Umschalten manuell weitererfasst.
- **Mehrere Schießbahnen und Kameras:** standardmäßig 20 Bahnen, Kontrollmonitor für die
  Jury, dauerhaftes Ereignisjournal mit Wiederherstellung nach Neustart.
- **Offene Schnittstellen für Zeitnahme und Livegrafik:** wirksame Scheibenzustände,
  Startnummern, Schießeinlagen und Bahnbelegung über dokumentierte REST- und
  WebSocket-Schnittstellen. Eine Anbindung an ein bestimmtes Zeitnahmesystem ist je
  System zu entwickeln und zu prüfen.
- **Mehrsprachig:** Tablet-Bedienung in Englisch, Deutsch und Tschechisch; Sportbegriffe
  aus den jeweiligen IBU-Regelfassungen ([Terminologie](docs/TERMINOLOGIE.md)).
- **Kostengünstig und flexibel:** Standard-Linux-Rechner, handelsübliche Tablets und
  IP-Kameras, herstellerunabhängig, Open Source unter Apache-2.0.

**Abgrenzung:** BTV ist keine Wettkampf-, Zeitnahme- oder Ergebnisverwaltung.
Ergebnisberechnung, Strafrunden und Ergebnislisten bleiben beim angeschlossenen System.
BTV meldet Scheibenzustände, keine einzelnen Schüsse, und emuliert kein KES.

## Installation

Voraussetzung: Debian oder Ubuntu mit Python 3.11 oder neuer, systemd und Internetzugang
während der Installation. Installiert wird ein veröffentlichter Versionstag
(aktueller Stand: [Releases](https://github.com/richtertoralf/biathlon-target-vision/releases)):

```bash
git clone --branch v0.8.5 https://github.com/richtertoralf/biathlon-target-vision.git
cd biathlon-target-vision
./install.sh
```

Der Installer nutzt sudo, installiert die Pakete `python3`, `python3-venv`, `git` und
`libglib2.0-0` und richtet BTV als systemd-Dienst `biathlon-target-vision` ein, der unter
dem Systembenutzer `btv` automatisch startet.

```bash
sudo biathlon-target-vision --status     # Zustand, Adressen, Kameras, Sitzung
sudo biathlon-target-vision --upgrade    # auf den neuesten Versionstag aktualisieren
```

Upgrades erhalten Konfiguration, Kalibrierungen, Ereignisse, den Dienstzustand und die
Autostart-Einstellung. Start ohne Installation
für Entwicklung und Tests: [Bedienungsanleitung](docs/BEDIENUNG.md#ohne-installation-starten-entwicklung-und-tests).

## Kurzanleitung

1. **Öffnen:** Tablet-Bedienung unter `http://SERVER-IP:8091/`, Kontrollmonitor unter
   `/monitor`, Administration unter `/admin`. Tablets und Server müssen im selben,
   vertrauenswürdigen Netz sein; eine Anmeldung gibt es noch nicht.
2. **Bahnen wählen:** Auf jedem Tablet die betreuten Schießbahnen auswählen.
3. **Manuell erfassen:** „Bahn belegen“, Startnummer eingeben, gefallene Scheiben
   antippen, „Bahn verlassen“, nach dem mechanischen Aufrichten „Alle Scheiben
   aufgerichtet“ bestätigen.
4. **Optional Kameras:** Unter `/admin` Kamera mit RTSP-Adresse anlegen, Bahnen zuordnen
   und je Bahn im Kamerabild den Scheibenbereich kalibrieren. Danach erfasst die Kamera
   automatisch; Korrekturen am Tablet bleiben jederzeit möglich.
5. **Neue Veranstaltung:** Unter `/admin` die Sitzung abschließen und eine neue beginnen.

Ausführlich: [Bedienungsanleitung](docs/BEDIENUNG.md).

## Deinstallation

Anwendung entfernen; Daten, Konfiguration und Kalibrierungen bleiben dabei erhalten:

```bash
sudo systemctl disable --now biathlon-target-vision
sudo rm /etc/systemd/system/biathlon-target-vision.service
sudo rm -r /etc/systemd/system/biathlon-target-vision.service.d   # nur falls angelegt
sudo systemctl daemon-reload
sudo rm /usr/local/bin/biathlon-target-vision
sudo rm -r /opt/biathlon-target-vision
```

`/opt/biathlon-target-vision/backups/` enthält die Datensicherungen der Upgrades; vor dem
Löschen bei Bedarf an einen anderen Ort verschieben.

Optional zusätzlich alle Daten (Sitzungen, Journale, Konfiguration mit Kamera-Zugangsdaten,
Kalibrierungen) und den Systembenutzer löschen – **nicht rückgängig zu machen**:

```bash
sudo rm -r /var/lib/biathlon-target-vision
sudo userdel btv
```

Die mit `apt` installierten Systempakete werden auch von anderen Programmen genutzt und
bleiben bestehen. Videoaufzeichnungen erstellt BTV nicht; sie gehören zu einem separat
betriebenen Mediaserver.

## Dokumentation

- [Bedienungsanleitung](docs/BEDIENUNG.md): Ablauf am Schießstand, Sitzungen, Kameras, Status, Simulator
- [API und Integration](docs/API.md): REST, WebSocket und Datenvertrag für Zeitnahme und Livegrafik
- [Architektur und Betrieb](docs/ARCHITECTURE.md): Komponenten, Speicherung, Installation und Upgrades
- [Produktkonzept](docs/PRODUKTKONZEPT.md) und [Roadmap](docs/ROADMAP.md): Nutzen, geplante Erweiterungen, Prioritäten
- [Tests und Testergebnisse](docs/praxistests/README.md): chronologische Testübersicht mit Ergebnissen und Grenzen
- [Entwicklungsbericht](docs/ENTWICKLUNGSBERICHT.md): Entscheidungen, Tests und Grenzen

Mitarbeit auf Deutsch, Englisch oder Tschechisch ist willkommen:
[Contributing Guide](CONTRIBUTING.md).

## Lizenz

Licensed under Apache-2.0 – siehe [LICENSE](LICENSE) und [NOTICE](NOTICE).
