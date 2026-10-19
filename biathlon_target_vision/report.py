"""Markdown test report of a session from journal, configuration, calibrations and diagnostics.

Pure formatting: all values are computed from the passed data. Unmeasured values
are named as such; nothing here judges a test as passed.
"""

from collections import Counter, defaultdict
from datetime import datetime
import math
import statistics

NOT_MEASURED = "nicht gemessen"
STATE_DE = {"standing": "aufgerichtet", "fallen": "gefallen", "unknown": "unbekannt", None: "–"}
CAPTURE_DE = {"active": "Automatik aktiv", "uncertain": "unsicher", "unavailable": "nicht verfügbar"}


def parse(value):
    return datetime.fromisoformat(value) if value else None


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(share * len(ordered)) - 1))]


def summary(values, unit="", digits=1):
    """min / median / p95 / max of measured values, or "nicht gemessen"."""
    values = [value for value in values if value is not None]
    if not values:
        return NOT_MEASURED
    fmt = lambda value: f"{value:.{digits}f}{unit}"
    return (f"min {fmt(min(values))} · Median {fmt(statistics.median(values))} · "
            f"p95 {fmt(percentile(values, .95))} · max {fmt(max(values))} (n = {len(values)})")


def size(value):
    if value is None:
        return NOT_MEASURED
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value} B"
        value /= 1024


def duration(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min {seconds % 60:02d} s"


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", " ") for cell in row) + " |" for row in rows]
    return lines


def calibration_geometry(calibration):
    """Mean target size and spacing in image pixels from the stored polygons."""
    sizes, centers = [], []
    for target in calibration["targets"]:
        xs = [point[0] for point in target["polygon"]]
        ys = [point[1] for point in target["polygon"]]
        sizes.append(((max(xs) - min(xs)) + (max(ys) - min(ys))) / 2)
        centers.append(target["center"])
    spacing = statistics.mean(math.dist(a, b) for a, b in zip(centers, centers[1:]))
    return statistics.mean(sizes), spacing


def journal_summary(events):
    """Counts per lane and kind; automatic changes are separated from baselines."""
    lanes = defaultdict(Counter)
    kinds = Counter()
    first = last = None
    order = Counter()
    reset_since_occupy = {}
    bout_ids = set()
    for event in events:
        command = event["command"]
        lane, kind = command["lane_id"], command["kind"]
        first = first or event["accepted_at"]
        last = event["accepted_at"]
        if kind == "target":
            automatic = command["source"].startswith("camera:")
            key = ("auto" if automatic else "observation") + ("_baseline" if event.get("baseline") else "")
            lanes[lane][key] += 1
            if automatic and command.get("state") == "unknown":
                lanes[lane]["auto_unknown"] += 1
            kinds["Beobachtung (" + ("Kamera" if automatic else command["source"]) + ")"] += 1
        elif kind == "reset":
            lanes[lane]["auto_reset"] += 1
            kinds["Automatisch bestätigte Rückstellung"] += 1
            reset_since_occupy[lane] = True
        elif kind == "manual_target":
            lanes[lane]["manual"] += 1
            if event.get("manual_input", {}).get("automatic_state") not in (None, command["state"]):
                lanes[lane]["manual_against_auto"] += 1
            kinds["Manuelle Scheibenkorrektur"] += 1
        elif kind == "manual_reset":
            lanes[lane]["manual_reset"] += 1
            kinds["Manuell bestätigte Rückstellung"] += 1
            reset_since_occupy[lane] = True
        elif kind == "occupy":
            lanes[lane]["occupy"] += 1
            kinds["Bahn belegt"] += 1
            reset_since_occupy[lane] = False
        elif kind == "release":
            lanes[lane]["release"] += 1
            kinds["Bahn verlassen"] += 1
            order["Rückstellung vor Verlassen" if reset_since_occupy.get(lane) else "Verlassen vor Rückstellung"] += 1
            bout_ids.add(command["bout_id"])
        elif kind == "assign":
            lanes[lane]["assign"] += 1
            kinds["Startnummer zugeordnet/korrigiert"] += 1
            if command.get("bout_id"):
                bout_ids.add(command["bout_id"])
        elif kind == "mode":
            lanes[lane]["mode"] += 1
            kinds["Quellensperre geändert"] += 1
        else:
            kinds[kind] += 1
    return lanes, kinds, first, last, order, bout_ids


def sample_summary(samples):
    """Aggregate stored diagnostics samples without keeping the raw lines."""
    result = {"count": 0, "first": None, "last": None, "process_cpu": [], "system_cpu": [], "rss": [], "available": [],
              "disk_free": [], "health": Counter(), "capture_down": 0, "classify": defaultdict(list), "step": [],
              "period": [], "cameras": {}, "lanes": defaultdict(Counter), "lane_drops": Counter()}
    previous_lanes = {}
    for sample in samples:
        result["count"] += 1
        result["first"] = result["first"] or sample["t"]
        result["last"] = sample["t"]
        result["process_cpu"].append(sample["process"].get("cpu_percent"))
        result["system_cpu"].append(sample["system"].get("cpu_percent"))
        result["rss"].append(sample["process"].get("rss_bytes"))
        result["available"].append(sample["system"].get("memory_available_bytes"))
        result["disk_free"].append(sample["system"].get("disk_free_bytes"))
        result["health"][sample.get("health")] += 1
        result["capture_down"] += not sample.get("capture_running", True)
        for lane, values in sample.get("timings", {}).get("classify", {}).items():
            result["classify"][lane].extend(values)
        result["step"].extend(sample.get("timings", {}).get("step", []))
        result["period"].extend(sample.get("timings", {}).get("period", []))
        for camera_id, camera in sample.get("cameras", {}).items():
            entry = result["cameras"].setdefault(camera_id, {"samples": 0, "connected": 0, "drops": 0, "epochs": set(),
                                                             "resolutions": Counter(), "frames": [], "last_frame": None,
                                                             "was_connected": None})
            entry["samples"] += 1
            entry["connected"] += bool(camera["connected"])
            if entry["was_connected"] and not camera["connected"]:
                entry["drops"] += 1
            entry["was_connected"] = camera["connected"]
            entry["epochs"].add(camera.get("stream_epoch"))
            if camera.get("resolution"):
                entry["resolutions"]["×".join(map(str, camera["resolution"]))] += 1
            entry["frames"].append(camera.get("frame_number"))
            entry["last_frame"] = camera.get("captured_at") or entry["last_frame"]
        for lane, status in sample.get("lanes", {}).items():
            result["lanes"][lane][status] += 1
            if previous_lanes.get(lane) == "active" and status != "active":
                result["lane_drops"][lane] += 1
            previous_lanes[lane] = status
    return result


def build_report(context):
    session = context["session"]
    runs = context["runs"]
    samples = sample_summary(context["samples"])
    lanes, kinds, first_event, last_event, order, bout_ids = journal_summary(context["events"])
    cameras, calibrations, notes = context["cameras"], context["calibrations"], context["notes"]
    lines = [f"# Testprotokoll – {session['name']}", "",
             f"Automatisch erstellt am {context['generated_at']} (UTC) von BTV. Die Daten stammen aus dem Ereignisjournal,",
             "der Konfiguration, den Kalibrierungen und der optionalen Testdiagnose dieser Sitzung. Der Bericht bewertet",
             "keine Tests als bestanden; die tatsächliche Scheibenstellung ist unabhängig zu belegen (Feldprotokoll, Video).", ""]

    lines += ["## 1. Sitzung", ""] + table(["Angabe", "Wert"], [
        ["Name", session["name"]], ["Sitzungs-ID", session["session_id"]], ["Beginn", session["started_at"]],
        ["Ende", session.get("ended_at") or "Sitzung aktiv"], ["Schießbahnen", context["lane_count"] or NOT_MEASURED]]) + [""]

    system = runs[-1]["system"] if runs else None
    lines += ["## 2. BTV-Version", ""] + table(["Angabe", "Wert"], [
        ["Version bei Diagnosebeginn", system["btv_version"] if system else NOT_MEASURED],
        ["Commit bei Diagnosebeginn", (system or {}).get("commit") or NOT_MEASURED],
        ["Version bei Berichtserstellung", f"{context['version']} · {context['commit'] or 'Commit unbekannt'}"]]) + [""]

    lines += ["## 3. Server und Betriebssystem", ""]
    if system:
        lines += table(["Angabe", "Wert"], [
            ["Betriebssystem", system["os"]], ["Kernel", system["kernel"]], ["Python", system["python"]],
            ["CPU", f"{system['cpu_model'] or 'unbekannt'} · {system['cpu_count']} logische Kerne"],
            ["Arbeitsspeicher", size(system["memory_total_bytes"])], ["Datenträger", size(system["disk_total_bytes"])],
            ["Netzwerkadressen", ", ".join(system["addresses"]) or "keine ermittelt"],
            ["Serverzeit / Zeitzone", f"{system['server_time']} · {system['timezone']}"]]) + [""]
    else:
        lines += ["Keine Testdiagnose aufgezeichnet; Systemangaben " + NOT_MEASURED + ".", ""]

    lines += ["## 4. Kameraübersicht", "", "Stand der Konfiguration bei Berichtserstellung; Adressen ohne Zugangsdaten.", ""]
    rows = []
    for camera in cameras:
        live = samples["cameras"].get(camera["id"])
        resolution = ", ".join(live["resolutions"]) if live and live["resolutions"] else NOT_MEASURED
        rows.append([camera["id"], camera["name"], camera["address"], resolution])
    lines += (table(["Kamera", "Name", "Adresse", "Bildauflösung (gemessen)"], rows) if rows else ["Keine Kamera konfiguriert."]) + [""]

    lines += ["## 5. Kamera-/Bahnzuordnung", ""]
    rows = [[camera["id"], ", ".join(map(str, camera["lane_ids"])) or "keine"] for camera in cameras]
    lines += (table(["Kamera", "Bahnen"], rows) if rows else ["Keine Zuordnung (nur manuelle Erfassung)."]) + [
        "", "Die Zuordnung wird nicht historisiert (Issue #15); maßgeblich ist der Stand bei Berichtserstellung.", ""]

    lines += ["## 6. Kalibrierungen und Bildgeometrie", "",
              "Aktueller Stand der gespeicherten Kalibrierungen (gemeinsam für alle Sitzungen).", ""]
    rows = []
    for lane, item in calibrations.items():
        calibration = item["calibration"]
        if not calibration:
            rows.append([lane, item["camera"] or "–", "nicht kalibriert", "–", "–", "–"])
            continue
        diameter, spacing = calibration_geometry(calibration)
        rows.append([lane, item["camera"] or "–", "gültig" if item["valid"] else "ungültig (Kamera/Adresse geändert)",
                     "×".join(map(str, calibration["image_size"])), f"{diameter:.0f} px", f"{spacing:.0f} px · {calibration['created_at']}"])
    lines += (table(["Bahn", "Kamera", "Status", "Bildgröße", "Scheibe ⌀", "Scheibenabstand · erstellt"], rows)
              if rows else ["Keine Bahn mit Kamera oder Kalibrierung."]) + [""]

    lines += ["## 7. Zeitraum der Diagnoseaufzeichnung", ""]
    if runs:
        rows = [[run["started_at"], run.get("stopped_at") or "läuft / nicht sauber beendet", run.get("stop_reason") or "–",
                 ", ".join(run.get("resumed") or []) or "–"] for run in runs]
        lines += table(["Beginn", "Ende", "Grund", "Fortgesetzt nach Neustart"], rows)
        lines += ["", f"Messungen: {samples['count']} (Abtastintervall etwa 5 s)"
                  + (f", erste {samples['first']}, letzte {samples['last']}" if samples["count"] else "") + "."]
    else:
        lines += ["Für diese Sitzung wurde keine Testdiagnose gestartet."]
    lines += [""]

    gib = lambda values: [value / 1024 ** 3 if value is not None else None for value in values]
    lines += ["## 8. Systemleistung", ""] + table(["Messgröße", "Zusammenfassung"], [
        ["CPU BTV-Prozess (% eines Kerns, inkl. RTSP-Dekodierung)", summary(samples["process_cpu"], " %")],
        ["CPU gesamtes System (% aller Kerne)", summary(samples["system_cpu"], " %")],
        ["RAM BTV-Prozess (GiB)", summary(gib(samples["rss"]), " GiB", 2)],
        ["Verfügbarer System-RAM (GiB)", summary(gib(samples["available"]), " GiB", 2)],
        ["Freier Speicher im Datenordner (GiB)", summary(gib(samples["disk_free"]), " GiB", 1)],
        ["Gesundheitsstatus", ", ".join(f"{key}: {value}" for key, value in samples["health"].items()) or NOT_MEASURED],
        ["Messungen mit gestoppter Erkennungsaufgabe", samples["capture_down"] if samples["count"] else NOT_MEASURED]]) + [""]

    lines += ["## 9. Kameraverfügbarkeit und Ausfälle", ""]
    rows = []
    for camera in cameras:
        live = samples["cameras"].get(camera["id"])
        if not live:
            rows.append([camera["id"], NOT_MEASURED, NOT_MEASURED, NOT_MEASURED, NOT_MEASURED])
            continue
        frames = [value for value in live["frames"] if value is not None]
        epochs = {epoch for epoch in live["epochs"] if epoch}
        rows.append([camera["id"], f"{live['connected'] / live['samples'] * 100:.0f} % der Messungen", live["drops"],
                     max(0, len(epochs) - 1), f"{max(frames) - min(frames)} Bilder dekodiert" if len(frames) > 1 else NOT_MEASURED])
    lines += (table(["Kamera", "Verbunden", "Abbrüche (zwischen Messungen)", "Neue Verbindungen", "Dekodierte Bilder"], rows)
              if rows else ["Keine Kamera konfiguriert."])
    lines += ["", "Abbrüche kürzer als das Abtastintervall erscheinen nur über „Neue Verbindungen“ (Verbindungszähler des Decoders).", ""]

    lines += ["## 10. Erkennungsleistung und Verarbeitungszeiten", "",
              "Gemessen wird die Verarbeitungsdauer in BTV, **keine physische Ende-zu-Ende-Latenz** "
              "(Kamera, Netzwerk und Anzeige sind nicht enthalten).", ""]
    rows = [["Erkennungsdurchlauf aller Bahnen (ohne Pause)", summary(samples["step"], " ms")],
            ["Abstand zwischen Durchläufen (inkl. 100 ms Pause)", summary(samples["period"], " ms")],
            ["Durchläufe mit Abstand > 2 s (Verarbeitungsaussetzer)", sum(1 for value in samples["period"] if value > 2000) if samples["period"] else NOT_MEASURED]]
    for lane in sorted(samples["classify"], key=int):
        rows.append([f"Bildauswertung Bahn {lane} (ausgewertete Bilder: {len(samples['classify'][lane])})", summary(samples["classify"][lane], " ms")])
    lines += table(["Messgröße", "Zusammenfassung"], rows) + [""]
    rows = [[lane, *(counts.get(key, 0) for key in ("active", "uncertain", "unavailable")), samples["lane_drops"][lane]]
            for lane, counts in sorted(samples["lanes"].items(), key=lambda item: int(item[0]))]
    if rows:
        lines += ["Erfassungsstatus je Bahn (Anzahl Messungen):", ""] + table(
            ["Bahn", "Automatik aktiv", "unsicher", "nicht verfügbar", "Wechsel aus „aktiv“"], rows) + [""]

    lines += ["## 11. Zusammenfassung des Ereignisjournals", "",
              f"Ereignisse: {sum(kinds.values())}" + (f", erstes {first_event}, letztes {last_event}" if first_event else "")
              + f". Referenzierte Schießeinlagen (BIB/Verlassen): {len(bout_ids)}.", ""]
    lines += (table(["Ereignisart", "Anzahl"], sorted(kinds.items())) if kinds else ["Keine Ereignisse."]) + [""]
    rows = [[lane, counts["occupy"], counts["release"], counts["assign"], counts["auto"], counts["auto_baseline"],
             counts["auto_unknown"], counts["auto_reset"], counts["manual_reset"], counts["manual"]]
            for lane, counts in sorted(lanes.items())]
    if rows:
        lines += table(["Bahn", "Belegt", "Verlassen", "BIB", "Kamera-Zustandswechsel", "Kamera-Grundbeob.", "Kamera „unbekannt“",
                        "Auto-Rückst.", "Manuelle Rückst.", "Manuelle Korr."], rows) + [""]

    lines += ["## 12. Manuelle Korrekturen und Auffälligkeiten", ""]
    corrected = {lane: counts for lane, counts in lanes.items() if counts["manual"]}
    if corrected:
        lines += table(["Bahn", "Manuelle Korrekturen", "davon abweichend vom Kamerawert"],
                       [[lane, counts["manual"], counts["manual_against_auto"]] for lane, counts in sorted(corrected.items())])
    else:
        lines += ["Keine manuellen Scheibenkorrekturen."]
    lines += ["", f"Korrekturbelege (Kameraausschnitte): {context['correction_images']} Dateien in "
              f"`sessions/{session['session_id']}/corrections/`.", ""]

    lines += ["## 13. Aufzeichnungsdateien und Videobelege", ""]
    recordings, problems, hints = context["recordings"]
    rows = []
    for camera_id, entry in recordings.items():
        files = entry["files"]
        if files:
            rows.append([camera_id, entry["mediamtx_path"], len(files), size(sum(file["bytes"] for file in files)),
                         f"{min(file['modified'] for file in files)} – {max(file['modified'] for file in files)}"])
        else:
            rows.append([camera_id, entry["mediamtx_path"] or "–", 0, "–", "keine Dateien gefunden"])
    lines += (table(["Kamera", "MediaMTX-Pfad", "Dateien", "Größe", "Letzte Änderung (UTC, erste – letzte)"], rows)
              if rows else ["Keine Kamera konfiguriert."])
    lines += [""]
    for camera_id, entry in recordings.items():
        for file in entry["files"][:50]:
            lines.append(f"- `{file['file']}` ({size(file['bytes'])}, geändert {file['modified']})")
    lines += [f"- {text}" for text in problems + hints]
    lines += ["", "Die Videodateien werden nur aufgelistet, nicht geöffnet oder verändert. Unterbrechungen der Aufzeichnung "
              "sind daraus nicht zuverlässig ableitbar.", ""]

    lines += ["## 14. Nicht verfügbare Messwerte", "",
              "- Physische Ende-zu-Ende-Latenz (Scheibenfall bis Tablet-Anzeige): nicht gemessen; Auswertung über Kamera-Zeiteinblendung und `accepted_at`.",
              "- Tatsächliche Scheibenstellungen: nur unabhängig belegbar (Feldprotokoll, Videoaufzeichnung).",
              "- CPU/RAM von MediaMTX und Netzwerklast: nicht gemessen.",
              "- Tablet-WLAN, Ablesbarkeit und Bedienung: nur manuell (Feldprotokoll).",
              "- Historische Kamera-/Bahnzuordnung: nicht gespeichert (Issue #15)."]
    if not runs:
        lines.append("- Systemleistung, Kameraverfügbarkeit und Verarbeitungszeiten: keine Testdiagnose aufgezeichnet.")
    lines += [""]

    camera_drops = sum(entry["drops"] for entry in samples["cameras"].values())
    reconnects = sum(max(0, len({e for e in entry["epochs"] if e}) - 1) for entry in samples["cameras"].values())
    resumed = sum(len(run.get("resumed") or []) for run in runs)
    manual_total = sum(counts["manual"] for counts in lanes.values())
    lines += ["## 15. Testfälle aus Issue #13 und belegbare Daten", "",
              "„Beleg“ nennt nur, was die Daten zeigen. Die Bewertung erfolgt manuell.", ""] + table(
        ["Testfall", "Beleg in den Daten", "Bewertung"], [
            ["Belegung, verspätete BIB und Korrektur", f"{kinds['Bahn belegt']} Belegungen, {kinds['Startnummer zugeordnet/korrigiert']} BIB-Zuordnungen", "manuell"],
            ["Verlassen und Rückstellung in beiden Reihenfolgen", ", ".join(f"{key}: {value}" for key, value in order.items()) or "nicht beobachtet", "manuell"],
            ["Null bis fünf gefallene Scheiben", "aus dem Journal nicht eindeutig ableitbar", "Feldprotokoll/Video"],
            ["Manuelle Priorität", f"{manual_total} Korrekturen, davon {sum(c['manual_against_auto'] for c in lanes.values())} gegen den Kamerawert", "manuell"],
            ["Kameraausfall und Wiederverbindung", f"{camera_drops} Abbrüche, {reconnects} neue Verbindungen" if runs else NOT_MEASURED, "manuell"],
            ["Grundbeobachtungen ohne nachträgliche Fälle", f"{sum(c['auto_baseline'] for c in lanes.values())} Grundbeobachtungen", "Video"],
            ["BTV-Neustart und Replay", f"{resumed} Neustarts während der Diagnose" if runs else NOT_MEASURED, "manuell"],
            ["Zwei Tablets, Serververbindungsverlust", "nicht im Journal erfasst", "Feldprotokoll"],
            ["Licht, Wetter, Kameraabstände", "siehe Abschnitt 16" if any(notes.get(k) for k in ("weather", "light", "camera_distances")) else "keine Angaben", "manuell"],
            ["Reale Bild-/Videobelege", f"{sum(len(e['files']) for e in recordings.values())} Aufzeichnungsdateien", "Video"]]) + [""]

    lines += ["## 16. Offene Fragen, Beobachtungen und erkannte Probleme", ""]
    labels = {"camera_distances": "Kameraabstände", "weather": "Wetter", "light": "Licht", "observations": "Besondere Beobachtungen"}
    for key, label in labels.items():
        lines += [f"**{label}:** {notes.get(key) or 'keine Angabe'}", ""]
    findings = []
    if samples["capture_down"]:
        findings.append(f"Erkennungsaufgabe in {samples['capture_down']} Messungen gestoppt.")
    if camera_drops or reconnects:
        findings.append(f"Kameraverbindungen: {camera_drops} Abbrüche, {reconnects} neue Verbindungen.")
    long_cycles = sum(1 for value in samples["period"] if value > 2000)
    if long_cycles:
        findings.append(f"{long_cycles} Erkennungsdurchläufe mit mehr als 2 s Abstand.")
    invalid = [lane for lane, item in calibrations.items() if item["calibration"] and not item["valid"]]
    missing = [lane for lane, item in calibrations.items() if item["camera"] and not item["calibration"]]
    if invalid:
        findings.append("Ungültige Kalibrierung: Bahn " + ", ".join(map(str, invalid)) + ".")
    if missing:
        findings.append("Kamerabahn ohne Kalibrierung: Bahn " + ", ".join(map(str, missing)) + ".")
    lines += [f"- {text}" for text in findings] or ["- Aus den Daten keine technischen Auffälligkeiten ableitbar."]
    lines += [""]

    lines += ["## 17. Zusammenfassung und nächste Schritte", "",
              f"- Ereignisse: {sum(kinds.values())}; Diagnosemessungen: {samples['count']}; Kameras: {len(cameras)}; "
              f"kalibrierte Bahnen: {sum(1 for item in calibrations.values() if item['calibration'] and item['valid'])}.",
              "- Journal (`/api/events?session_id=…`) und Videoaufzeichnungen gegen das Feldprotokoll abgleichen.",
              "- Abweichungen nach Schwere priorisieren und im Entwicklungsbericht dokumentieren (Issue #13).", ""]
    return "\n".join(lines)
