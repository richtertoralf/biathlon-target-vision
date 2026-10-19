# Roadmap

Stand: **19. Oktober 2026**, `main` nach PR #31 (`2e86ea9`): 15 offene und zwei
abgeschlossene Issues. Die Prioritäten und Reihenfolgen sind Empfehlungen aus der
Issue-Prüfung; sie ändern weder die GitHub-Issues noch den implementierten Umfang.
Die fachliche Zielbeschreibung steht im [Produktkonzept](PRODUKTKONZEPT.md), der
tatsächliche Entwicklungsstand im [Entwicklungsbericht](ENTWICKLUNGSBERICHT.md).
BTV ist in aktiver Entwicklung und nicht für produktiven Wettkampfbetrieb freigegeben.

## Nächster Meilenstein: Arberstadion-Praxistest

**Ende Oktober 2026 erstmals an realen Schießstandanlagen testen
([#13](https://github.com/richtertoralf/biathlon-target-vision/issues/13)).**
Jetzt Testprotokoll, unabhängige Referenzbeobachtung und Datensicherung vorbereiten.
Softwarestand, Kamera-/Bahnzuordnung, Kalibrierung, Netzwerk und Wetter festhalten.
Manuellen Ablauf, automatische Erfassung mit manuellen Korrekturen, Kameraausfall,
Wiederverbindung, zwei Tablets, Neustart und Sitzungswechsel prüfen; Journale,
Konfiguration, Kalibrierungen und geeignete reale Bildbelege sichern.
Ergebnisse auswerten und tatsächliche Fehler vor weiteren Funktionen priorisieren.

Als nächste kleine Codeänderungen **#30, danach #22** empfehlen; #28 möglichst vor
der tschechischen Begutachtung. #13 wartet nicht auf sämtliche P1-Erweiterungen:
für den beaufsichtigten Entwicklungstest einen geprüften Stand mit bekannten
Einschränkungen festlegen. Fehlender Zugriffsschutz ist dabei kein zwingender
Testblocker. Es gibt noch keine bestätigte Praxistauglichkeit oder Herstellerintegration.

## Priorisierte offene Issues

| Priorität | Issue | Kleinster sinnvoller nächster Schritt |
|---|---|---|
| **P0** | [#13 – Arberstadion-Test](https://github.com/richtertoralf/biathlon-target-vision/issues/13) | Vorbereiten, durchführen, Ergebnisse und Fehler dokumentieren. |
| **P1** | [#30 – Erfassungsstatus am Tablet](https://github.com/richtertoralf/biathlon-target-vision/issues/30) | Vorhandene Daten kompakt anzeigen; Kameraverbindung nicht mit zuverlässiger Beobachtung gleichsetzen. |
| **P1** | [#22 – ROI-Markierung](https://github.com/richtertoralf/biathlon-target-vision/issues/22) | Eindeutige Eckpunktführung; beliebige Reihenfolge nur bei ebenso einfacher, verlässlicher Validierung. |
| **P1** | [#28 – Alle Seiten dreisprachig](https://github.com/richtertoralf/biathlon-target-vision/issues/28) | Bestehende Sprachdatei auch für Monitor, Administration und Kalibrierung nutzen; Sitzungsverwaltung einschließen. |
| **P1** | [#20 – Bedienbegriffe abstimmen](https://github.com/richtertoralf/biathlon-target-vision/issues/20) | Bei #13 Rückmeldungen in EN/DE/CS sammeln; bis dahin bestehende Beschriftungen beibehalten. |
| **P1** | [#24 – Zugriffsschutz](https://github.com/richtertoralf/biathlon-target-vision/issues/24) | Zwei gemeinsame Passwörter für Bedienung und Administration; REST und WebSocket serverseitig schützen, einschließlich Sitzungsverwaltung. |
| **P1** | [#25 – Navigation und öffentlicher Lesezugriff](https://github.com/richtertoralf/biathlon-target-vision/issues/25) | Mit #24 konsistente Navigation und öffentliche Lesewege prüfen; Monitor und Zustandsabruf sind bereits öffentlich. |
| **P1** | [#23 – Kameraeingaben vereinfachen](https://github.com/richtertoralf/biathlon-target-vision/issues/23) | Nach Zugriffsschutz vollständige RTSP-Adresse administrativ bearbeiten; stabile interne ID erhalten, möglichst automatisch vergeben. |
| **P1** | [#14 – Journalansicht und Export](https://github.com/richtertoralf/biathlon-target-vision/issues/14) | Nach dem Test vorhandenen Journalabruf zeitbezogen darstellen; CSV/JSON auf Sitzung und feste obere Sequenz begrenzen. |
| **P1** | [#15 – Kamera-/Bahnzuordnung dokumentieren](https://github.com/richtertoralf/biathlon-target-vision/issues/15) | Ausdrücklich bestätigten Konfigurationsstand ohne Zugangsdaten protokollieren; keine zweite Konfigurationsverwaltung. |
| **P2** | [#16 – Schießposition je Einlage](https://github.com/richtertoralf/biathlon-target-vision/issues/16) | Liegend/stehend/unbekannt explizit zuordnen und korrigieren; kein Einfluss auf Einlagenbeginn oder Scheibenzustände. |
| **P2** | [#26 – Video-Geometrie-API](https://github.com/richtertoralf/biathlon-target-vision/issues/26) | Zugriffskonflikt klären, dann vorhandene Kalibrierungsgeometrie für einen konkreten externen Anwendungsfall bereitstellen. |
| **P2** | [#17 – Unabhängige Juryvorfälle](https://github.com/richtertoralf/biathlon-target-vision/issues/17) | Erst Bedienkonzept und Trennung von Meldung/Bewertung klären; laufende Einlagen nicht beeinflussen. |
| **P3** | [#18 – Schussbeobachtung](https://github.com/richtertoralf/biathlon-target-vision/issues/18) | Eingabeweg praktisch erproben, danach tatsächliche Schussbeobachtungen unabhängig von Zielzuständen erfassen. |
| **P3** | [#19 – Staffel-Reservepatronen](https://github.com/richtertoralf/biathlon-target-vision/issues/19) | Auf #18 aufbauend beobachtete Schüsse ausdrücklich klassifizieren; nichts aus Schussnummer oder Scheiben ableiten. |

## Reihenfolge und gemeinsame PRs

1. **Testvorbereitung #13 sofort**, parallel #30 → #22 und bei Bedarf #28.
   #20 beim Test mitbearbeiten; eigene Abschlusskriterien beibehalten.
2. **#24 + #25 in einem PR:** öffentliche Lesewege, geschützte Schreibwege und
   Navigation gemeinsam prüfen. **#23 anschließend** für geschützte RTSP-Bearbeitung.
3. **#14, dann #15 in getrennten PRs:** Journalansicht und neue Dokumentationsereignisse
   überschaubar halten. #16 kann nach dem Test als erste Funktionserweiterung
   vorgezogen werden, insbesondere bei konkretem Bedarf einer Liveproduktion.
4. **#26 nach Zugriffsentscheidung**, #17 nach fachlicher Klärung; anschließend
   **#18 + #19 als gemeinsames Entwicklungspaket** nach praktischem Bedienversuch.
   Ein gemeinsamer Implementierungs-PR ist sinnvoll, wenn #19 nur eine kleine
   Klassifizierungserweiterung von #18 bleibt.

**Echte technische Abhängigkeit:** #19 benötigt die Schussbeobachtung aus #18.
#14 bietet Darstellung/Export für #15, #17 und #18, ist aber keine Voraussetzung
für deren Ereignisspeicherung. #16 benötigt #14/#15 nicht; #28 ist nicht durch die
Begriffsrückmeldungen aus #20 blockiert. #22 und #23 getrennt halten, damit die
Kalibrierungshilfe nicht auf Zugriffsschutz wartet. Die übrigen Reihenfolgen sind
Empfehlungen oder fachliche Freigaben, keine technischen Blockaden.

## Offene Entscheidungen und Leitplanken

- **#26 versus #24:** #26 fordert die vollständige konfigurierte RTSP-URL ohne
  Anmeldung; sie kann Benutzername und Passwort enthalten. Vor Umsetzung entscheiden.
  Empfehlung: öffentliche Geometrie ohne Zugangsdaten, vollständige konfigurierte
  URL nur administrativ zugänglich.
- **Sitzungsgrenzen aus #29:** Journalansicht, Zuordnungsprotokoll, Positionen und
  Juryvorfälle brauchen einen eindeutigen Sitzungsbezug. Externe Cursor verwenden
  `(session_id, sequence)` gemäß [API](API.md). Eine beendete Einlage in der aktiven
  Sitzung ist kein Sitzungsarchiv; Archivbearbeitung gehört nicht beiläufig dazu.
  Konfiguration und Kalibrierungen bleiben gemeinsam, bestätigte Zuordnungsstände
  sind Dokumentation und ändern beim Replay keine Kamerakonfiguration.
- **Juryvorfälle:** Meldung ist keine Entscheidung. Zustände wie „gemeldet“,
  „in Prüfung“ und „abgeschlossen“ nur bei nachgewiesenem Arbeitsablauf einführen;
  keine automatische Strafentscheidung.
- **Schussbeobachtung:** Vor Programmierung gesonderten Beobachter, Tastengerät
  oder automatische Quelle praktisch bewerten. Keine zusätzlichen Adapter auf
  Vorrat; Zielzustände erzeugen keine Schuss- oder Fehlschussereignisse.
- **Entwicklungsphase:** Ältere Kompatibilitätsforderungen in #14–#19 sind kein
  Auftrag für Migrationen früherer Entwicklungsversionen. Daten nicht stillschweigend
  löschen; Formatänderungen dokumentieren, Replay deterministisch halten und
  Kamerakonfiguration/Kalibrierungen möglichst erhalten. Vorhandenen Ereigniskern,
  JSONL-Journal und Browserarchitektur nutzen; keine neuen Dienste oder Datenbanken.

## Bereits abgeschlossen

- [#21 – Nachträgliche BIB-Eingabe](https://github.com/richtertoralf/biathlon-target-vision/issues/21): Scheibenzustände bleiben erhalten (PR #27).
- [#29 – Aufzeichnungssitzungen](https://github.com/richtertoralf/biathlon-target-vision/issues/29): Sitzung abschließen und neu starten, Archive erhalten (PR #31).
