"""Printable field protocol (PDF, DIN A4) for everything BTV cannot record itself.

A minimal PDF writer without extra dependency: standard fonts Helvetica and
Helvetica-Bold (WinAnsi, covers German umlauts), lines, rectangles and text.
Known values are pre-filled; never credentials or full RTSP addresses.
"""

PORTRAIT, LANDSCAPE = (595.28, 841.89), (841.89, 595.28)
MARGIN = 36


def pdf_text(value):
    """WinAnsi bytes with PDF string escaping; unsupported characters become '?'."""
    data = str(value).encode("cp1252", "replace")
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def fit(value, width, size):
    """Shorten text to an estimated Helvetica width (about 0.52 em per character)."""
    value = str(value)
    limit = max(1, int(width / (size * .52)))
    return value if len(value) <= limit else value[:limit - 1] + "…"


class Page:
    def __init__(self, size):
        self.width, self.height = size
        self.parts = []

    def text(self, x, y, value, size=10, bold=False):
        # y is measured from the top edge, as for a printed form.
        self.parts.append(b"BT /%s %g Tf %.2f %.2f Td (" % (b"F2" if bold else b"F1", size, x, self.height - y)
                          + pdf_text(value) + b") Tj ET")

    def line(self, x1, y1, x2, y2, width=.6):
        self.parts.append(b"%.2f w %.2f %.2f m %.2f %.2f l S" % (width, x1, self.height - y1, x2, self.height - y2))

    def rect(self, x, y, w, h, width=.6):
        self.parts.append(b"%.2f w %.2f %.2f %.2f %.2f re S" % (width, x, self.height - y - h, w, h))

    def table(self, x, y, widths, headers, rows, row_height, header_height=26, size=9):
        """Grid with bold headers (one or two lines) and pre-filled or empty cells; returns the bottom y."""
        total = sum(widths)
        self.rect(x, y, total, header_height + row_height * len(rows), .8)
        left = x
        for width, header in zip(widths, headers):
            for index, part in enumerate(header.split("\n")):
                self.text(left + 3, y + 11 + index * 10, fit(part, width - 6, size - 1), size - 1, bold=True)
            left += width
            if left < x + total:
                self.line(left, y, left, y + header_height + row_height * len(rows))
        self.line(x, y + header_height, x + total, y + header_height, .8)
        for row_index, row in enumerate(rows):
            top = y + header_height + row_index * row_height
            if row_index:
                self.line(x, top, x + total, top, .4)
            left = x
            for width, cell in zip(widths, row):
                if cell not in (None, ""):
                    self.text(left + 3, top + 13, fit(cell, width - 6, size), size)
                left += width
        return y + header_height + row_height * len(rows)

    def field(self, x, y, label, width, value=""):
        """Label with a writing line; an optional pre-filled value."""
        self.text(x, y, label, 9, bold=True)
        self.line(x, y + 16, x + width, y + 16, .5)
        if value:
            self.text(x + 2, y + 13, fit(value, width - 4, 10), 10)

    def lines(self, x, y, width, count, gap=22):
        for index in range(count):
            self.line(x, y + gap * (index + 1), x + width, y + gap * (index + 1), .4)
        return y + gap * count


def document(pages):
    """Serialise pages into a PDF file (one content stream per page)."""
    objects = [None, None,
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for page in pages:
        stream = b"\n".join(page.parts)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                       b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>" % (page.width, page.height, len(objects)))
        kids.append(b"%d 0 R" % len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % len(pages)
    output, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(output)


def field_protocol(context):
    session, cameras, calibrations = context["session"], context["cameras"], context["calibrations"]
    pages = []

    def new_page(title, size=PORTRAIT):
        page = Page(size)
        page.text(MARGIN, MARGIN + 4, "BTV Feldprotokoll – Praxistest", 9, bold=True)
        page.text(MARGIN + 190, MARGIN + 4, fit(f"Sitzung: {session['name']}", page.width - 2 * MARGIN - 190, 9), 9)
        page.line(MARGIN, MARGIN + 10, page.width - MARGIN, MARGIN + 10, .8)
        page.text(MARGIN, MARGIN + 36, title, 15, bold=True)
        pages.append(page)
        return page

    # Overview with the pre-filled values.
    page = new_page("Feldprotokoll Praxistest")
    width = page.width - 2 * MARGIN
    y = page.table(MARGIN, MARGIN + 52, [150, width - 150], ["Angabe", "Wert (von BTV vorausgefüllt)"], [
        ["Sitzung", session["name"]], ["Sitzungs-ID", session["session_id"]], ["Datum (Sitzungsbeginn)", context["date"]],
        ["BTV-Version / Commit", f"{context['version']} · {context['commit'] or 'unbekannt'}"],
        ["Formular erstellt", context["generated_at"]]], 20)
    y += 22
    for label in ("Ort / Anlage", "Protokollführung", "Kampfrichter / Beteiligte", "Testbeginn – Testende (Uhrzeit)",
                  "Tablets / Browser", "Netzwerk / WLAN", "BTV-Server / Stromversorgung"):
        page.field(MARGIN, y, label, width)
        y += 30
    y += 6
    page.text(MARGIN, y, "Kameras laut BTV-Konfiguration", 11, bold=True)
    rows = [[camera["id"], camera["name"], ", ".join(map(str, camera["lane_ids"])) or "–", camera["resolution"] or "unbekannt",
             ", ".join(str(lane) for lane in camera["lane_ids"] if calibrations.get(lane, {}).get("valid")) or "keine"]
            for camera in cameras] or [["", "Keine Kamera konfiguriert", "", "", ""]]
    page.table(MARGIN, y + 8, [80, 150, 80, 90, width - 400], ["Kamera-ID", "Name", "Bahnen", "Auflösung", "Kalibrierte\nBahnen"], rows, 20)

    # One sheet per camera (an empty sheet if none is configured yet).
    for camera in cameras or [{"id": "", "name": "", "lane_ids": [], "resolution": None}]:
        page = new_page(f"Kamera {camera['id']}".strip() + (f" – {camera['name']}" if camera["name"] else ""))
        y = MARGIN + 60
        page.field(MARGIN, y, "Kamera-ID", 160, camera["id"])
        page.field(MARGIN + 180, y, "Bildauflösung laut BTV", width - 180, camera["resolution"] or "")
        y += 34
        for left, right in (("Hersteller und Modell", "Objektiv / Brennweite (mm)"), ("Zoomstellung", "Montagehöhe (m)"),
                            ("Aufstellungsposition", "Betrachtungswinkel zu den Scheiben (°)")):
            page.field(MARGIN, y, left, width / 2 - 10)
            page.field(MARGIN + width / 2 + 10, y, right, width / 2 - 10)
            y += 34
        page.text(MARGIN, y + 4, "Erfasste Schießbahnen (Abstand je Bahn bzw. Scheibengruppe)", 11, bold=True)
        lanes = camera["lane_ids"]  # test case: up to five lanes; more still get their own row
        rows = []
        for index in range(max(5, len(lanes))):
            lane = lanes[index] if index < len(lanes) else None
            calibration = calibrations.get(lane, {}) if lane else {}
            rows.append([lane or "", "", "", f"{calibration['diameter_px']:.0f} px" if calibration.get("diameter_px") else "",
                         ("gültig" if calibration.get("valid") else "ungültig") if calibration.get("image_size") else ("nein" if lane else ""), ""])
        y = page.table(MARGIN, y + 12, [44, 86, 86, 76, 66, width - 358],
                       ["Bahn", "Abstand Kamera–\nScheiben (m)", "Scheiben-\ngröße (mm)", "Scheibe im\nBild (BTV)", "Kalibriert", "Bemerkung"], rows, 26)
        page.text(MARGIN, y + 24, "Besonderheiten des Kamerabildes (Spiegelung, Verdeckung, Vibration, Schärfe)", 10, bold=True)
        page.lines(MARGIN, y + 28, width, 6)

    # Weather and light: several observations over the test period.
    page = new_page("Wetter und Licht", LANDSCAPE)
    width = page.width - 2 * MARGIN
    page.text(MARGIN, MARGIN + 54, "Himmel: S = sonnig, W = wolkig, B = bedeckt. Mehrere Beobachtungen über den Testzeitraum eintragen.", 9)
    page.table(MARGIN, MARGIN + 64, [52, 50, 52, 76, 64, 64, 66, 76, 76, width - 576],
               ["Uhrzeit", "Temp.\n°C", "Himmel\nS / W / B", "Niederschlag", "Wind", "Sicht", "Gegenlicht", "Schatten auf\nScheiben", "Licht-\nwechsel", "Sonstige Besonderheiten"],
               [[""] * 10 for _ in range(13)], 31)

    # Independent reference of the actual target positions.
    for part in (1, 2):
        page = new_page(f"Referenzbeobachtungen Scheibenzustände ({part}/2)", LANDSCAPE)
        page.text(MARGIN, MARGIN + 54, "Je Scheibe: A = aufgerichtet, G = gefallen, ? = unbekannt / nicht erkennbar. "
                  "Tatsächliche Stellung unabhängig von BTV notieren; keine Treffer oder Schüsse ableiten.", 9)
        page.table(MARGIN, MARGIN + 64, [70, 52, 36] + [26] * 5 + [26] * 5 + [70, width - 488],
                   ["Uhrzeit /\nVideozeit", "Kamera", "Bahn", "Ist\n1", "Ist\n2", "Ist\n3", "Ist\n4", "Ist\n5",
                    "BTV\n1", "BTV\n2", "BTV\n3", "BTV\n4", "BTV\n5", "Abweichung", "Bemerkung"],
                   [[""] * 15 for _ in range(14)], 29)

    # Operation and technical observations.
    page = new_page("Bedienbarkeit und technische Auffälligkeiten")
    width = page.width - 2 * MARGIN
    y = MARGIN + 56
    for label in ("Tablet-Helligkeit und Ablesbarkeit", "Bedienung mit Handschuhen", "Touch-Bedienung",
                  "WLAN-Unterbrechungen (Uhrzeit, Dauer, Tablet)", "Verzögerungen (Uhrzeit, Bahn)", "Fehleingaben",
                  "Kameraausfälle (Uhrzeit, Kamera)", "Verbesserungsvorschläge der Kampfrichter"):
        page.text(MARGIN, y, label, 10, bold=True)
        y = page.lines(MARGIN, y + 2, width, 3, 20) + 18

    for number, page in enumerate(pages, start=1):
        page.line(MARGIN, page.height - MARGIN + 4, page.width - MARGIN, page.height - MARGIN + 4, .5)
        page.text(MARGIN, page.height - MARGIN + 16,
                  fit(f"Sitzung {session['name']} · ID {session['session_id']} · BTV {context['version']}", page.width - 2 * MARGIN - 80, 8), 8)
        page.text(page.width - MARGIN - 70, page.height - MARGIN + 16, f"Seite {number} von {len(pages)}", 8)
    return document(pages)
