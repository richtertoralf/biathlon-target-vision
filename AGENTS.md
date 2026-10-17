# AGENTS.md

## Orientierung

Projekt und Funktionsumfang: [README.md](README.md).
Technische Architektur: [ARCHITECTURE.md](docs/ARCHITECTURE.md).
Die [KES-Protokolldokumentation](KES -Protocol description17.10.2001.pdf) im Repository ist die verbindliche Schnittstellenreferenz.

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
- Dokumentation und Benutzeroberfläche auf Deutsch, technische Bezeichner im Code auf Englisch.

## Änderungen und Qualität

- Vor Änderungen den vorhandenen Code verstehen.
- Nur den beauftragten Umfang ändern; keine ungefragten Erweiterungen oder Refactorings.
- Änderungen durch passende, möglichst einfache Tests überprüfen.
- Fehlerfälle berücksichtigen, ohne unnötige Schutz- und Verwaltungsschichten aufzubauen.
- Nach Abschluss kurz mitteilen, was geändert und tatsächlich getestet wurde.
- `CLAUDE.md` verweist ausschließlich auf diese Datei.
