# Architektur – Biathlon Target Vision

## Grundkonzept

Die Anwendung orientiert sich technisch an [LiveScore](https://github.com/richtertoralf/LiveScore), übernimmt jedoch nur die benötigten Komponenten.

- Python 3 mit FastAPI und Uvicorn
- Ein zentraler Linux-Serverprozess
- HTML, CSS und JavaScript ohne Frontend-Buildsystem
- REST-API und WebSockets für die Bedienoberflächen
- Gemeinsamer Serverzustand für alle Bedienplätze
- Lokale Speicherung von Konfiguration und Ereignissen
- Betrieb als systemd-Dienst unter Debian/Ubuntu
- Kein Internetzugang für den Wettkampfbetrieb erforderlich

## Funktionsbereiche

### Bahnbelegung

- Browserbasierte Tablet-Oberfläche
- Alternativ physisches Tastenfeld
- Beliebig konfigurierbare Anzeige der Schießbahnen je Bedienplatz
- Mehrere gleichzeitig arbeitende Kampfrichter
- Automatische Synchronisierung aller Bedienplätze

### Treffererfassung

Zwei austauschbare Erfassungsarten:

- **Optisch:** IP-Kameras mit RTSP und Bildauswertung
- **Sensorbasiert:** Sensoren an den Klappscheiben, beispielsweise mit ESP32 und WLAN

Beide liefern ein gemeinsames internes Ereignisformat.

### Ereignisverarbeitung

- Treffererfassung unabhängig von der Startnummerneingabe
- Zuordnung der Sportler zu Schießeinlagen
- Behandlung verspäteter Eingaben und Bahnfreigaben
- Nachvollziehbare Speicherung der Ereignisse
- Keine automatische Zuordnung bei widersprüchlichen Daten

### KES-Schnittstelle

Ausgabe über TCP im dokumentierten Kurvinen-KES-Nachrichtenformat.

Die Originaldokumentation im Repository ist die verbindliche Protokollreferenz.

## Bedienoberfläche

Die Oberfläche unterstützt drei Sprachen:

- English (EN) – Standardsprache
- Deutsch (DE)
- Čeština (CS)

Die Sprache wird je Browser gewählt und lokal gespeichert.

Übersetzungen werden zentral in JavaScript verwaltet, ohne zusätzliches Internationalisierungsframework.

Die Bedienung ist für den Wettkampfbetrieb mit großen Schaltflächen, möglichst wenigen Eingaben und klaren Statusanzeigen ausgelegt.

## Architekturprinzipien

- Eine Anwendung statt verteilter Dienste.
- Klare Trennung von Bedienung, Treffererfassung und Protokollausgabe.
- Keine unnötigen Abstraktionen oder zusätzlichen Abhängigkeiten.
- Vorhandene Standardkomponenten bevorzugen.
- Erweiterungen nur bei konkretem Bedarf.
- Einfache Installation, Wartung und Fehlerdiagnose.
