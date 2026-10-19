# Biathlon Target Vision

**Digitales Schießstand-Informationssystem für mechanische Klappscheibenanlagen**

*Stand: 18. Oktober 2026, Implementierung auf `main` nach PR #10 und #11.
„Vorhanden“ bezeichnet implementierte Funktionen, keine abgeschlossene
Praxistestvalidierung. Geplante Erweiterungen benötigen eine gesonderte fachliche
Freigabe; Perspektiven sind noch keine Umsetzungszusagen. Keine IBU-Zulassung.*

## 1. Problem, Bedarf und Lösung

Elektronische Schießanlagen können Daten für Zeitnahme, Jury und TV bereitstellen.
BTV richtet sich an Betreiber mechanischer Anlagen, denen eine solche
Datenschnittstelle fehlt.

Ein Schwerpunkt sind mechanische 10-Meter-Luftgewehranlagen für Schüler- und
Nachwuchsveranstaltungen. Die jeweils geltenden Wettkampfbestimmungen legt BTV
nicht fest; IBU-Regeln für andere Anlagen werden nicht pauschal auf diesen Einsatz
übertragen.

Ohne Datenschnittstelle müssen Kampfrichter ihre Beobachtungen gesondert an die
Zeitnahme weitergeben. Zuschaueranzeigen und Livestreams erhalten diese Daten
nicht automatisch.

Genau hier liegt der Bedarf: **bestehende mechanische Zielanlagen digital
anbinden, ohne sie ersetzen zu müssen.**

Biathlon Target Vision (BTV) stellt dafür ein herstellerunabhängiges
Open-Source-System bereit: Es erfasst Klappscheibenzustände am Tablet oder durch
Kamerabildanalyse, führt Informationen zentral zusammen, protokolliert Änderungen
und stellt aktuelle Zustände über REST und WebSocket bereit. Schon ohne Kamera
ist reguläre manuelle Erfassung möglich. Automatische Beobachtungen entlasten die
Kampfrichter; ihre unmittelbaren Korrekturen haben Vorrang. Sensorik direkt an den
Scheiben ist geplant, aber noch nicht implementiert.

## 2. Für wen ist BTV gedacht?

- **Schießstandsbetreiber und Vereine:** Mechanische 10-m-Anlagen weiterverwenden und schrittweise digitalisieren.
- **Wettkampfveranstalter:** Helfer flexibel einsetzen und die Abläufe aller Bahnen zentral überblicken.
- **Kampfrichter und Helfer:** Mit wenigen Aktionen erfassen, beobachten und falsche Zustände sofort korrigieren.
- **Zeitnahmeunternehmen:** Strukturierte Live-Daten aus dem Schießstand zur Einbindung in eigene Systeme; eine konkrete Integration ist noch zu entwickeln und zu prüfen.
- **Jury und Wettkampfleitung:** Aktueller Überblick sowie nachvollziehbare Ereignisse und spätere Vorfallsberichte.
- **Stadionsprecher, Zuschauer und Livestream-/TV-Produzenten:** Datenbasis für anzubindende Anzeigen und Schießstandgrafiken; BTV enthält keine fertige TV-Integration.

## 3. So läuft eine Schießeinlage praktisch ab

1. **Bahn vorbereiten:** Die fünf Scheiben tatsächlich aufrichten und die Vorbereitung bestätigen. Ist die Bahn unbelegt, wird sie grün (frei und bereit). Unbekannte Zustände gelten nicht als bereit.
2. **Sportler kommt:** „Bahn belegen“ drücken; die Kachel wird gelb. Die Startnummer kann sofort oder später eingegeben werden.
3. **Schießen beobachten:** Die fünf Scheibenzustände werden von einer Kamera oder manuell am Tablet erfasst. Schwarz = aufgerichtet, Weiß = gefallen. Jede Scheibe kann unmittelbar korrigiert werden; die Korrektur hat Vorrang.
4. **Sportler geht:** „Bahn verlassen“ drücken; ohne abgeschlossene Rückstellung wird die Bahn grau.
5. **Scheiben zurückstellen:** Nach bestätigter vollständiger Rückstellung ist die freie Bahn wieder grün. Verlassen und Rückstellung dürfen in beliebiger Reihenfolge erfolgen. Eine zuverlässig beobachtete vollständige Rückstellung kann die Kamera bestätigen; fünf unverändert aufgerichtete Scheiben allein reichen dafür nicht.

Mehrere Tablets arbeiten gleichzeitig und synchron. Ein Helfer kann eine frei gewählte Anzahl von Bahnen anzeigen; wie viele er zuverlässig betreuen kann, entscheidet die Praxis.

Es gibt keine sichtbare Wahl zwischen manuellem, automatischem und Mischbetrieb.
Bei Kameraausfall oder unklarer Erkennung kann unmittelbar manuell weitergearbeitet
werden; Startnummer, laufende Einlage und Ereignisse bleiben erhalten. Bei Ausfall
der Verbindung zum BTV-Server können Tablets dagegen keine Eingaben bestätigen.

## 4. Bestehende Funktionen und technische Einbindung

- Manuelle Scheibenerfassung und unmittelbare Korrekturen mit Vorrang gegenüber der Kamera; Tablet-Bedienung in Englisch, Deutsch und Tschechisch. Administration, Kalibrierung und Monitor sind derzeit deutsch.
- Optische Auswertung von RTSP-IP-Kameras über OpenCV, mit Kamera-/Bahnzuordnung und browserbasierter Kalibrierung. Bisher synthetisch getestet; reale Zielanlagen stehen noch zur Validierung aus.
- Zentraler, schreibgeschützter Schießstandmonitor; gleichzeitige Tablet-Bedienplätze; Startnummern- und Bahnbelegungserfassung.
- Getrennte Aufzeichnungssitzungen: über die Administration abschließen und neu beginnen, Journale und Korrekturbelege erhalten; gemeinsame Kamerakonfiguration und Kalibrierungen bleiben bestehen. Keine Wettkampfplanung.
- Dauerhaftes JSONL-Ereignisjournal mit serverseitigen Annahmezeiten und vorhandenen Beobachtungszeitpunkten; Wiederherstellung nach Neustart und Abruf über die API. Noch keine zeitbezogene Journaloberfläche oder formatierten Berichte.
- Aktuelle Kamera-/Bahnzuordnung in der persistenten Konfiguration und Administration. Mehrere Bahnen können eine Kamera nutzen; je Bahn ist höchstens eine Kamera zuständig. Eine Änderungshistorie dieser Zuordnung fehlt noch.
- Protokollierte manuelle Korrekturen mit automatischem Vergleichswert; nach Möglichkeit ein Kameraausschnitt als Vergleichsbeleg. Keine durchgehende Videoaufzeichnung.
- REST- und WebSocket-Schnittstellen für die Integration in Zeitnahme- und Grafiksysteme. Eine konkrete Integration ist jeweils zu prüfen; BTV berechnet keine offiziellen Ergebnisse oder Strafen.
- Lokaler Linux-Betrieb mit Installer und systemd-Dienst, ohne Cloudpflicht. Keine spezielle Tablet-App erforderlich. Die Anwendung ist für ein vertrauenswürdiges lokales Netz ausgelegt und besitzt keine Anmeldung oder Juryrollenverwaltung.

## 5. Geplante Erweiterungen – noch nicht implementiert

Zusätzliche Erfassungsfelder sollen administrativ nach Bedarf zuschaltbar sein,
ohne eine Wettkampfverwaltung einzuführen oder den normalen Bahnbedienablauf zu
ändern. Die konkrete Aktivierung und Umsetzung sind Gegenstand des noch
freizugebenden Entwicklungsplans.

Die folgenden Regelbezüge wurden anhand der IBU-Fassungen EN 2026 und DE 2025
geprüft. Die Sprachfassungen sind nicht identisch datiert; veröffentlichte Quellen
und bestehende Fachterminologie stehen in [TERMINOLOGIE.md](TERMINOLOGIE.md).
Die Bezüge dienen der Planung von Beobachtungen und Berichten, nicht der
automatischen Regelprüfung oder einer IBU-Zertifizierung.

**IBU 8.3 – Schießposition**

Zuordnung von liegendem oder stehendem Anschlag zur Einlage, mit einfacher Auswahl,
Korrektur, Journal und Live-Ausgabe für externe Anzeigen. Eine fehlende Angabe
bleibt unbekannt. Die Schießposition des Sportlers ist unabhängig von der
mechanischen Scheibenstellung `standing` (aufgerichtet).
Fundstelle: [IBU DE 2025, 8.3.1–8.3.2, PDF 51–52](https://assets.ctfassets.net/cz0vl36hcq0x/4YTdYSpJfbDUU5ruU6RQDT/5fa20af436257a35eb02f400ecfbc7a3/Rules_2025_DE_cap3.pdf#page=51).

**IBU 8.7.5 – Schussbeobachtung**

Optionales Bedienfeld für tatsächlich beobachtete abgegebene Schüsse, getrennt
von Scheibenzuständen und deren Korrekturen. Daraus folgt keine Treffer- oder
Fehlschusswertung. IBU 8.7.5 verlangt drei unabhängige Personen oder Methoden;
bei elektronischer Trefferwertung zwei getrennte Beobachtungen durch Offizielle.
Synchronisierte Ansichten desselben BTV-Datensatzes sind keine unabhängigen
Beobachtungen. [IBU EN 2026, 8.7.5, PDF 51](https://assets.ctfassets.net/cz0vl36hcq0x/7mkQn1kQTB7VzlUZHAcuec/c8897efcf14ccded0f82af3513c6e5ef/ECR_Rules_2026_cap03.pdf#page=51).

**IBU 8.2.2 – Staffel-Reservepatronen (Nachlader)**

Kennzeichnung tatsächlich beobachteter Schüsse mit Staffel-Reservepatronen.
IBU 8.2.2 beschreibt nach den ersten fünf Schüssen bis zu drei einzeln von Hand
zu ladende Reservepatronen. Ersatz bei verlorenen oder versagenden Patronen nach
8.4.2/8.6 ist davon zu unterscheiden. BTV soll keine Verwendung aus verbliebenen
Scheiben ableiten oder Strafen berechnen.
[IBU DE 2025, 8.2.2 und 8.4.2, PDF 51–52](https://assets.ctfassets.net/cz0vl36hcq0x/4YTdYSpJfbDUU5ruU6RQDT/5fa20af436257a35eb02f400ecfbc7a3/Rules_2025_DE_cap3.pdf#page=51).

**IBU 8.4.2, 8.6 und 8.7.1–8.7.4 – Juryvorfälle**

Geplant ist eine von der laufenden Bahnbedienung unabhängige Vorfallserfassung:
Magazin-/Munitionsprobleme, beschädigte Gewehre, falsch eingestellte oder defekte
Scheiben, Crossfire und relevante Unterbrechungen. Vorfälle müssen auch ohne
bekannte BIB oder aktive Einlage dokumentierbar sein und können mehrere Bahnen
betreffen. Freitext und Textvorlagen sollen Beobachtung, Regelbezug und Zeitangaben
festhalten. [IBU DE 2025, 8.4.2, 8.6 und 8.7.1–8.7.4, PDF 52–56](https://assets.ctfassets.net/cz0vl36hcq0x/4YTdYSpJfbDUU5ruU6RQDT/5fa20af436257a35eb02f400ecfbc7a3/Rules_2025_DE_cap3.pdf#page=52).

Eine Meldung bestätigt weder einen Regelverstoß noch eine Strafe oder einen
Zeitausgleich. Zuständige Offizielle entscheiden. Eine spätere Ausgabe für
Zeitnahme oder Grafik muss Meldungen als solche kennzeichnen; eine direkte
Anbindung oder automatische Veröffentlichung für Zuschauer ist nicht vorhanden.

**Journalberichte**

Geplant sind eine lesende Journalansicht und Exporte nach Startnummer, Bahn,
Einlage, Zeitraum und später Vorfall. Server-Annahmezeit und tatsächliche oder
nachträglich gemeldete Beobachtungszeit müssen unterscheidbar bleiben. Der
Zeitpunkt einer Tableteingabe ist kein präzise gemessener Schusszeitpunkt.

Ein Konfigurationsprotokoll soll nachvollziehbar festhalten, welche Kamera welchen
Bahnen zugeordnet war. Vorhanden ist bisher nur die aktuelle Zuordnung; ältere
Stände dürfen daraus nicht rekonstruiert oder behauptet werden. Veröffentlichte
Berichte sollen keine RTSP-Adressen oder Zugangsdaten enthalten.

**Zusätzliche Erfassungsquelle Sensor**

Sensoren an Klappscheiben sind als zusätzliche Quelle geplant. Hardware und
Adapter fehlen; auch solche Beobachtungen sollen manuellen Korrekturen unterliegen.

## 6. Perspektiven ohne Umsetzungszusage

Transponder zur Unterstützung der Sportlerzuordnung und zusätzliche
KI-/ML-Verfahren sind lediglich längerfristige Prüfoptionen. Ob sie benötigt werden,
hängt von Praxiserfahrungen ab. Derzeit arbeitet die Kameraauswertung mit einfachen
OpenCV-Verfahren; ein Modelltraining ist nicht Bestandteil des Entwicklungsstands.

## 7. Grenzen und nächster Schritt

BTV dokumentiert bisher mechanische Scheibenzustände, nicht einzelne abgegebene Schüsse. Aus einer stehen gebliebenen Scheibe darf kein Schuss- oder Fehlschusszeitpunkt abgeleitet werden.

Zuständige Kampfrichter und Jury bleiben für Beobachtungen und Entscheidungen verantwortlich. Die IBU-Regelbezüge dienen der fachlichen Planung optionaler Erfassung und stellen keine Zulassung dar.

Ein Praxistest mit realen Klappscheibenanlagen im Arberstadion ist für Ende Oktober
2026 vorgesehen. Vorrang haben die vorhandene Erfassung, manuelle Priorität,
Bedienbarkeit und Verhalten bei Ausfällen. Interessierte tschechische Zeitnehmer
sollen Anwendung und Schnittstellen begutachten und eine mögliche Anbindung
beurteilen können; eine geprüfte Herstellerintegration wird nicht behauptet.

BTV bleibt auf Schießstanderfassung und Dokumentation begrenzt. Keine
Wettkampforganisation, Ergebnisberechnung, automatische Strafentscheidung oder
KES-Emulation. Neue Funktionen werden erst nach fachlicher Freigabe umgesetzt.

Installation und vollständiger Bedienablauf: [README](../README.md).
Vorhandene Technik: [Architektur](ARCHITECTURE.md) und [API](API.md).
Tatsächliche Prüfungen und Grenzen: [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md).
