# Contributing to Biathlon Target Vision

Thank you for your interest in Biathlon Target Vision (BTV)!

BTV is an open-source project for manual and camera-assisted biathlon shooting range monitoring. It is being developed together with feedback from people involved in biathlon competitions, including shooting range officials, timekeepers, and software developers.

The project is under active development and is not yet validated for official competition use.

## Českým přispěvatelům

Vítáme spolupráci českých vývojářů, časoměřičů, rozhodčích a dalších biatlonových nadšenců!

**Issues, návrhy i komentáře můžete psát česky.** Není nutné používat angličtinu ani němčinu.

Pomoci můžete testováním aplikace, kontrolou českých překladů, hlášením chyb, návrhy na vylepšení nebo přímo vývojem.

Projektová dokumentace je převážně v němčině, ale zdrojový kód a komentáře v něm jsou v angličtině.

## How to contribute

You can help by:

- Testing the application under real shooting range conditions.
- Reporting bugs or suggesting improvements.
- Reviewing Czech, German, and English translations.
- Checking biathlon terminology and practical workflows.
- Improving camera-based target recognition.
- Developing integrations with existing timing systems.
- Contributing code and tests.

## Languages

We welcome international collaboration without requiring everyone to write in English.

| Area | Language |
|---|---|
| Issues, pull requests, discussions | Czech, German, or English |
| Project documentation | German |
| Source code and code comments | English |
| Commit messages | English |
| User interface | English, German, Czech |

For discussions involving contributors speaking different languages, a short English summary is helpful when needed.

## Reporting issues

Please check existing issues before opening a new one.

When reporting a bug, include:

- What happened and what you expected.
- Steps to reproduce the problem.
- Application version or Git commit, if known.
- Relevant screenshots or logs, if available.

For problems with camera recognition, information about camera resolution, distance, lighting, and weather conditions is especially useful.

Please remove passwords, credentials, and personal information from logs and screenshots.

## Contributing code

1. Check existing issues or open a new issue to discuss your proposed change.
2. Fork the repository and create a branch.
3. Keep changes small and focused.
4. Follow the existing architecture and coding guidelines in [AGENTS.md](AGENTS.md).
5. Run relevant tests.
6. Submit a pull request describing what changed and what was tested.

Keep solutions simple. Avoid unnecessary dependencies, frameworks, or architectural changes.

Source code, identifiers, comments, and docstrings should be in English.

## Translations

BTV supports three interface languages:

- English (default)
- German
- Czech (Čeština)

Translations are maintained in the existing `biathlon_target_vision/static/translations.js`.

Please use established biathlon terminology rather than literal translations where these differ.

The [terminology documentation](docs/TERMINOLOGIE.md) contains references to official biathlon rules and terminology in all three languages.

Native Czech speakers are especially welcome to review the Czech interface and help improve wording for real competition use.

## Contact and collaboration

Questions, suggestions, and technical discussions are welcome through [GitHub Issues](https://github.com/richtertoralf/biathlon-target-vision/issues).

**You are welcome to participate in Czech, German, or English.**

Thank you for helping make Biathlon Target Vision useful for biathlon communities across borders.
