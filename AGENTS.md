# AGENTS.md

## Orientierung

Projekt und Funktionsumfang: [README.md](README.md).  
Internationale Mitarbeit: [CONTRIBUTING.md](CONTRIBUTING.md).  
Technische Architektur: [ARCHITECTURE.md](docs/ARCHITECTURE.md).  
Die [KES-Protokolldokumentation vom 17.10.2001](KES%20-Protocol%20description17.10.2001.pdf) im Repository ist die Orientierung für eine Schnittstellenreferenz.

## Programmierung

- **KISS:** Immer die einfachste funktionierende und wartbare Lösung wählen.
- Vorhandene Funktionen, Bibliotheken und Betriebssystemmittel nutzen, statt eigene Lösungen zu erfinden.
- Keine vorsorglichen Abstraktionen, Frameworks, Dienste oder Konfigurationsmöglichkeiten.
- Kleine, verständliche Funktionen mit eindeutigen Namen und klaren Zuständigkeiten.
- Wiederholungen vermeiden, aber keine Abstraktion für einmalig verwendeten Code.
- Fehler nachvollziehbar behandeln, nicht stillschweigend unterdrücken.
- Bestehenden funktionierenden Code nicht ohne konkreten Anlass umbauen.

## Lesbarkeit und Dokumentation

- Code muss auch für menschliche Entwickler ohne KI-Unterstützung verständlich sein.
- Jede Quelldatei erhält einen kurzen Kommentar zu Zweck und Aufgabe, sofern dies nicht bereits offensichtlich ist.
- Nicht offensichtliche Abläufe, Entscheidungen und technische Besonderheiten direkt im Code kommentieren.
- Kommentare erklären vor allem **warum**, nicht bloß, was der Code ohnehin zeigt.
- Keine überflüssigen Kommentare, generierten Dokumentationsmengen oder doppelten Erklärungen.

## Sprache und internationale Zusammenarbeit

- Projektdokumentation (`README.md`, `docs/`, `AGENTS.md`) grundsätzlich auf Deutsch.
- Programmcode einschließlich Bezeichnern, Kommentaren und Docstrings auf Englisch.
- GitHub-Issues, Pull Requests und Diskussionen dürfen auf Deutsch, Tschechisch oder Englisch verfasst werden.
- Bei sprachübergreifender Zusammenarbeit bei Bedarf eine kurze englische Zusammenfassung ergänzen.
- Commit-Messages auf Englisch.
- Die Benutzeroberflächen unterstützen Englisch (Standard), Deutsch und Tschechisch.
- Alle drei Sprachversionen vollständig und konsistent pflegen.
- Fachbegriffe anhand der IBU-Regeln.
- Keine zusätzlichen Übersetzungsframeworks oder parallelen Dokumentationsstrukturen einführen.
- Bestehende Dokumentation nicht allein wegen der Sprache umstrukturieren.

## Zuständigkeiten der Dokumentation

- `README.md`: kurze öffentliche Produktbeschreibung, Installation, grundlegende Bedienung und Deinstallation. Nicht mit jedem Entwicklungsschritt erweitern; Details in `docs/` verlinken.
- `docs/`: technische Dokumentation, Schnittstellen, Architektur, Entwicklung, Tests und ausführliche Anleitungen (`docs/BEDIENUNG.md`).
- `docs/praxistests/`: Ergebnisse und Berichte realer Tests, je Test ein Ordner; keine Videos, Zugangsdaten oder `config.json`.
- `docs/ARCHITECTURE.md`: aktuelle Architektur und grundlegende technische Entscheidungen.
- `docs/API.md`: Schnittstellen und Integrationshinweise.
- `docs/ENTWICKLUNGSBERICHT.md`: Entwicklungsverlauf, Entscheidungen, Tests und Einschränkungen; überholte Entscheidungen kennzeichnen.
- Informationen nicht unnötig mehrfach dokumentieren. Bei Änderungen gezielt aktualisieren, statt pauschal Abschnitte anzuhängen.
- Zusätzliche Dokumentationsdateien nur bei konkretem Bedarf anlegen.

## README

Die README ist die öffentliche Einstiegsseite für Anwender, Interessenten und
Mitwirkende; Vertiefendes steht in `docs/`.

- Nutzen vor technischen Details. Gliederung und Überschriften passend zum
  Produkt wählen.
- Nur tatsächlich vorhandene Funktionen und Befehle als verfügbar
  beschreiben; Erprobtes und Geplantes getrennt kennzeichnen.
- Einen Entwicklungsstatus nur nennen, wenn er nachvollziehbar belegt ist:
  **Konzept** (keine nutzbare Implementierung), **In Entwicklung**
  (begonnen, eventuell noch nicht installierbar; nennen, was funktioniert und
  wie man es ausprobiert), **Im Praxistest** (bei mindestens einem realen
  Einsatz betreut erprobt, datierter Beleg in `docs/`), **Im Einsatz**
  (wiederholt produktiv genutzt, Beleg in `docs/`), **Archiviert**. Fehlen
  Belege, die Aussage weglassen; Installations- und Upgradeprüfungen belegen
  keinen Praxiseinsatz.
- Nur verifizierte Informationen aufnehmen: Aussagen zuerst an Code und
  Dokumentation prüfen; was sich nicht bestätigen lässt, weglassen. Fehlende
  Dokumentation ist kein Beleg für eine fehlende Funktion.
- Einschränkungen nur nennen, wenn sie nachgewiesen und für Anwender relevant
  sind; keine vermuteten Risiken, vorsorglichen Warnhinweise oder künstlich
  offenen Fragen. Lieber kürzer und sachlich richtig als ausführlich mit
  Annahmen.
- Bei Änderungen an Funktionen, Installation, Bedienung, Verwaltungsbefehlen
  oder Entwicklungsstand auch die README auf nötige Anpassungen prüfen.
- Alles Notwendige steht in diesem Repository. Nicht auf nicht öffentliche
  Repositories als notwendige Quelle verweisen.
- Bestehende Informationen nicht ohne fachlichen Grund entfernen, sondern bei
  Bedarf nach `docs/` verschieben.
- Der Leitgedanke von RICHTER.PROJECTS, „Möglichkeiten schaffen.“, ist
  erkennbar, in eigenen Worten passend zum Produkt.
- Natürliches, sachliches Deutsch ohne Werbe- und Füllformeln; vorhandene
  Bilder und Beispiele erhalten.

## Änderungen und Qualität

- Vor Änderungen den vorhandenen Code verstehen.
- Nur den beauftragten Umfang ändern; keine ungefragten Erweiterungen oder Refactorings.
- Änderungen durch passende, möglichst einfache Tests überprüfen.
- Fehlerfälle berücksichtigen, ohne unnötige Schutz- und Verwaltungsschichten aufzubauen.
- Nach Abschluss kurz mitteilen, was geändert und tatsächlich getestet wurde.
- `CLAUDE.md` verweist ausschließlich auf diese Datei.
