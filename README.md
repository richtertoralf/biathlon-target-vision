# Biathlon Target Vision

**Herstellerunabhängige Schießerfassung für mechanische Biathlon-Klappscheiben mit optischer oder sensorbasierter Treffererkennung und Kurvinen-KES-kompatibler Datenausgabe.**

## Projektübersicht

Biathlon Target Vision ist ein kostengünstiges, eigenständig betreibbares Open-Source-System zur Digitalisierung mechanischer Biathlon-Klappscheibenanlagen.

Der Schwerpunkt liegt auf temporären 10-Meter-Luftgewehr-Schießständen, wie sie bei Schülercups, Nachwuchswettkämpfen, Trainingsveranstaltungen und Gästeschießen eingesetzt werden.

Das System verbindet zwei Aufgaben:

1. **Manuelle Bahnbelegung:** Kampfrichter ordnen Sportler über Tablets oder alternative Tastenfelder den Schießbahnen zu.
2. **Automatische Treffererfassung:** Kameras oder Sensoren erkennen die Zustandsänderungen der fünf Klappscheiben.

Die erfassten Daten werden über eine Schnittstelle im vorhandenen seriellen Kurvinen-KES-Protokoll ausgegeben.

Damit lassen sich mechanische Schießstände an bestehende Zeitnahme-, Auswertungs- und Anzeigesysteme anbinden, ohne deren Software verändern zu müssen, sofern diese das unterstützte KES-Protokoll verarbeiten.

## 1. Manuelle Bahnbelegung

Die Zuordnung der Sportler zu den Schießbahnen bleibt Aufgabe der Kampfrichter.

### Variante A: Tablet

|Eine browserbasierte Bedienoberfläche ermöglicht die Verwaltung von bis zu 20 oder mehr Schießbahnen.

Jedes Tablet kann individuell konfiguriert werden:

- Anzeige sämtlicher Schießbahnen
- Anzeige nur ausgewählter Bahnen, beispielsweise drei bis fünf
- Gleichzeitiger Betrieb mehrerer Tablets

Die Bedienung ist bewusst einfach gehalten:

1. Schießbahn auswählen.
2. Startnummer über ein großes numerisches Tastenfeld eingeben.
3. Startnummer bestätigen.
4. Beim Verlassen des Schießstandes die Bahn per Schaltfläche freigeben.

Die Oberfläche wird für die Bedienung im Freien mit großen, kontrastreichen Schaltflächen ausgelegt.|

![Bahnbelegung erfassen](Schießstand-Erfassung_auf_Tablet_UI.png) |
|---|---|

### Variante B: Physisches Tastenfeld

Alternativ kann die Bahnbelegung über ein robustes Bediengerät mit fühlbaren Tasten erfolgen.

Vorgesehen sind:

- Auswahl der zugeordneten Schießbahn
- Numerische Eingabe der Startnummer
- Bestätigung und Korrektur der Eingabe
- Freigabe der Schießbahn

Die physische Tastatur soll insbesondere bei niedrigen Temperaturen, Schneefall und der Bedienung mit Handschuhen Vorteile bieten.

Beide Bedienvarianten verwenden dieselbe zentrale Bahnverwaltung.

## 2. Automatische Treffererfassung

Die Erkennung der Treffer erfolgt unabhängig von der manuellen Startnummerneingabe.

### Variante A: Optische Erfassung

Handelsübliche IP-Kameras beobachten die mechanischen Klappscheiben.

Die Bildverarbeitung erkennt, welche Ziele aufgerichtet beziehungsweise gefallen sind.

Eigenschaften:

- Nutzung vorhandener mechanischer Klappscheiben ohne Umbau
- RTSP-basierte Videoquellen
- Mehrere Schießbahnen pro Kamera
- Konfigurierbare Zielpositionen
- Automatische Erkennung von Treffer- und Rückstellvorgängen
- Erkennung unklarer oder verdeckter Zielzustände

Für eine Anlage mit 20 Bahnen werden zunächst ungefähr sieben Kameras vorgesehen, sofern die Erfassung von drei Bahnen pro Kamera im Praxistest bestätigt wird.

### Variante B: Sensorbasierte Erfassung

Alternativ werden die einzelnen Klappscheiben mit einfachen Sensoren ausgestattet.

Als bevorzugte Lösung werden berührungslose Hall-Sensoren mit Magneten untersucht. Auch Reedkontakte oder geeignete mechanische Schalter kommen infrage.

Ein ESP32-Mikrocontroller erfasst die Zustände der fünf Ziele einer Schießbahn und übermittelt diese über WLAN an den zentralen Server.

Eigenschaften:

- Fünf Sensoren pro Schießbahn
- Automatische Erkennung gefallener und zurückgestellter Ziele
- Drahtlose Datenübertragung
- Wettergeschützte Elektronik
- Keine Kameras oder Bildverarbeitung erforderlich

Die endgültige Sensorbefestigung wird anhand der tatsächlichen Mechanik der verwendeten Klappscheiben entwickelt.

Beide Erfassungsarten können innerhalb derselben Veranstaltung eingesetzt werden.

## 3. Unabhängige Erfassung und Zuordnung

Ein wesentliches Merkmal ist die Trennung zwischen Treffererkennung und Bahnbelegung.

Die automatische Erfassung arbeitet auch dann, wenn noch keine Startnummer für eine Bahn eingetragen wurde.

Dadurch werden typische Bedienverzögerungen berücksichtigt:

- Der erste Treffer erfolgt vor der Startnummerneingabe.
- Die Startnummer wird erst während der Schießeinlage eingetragen.
- Der Kampfrichter gibt die Bahn verspätet frei.
- Eine falsche Startnummer muss korrigiert werden.

Trefferereignisse bleiben erhalten und können einer Schießeinlage nachträglich zugeordnet werden.

Widersprüchliche Zuordnungen müssen erkannt werden. Die Software darf keine Sportlerzuordnung erraten.

## 4. Kurvinen-KES-kompatible Schnittstelle

Biathlon Target Vision soll das bereits dokumentierte serielle Kurvinen-KES-PC-Nachrichtenprotokoll bereitstellen.

Referenz ist die vorhandene Schnittstellendokumentation `KES-PC-Message-description-2001.pdf`, die bereits für die Kurvinen-Integration verwendet wurde.

Zu den dokumentierten Ereignistypen gehören:

| Typ | Ereignis |
|---|---|
| 1 | BEGIN – Beginn |
| 2 | SHOOTER – Startnummer |
| 3 | SHOT – Schussmeldung |
| 4 | HIT – Treffer |
| 5 | LEAVE – Bahn verlassen |
| 6 | CLEAR – Zurücksetzen |
| 7 | STOP – Stopp |
| 8 | HEARTBEAT – Verbindungstest |
| 9 | MISS – Fehlschuss |

Der Adapter erzeugt ausschließlich durch vorhandene Daten und das dokumentierte Protokoll gedeckte Ereignisse.

Insbesondere darf ein Fehlschusszeitpunkt nicht erfunden werden, wenn die Zielerfassung nur den Zustand der Klappscheiben kennt.

Die Ausgabe erfolgt zunächst über einen TCP-Server, der die vorhandene serielle KES-Übertragung über Ethernet nachbildet.

Eine direkte serielle Ausgabe kann später ergänzt werden.

Die Kompatibilität wird anhand vorhandener Originaldaten aus Oberwiesenthal, des KES-Simulators und des bestehenden KES-Parsers geprüft.

## 5. Technische Architektur

Das System besteht aus vier funktionalen Komponenten:

**Lane Management**
- Verwaltung aller Schießbahnen
- Startnummernzuordnung
- Tablet- und Tastenfeldbedienung
- Mehrbenutzerbetrieb

**Target Detection**
- Optische Treffererkennung über Kameras
- Alternativ Sensorerfassung über ESP32
- Einheitliche Übermittlung der Zielzustände

**Event Processing**
- Zusammenführung von Bahnbelegung und Trefferereignissen
- Behandlung verspäteter Eingaben
- Speicherung und Wiederherstellung relevanter Ereignisse

**KES Protocol Adapter**
- Umsetzung in das vorhandene KES-Nachrichtenformat
- TCP-basierte Bereitstellung
- Anschluss kompatibler externer Systeme

## 6. Betrieb und Einsatz

Biathlon Target Vision soll auf einem handelsüblichen Linux-Rechner ohne Cloud-Anbindung betrieben werden können.

Die Software wird auf einfache Installation, geringen Ressourcenbedarf und zuverlässigen lokalen Betrieb ausgelegt.

Es werden möglichst vorhandene Open-Source-Komponenten und Standardprotokolle genutzt. Zusätzliche Frameworks, Datenbanken und Verwaltungsdienste sollen nur eingesetzt werden, wenn sie technisch notwendig sind.

Eine eigene Wettkampfverwaltung, Zeitnahme oder Ergebnisgrafik ist nicht Bestandteil des Projekts.

## 7. Entwicklungsstrategie

Die erste Entwicklungsphase konzentriert sich auf:

1. Funktionsfähige Tablet-Bedienung für die Bahnbelegung.
2. Optische Erkennung der fünf Klappscheiben für zunächst eine bis drei Bahnen.
3. Zusammenführung der Ereignisse.
4. Ausgabe über den vorhandenen KES-Protokollstandard.
5. Praxistests mit realen mechanischen Biathlonanlagen.

Anschließend werden die physische Tastaturbedienung und die ESP32-Sensorerfassung als alternative Eingabe- beziehungsweise Erfassungsmethoden integriert.

## Projektziel

Biathlon Target Vision soll bestehenden mechanischen Biathlon-Schießständen eine kostengünstige digitale Treffererfassung ermöglichen.

Der Einsatz handelsüblicher Kameras oder preiswerter Sensorik reduziert die Abhängigkeit von proprietären elektronischen Zielanlagen.

Durch die Trennung von Sportlerzuordnung, Treffererfassung und standardisierter Datenausgabe entsteht eine flexible Lösung für Sportvereine, Veranstalter, Zeitnehmer und Systemintegratoren.
