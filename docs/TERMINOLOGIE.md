# Verbindliche GUI-Terminologie

Geprüft am 18.10.2026. Sportbegriffe werden aus den unten verlinkten veröffentlichten
Regelwerken übernommen, nicht selbst übersetzt. Grammatische Beugung und die im
Regelwerk verwendeten Kurzformen sind zulässig. API-Bezeichner bleiben unverändert.

## Quellen und Fassungen

- **EN:** IBU Event and Competition Rules, **Version 2026**, auf der
  [IBU-Downloadseite](https://www.biathlonworld.com/inside-ibu/downloads/downloads-documents-sport-and-event)
  als September 2026 veröffentlicht:
  [Original-PDF](https://assets.ctfassets.net/cz0vl36hcq0x/7mkQn1kQTB7VzlUZHAcuec/c8897efcf14ccded0f82af3513c6e5ef/ECR_Rules_2026_cap03.pdf).
- **DE:** IBU Veranstaltungs- und Wettkampfregeln, **Version 2025**, auf der
  [deutschen IBU-Seite](https://www.biathlonworld.com/de/inside-ibu/sports-and-event/event-competition-rules-biathlon)
  als Juli 2025 verlinkt:
  [Original-PDF](https://assets.ctfassets.net/cz0vl36hcq0x/4YTdYSpJfbDUU5ruU6RQDT/5fa20af436257a35eb02f400ecfbc7a3/Rules_2025_DE_cap3.pdf).
- **CS:** IBU Pravidla soutěží a závodů, **Verze 2025**, vom Český svaz biatlonu
  als „Pravidla IBU 2025 česky se změnami“
  [veröffentlicht](https://www.biatlon.cz/domaci/vysledky/pravidla-biatlonu-a-formulare-k-soutezim/):
  [Verbands-PDF](https://www.biatlon.cz/wp-content/uploads/2025/11/Pravidla-IBU-2025-cesky-se-zmenami.pdf).
  Es enthält zwei gedruckte Seiten pro PDF-Seite. Die separat verlinkte
  Sicherheitsaktualisierung ab 1.4.2026 wird für diese Terminologieprüfung nicht
  als Quelle verwendet.

Die unterschiedlichen Fassungen sind die tatsächlich dort angebotenen
Sprachfassungen, keine behauptete gemeinsame Ausgabe 2026. Fundstellen beziehen
sich auf die Artikelnummern der jeweiligen Fassung.

## Belegte Sportbegriffe

| Bedeutung | Englisch | Deutsch | Tschechisch | Fundstelle in EN / DE / CS |
|---|---|---|---|---|
| Gesamter Schießbereich | shooting range | Schießstand | střelnice | jeweils 3.4 und 3.4.1 |
| Einzelne nummerierte Bahn | shooting lane | Schießbahn | střelecký stav | jeweils 3.4.3.1 |
| Eine Schießeinlage | shooting bout | Schießeinlage | střelecká položka | jeweils 1.4.10.4, Erklärung zu Spalte 7; außerdem 8.2.1 |
| Beschossene Scheibe | target | Scheibe / Zielscheibe | terč | jeweils 3.4.4; DE zusätzlich 3.1.2.3 |
| Treffer | hit | Treffer | zásah | jeweils 3.1.2.3 und 8.7.3.1 |
| Fehlschuss | miss | Fehlschuss | nezásah | jeweils 3.1.2.3 |
| Nummer des Sportlers | start number / bib number | Startnummer | startovní číslo | jeweils 6.5 und 3.1.2.3 |
| Scheiben erneut bereitstellen | reset | zurückgesetzt | nové nastavení | jeweils 8.7.3 und 8.7.3.1; DE/CS dort als gebeugte Verbformen bzw. Nominalgruppe |

Direkte PDF-Seiten für die zentralen Definitionen:
[EN Bahn/Scheibe, PDF 32](https://assets.ctfassets.net/cz0vl36hcq0x/7mkQn1kQTB7VzlUZHAcuec/c8897efcf14ccded0f82af3513c6e5ef/ECR_Rules_2026_cap03.pdf#page=32),
[DE Bahn/Scheibe, PDF 34](https://assets.ctfassets.net/cz0vl36hcq0x/4YTdYSpJfbDUU5ruU6RQDT/5fa20af436257a35eb02f400ecfbc7a3/Rules_2025_DE_cap3.pdf#page=34),
[CS Bahn/Scheibe, PDF 19](https://www.biatlon.cz/wp-content/uploads/2025/11/Pravidla-IBU-2025-cesky-se-zmenami.pdf#page=19).
Die Erklärung der Schießeinlage steht in EN/DE auf PDF-Seite 7, in CS auf PDF-Seite 4.
Treffer/Fehlschuss und Startnummer stehen in 3.1.2.3 auf PDF-Seite EN 28, DE 29, CS 17.
Die Rücksetzbegriffe stehen in 8.7.3.1 auf PDF-Seite EN 51, DE 55, CS 29.

GUI-Kurzformen `Lane`, `Bahn`, `Stav`, `Bout`, `Einlage`, `Položka` sowie `Bib`
werden nur im eindeutigen Kontext ihrer Bahn-/Einlagenkacheln verwendet. Sie
führen keine zusätzlichen Sportkonzepte ein. `Bib` wird insbesondere in EN
3.1.2.3 und 1.4.11.c auch für die Nummer verwendet; es ist kein nachgewiesener
Übersetzungsfehler. Deutsch bezeichnet die mechanischen Ziele in allen
projektspezifischen Browserseiten als **Scheiben**. Tschechisch verwendet `terč`,
nicht das den Zieleinlauf bezeichnende `cíl`.

## Technische UI-Bezeichnungen ohne zugesicherte IBU-Terminologie

| Funktion | Englisch | Deutsch | Tschechisch | Einordnung |
|---|---|---|---|---|
| Mechanische Stellung `standing` | Standing | Aufgerichtet | Vztyčený | technische Zustandsbeschreibung, nicht Anschlag stehend |
| Mechanische Stellung `fallen` | Fallen | Gefallen | Sklopený | technische Zustandsbeschreibung, keine Schussmeldung |
| Unsicherer Zustand | Unknown | Unbekannt | Neznámý | technischer Beobachtungsstatus, kein Fehlschuss |
| Bedienbestätigung der Rückstellung | All targets are standing | Alle Scheiben aufgerichtet | Všechny terče jsou vztyčené | technischer Vorgang dieser Anwendung; keine behauptete gleichlautende IBU-Schaltfläche |
| Betriebsarten | Manual / Automatic / Mixed | Manuell / Automatisch / Mischbetrieb | Ruční / Automatický / Smíšený | Softwarebetrieb, keine Wettkampfformate |
| Priorität/Freigabe | M / Auto ↩ | M / Auto ↩ | M / Auto ↩ | manuelle Übersteuerung und Rückgabe an die Automatik |

Die neuen Bedienaktionen `Occupy lane / Bahn belegen / Obsadit stav` und
`Leave lane / Bahn verlassen / Opustit stav` sowie die drei Vorbereitungsstatus
sind technische UI-Beschreibungen. Ihre Sportbegriffe verwenden die oben belegten
Kurzformen; die vollständigen Schaltflächen sind keine behaupteten IBU-Zitate.

Auch Kameraverbindung, RTSP-Adresse, Kalibrierung, Gesamt-ROI, Bildverschiebung,
Tablet-Nummer, Entwurf, Speichern, Freigabe einer Belegung und Netzwerk-/Speicherstatus
sind **nicht als IBU-Begriffe belegt**. Sie beschreiben Technik oder die Bedienung
des Systems. `Range control` ist die technische Überschrift der Bedienansicht.
Eine gespeicherte Einlage ist keine Ergebnisverwaltung; die Software entscheidet
nicht über sportrechtliche Trefferwertung.

Der Terminologieabgleich überträgt keine Kleinkaliber-Vorschriften auf mechanische
10-Meter-Luftgewehranlagen. Insbesondere folgt aus den Bezeichnungen keine
Anforderung an Schussdistanz, Scheibendurchmesser, Anzahl der Bahnen oder
Schießhaltung. Die Stellung einer Klappscheibe und der Anschlag des Sportlers sind
unterschiedliche Informationen. BTV liefert keine Fehlschussbeobachtung.

## Schutz gegen doppelte Übersetzung

Die vier projektspezifischen HTML-Seiten verwenden `translate="no"`, die Klasse
`notranslate` und `<meta name="google" content="notranslate">`. Auf dem Tablet setzt
die bestehende Sprachwahl das HTML-Attribut `lang` auf `en`, `de` oder `cs`.
Monitor, Kameraadministration und Kalibrierung sind derzeit deutsch und behalten
korrekt `lang="de"`; eine neue Übersetzungsbibliothek oder zusätzliche Sprachwahl
wird mit diesem Fehlerfix nicht eingeführt.

Die gemeldeten Ausdrücke „Fahrspuren“, „Strecke 1“, „Errichtet“ und „Bevorzugt“
kommen in den Original-Browserdateien nicht vor. Ohne Browserübersetzung liefert
auch Chromium sie nicht. Damit ist eine zusätzliche Seitenübersetzung eine
plausible Ursache; der Zustand des betroffenen Chrome-Profils wurde nicht
untersucht und die Ursache dort nicht abschließend reproduziert. Der Browsercheck
prüft die ausgelieferten Schutzmerkmale, eigene Sprachwahl, dynamische Kacheln und
Dialoge. Er steuert nicht den externen Übersetzungsdienst und garantiert nicht das
Verhalten beliebiger Erweiterungen, die Seitentext bewusst verändern.
