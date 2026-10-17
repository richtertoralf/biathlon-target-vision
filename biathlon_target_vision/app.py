"""FastAPI-Zugang für Tablet-Bedienplätze, Ereignisquellen und Kalibrierung."""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
from itertools import count
from pathlib import Path
from time import monotonic
from uuid import uuid4

import anyio
import cv2
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import numpy as np
from starlette.concurrency import run_in_threadpool

from . import API_VERSION, __version__
from .calibration import CalibrationError, CalibrationStore, align, calibrate
from .config import CameraSettings, Settings, load_settings, save_settings
from .cameras import CameraManager, camera_binding
from .core import Conflict, EventStore
from .models import (Assignment, Observation, Release, ModeChange, ManualTarget,
                     OverrideRelease, ManualReset)
from .vision import VisionService


def create_app(data_dir: Path = Path("data"), lane_count: int | None = None, simulation: bool = False):
    subscribers = set()
    drafts = {}
    editor_numbers = count(1)
    camera_changes = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        app.state.instance_id = str(uuid4())
        app.state.store = EventStore(Path(data_dir), lane_count)
        try:
            app.state.calibrations = CalibrationStore(Path(data_dir))
            app.state.settings = load_settings(data_dir)
            if any(lane > len(app.state.store.state["lanes"]) for camera in app.state.settings.cameras for lane in camera.lane_ids):
                raise ValueError("Kamerakonfiguration enthält unbekannte Bahn")
            app.state.cameras = CameraManager(app.state.settings.cameras)
            app.state.vision = VisionService(lambda: app.state.settings, app.state.cameras,
                                             app.state.calibrations, app.state.store, publish)
            app.state.vision_task = asyncio.create_task(app.state.vision.run())
            try:
                yield
            finally:
                app.state.vision_task.cancel()
                with anyio.CancelScope(shield=True):
                    await asyncio.gather(app.state.vision_task, return_exceptions=True)
                    await run_in_threadpool(app.state.cameras.close)
        finally:
            app.state.store.close()

    app = FastAPI(title="Biathlon Target Vision", version=__version__, lifespan=lifespan)
    static = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(CalibrationError)
    async def calibration_handler(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(OSError)
    async def storage_handler(request, exc):
        logging.exception("Lokaler Speicherzugriff fehlgeschlagen", exc_info=exc)
        return JSONResponse(status_code=503, content={"detail": "Speicherfehler. Serverprotokoll und Datenträger prüfen."})

    def api_identity():
        return {"api_version": API_VERSION, "instance_id": app.state.instance_id}

    def health_status():
        return "ok" if not app.state.store.failed and not app.state.vision_task.done() else "error"

    def snapshot():
        return {**app.state.store.snapshot(), **api_identity(), "simulation": simulation,
                "health": health_status(), "capture": {"running": not app.state.vision_task.done(),
                    **camera_list(), "calibration_errors": dict(app.state.vision.errors)}}

    def wake_subscribers():
        for queue in subscribers:
            if not queue.full():
                queue.put_nowait(None)

    def socket_snapshot(editor_id):
        # Entwürfe gehören nur zur lebenden Verbindung. Ausbleibende Erneuerung
        # entfernt auch bei stillen WLAN-Ausfällen veraltete Eingabeanzeigen.
        now = monotonic()
        for owner, (_, updated_at) in list(drafts.items()):
            if now - updated_at > 15:
                del drafts[owner]
        return {"type": "state", **snapshot(), "editor_id": editor_id,
                "drafts": [draft for draft, _ in drafts.values()]}

    def publish(command):
        duplicate = command.event_id in app.state.store.by_id
        event = app.state.store.apply(command)
        if isinstance(command, ManualTarget) and not duplicate and event["manual_input"]["mode"] == "mixed":
            save_correction_image(command, event)
        message = {"type": "state", **snapshot()}
        wake_subscribers()
        return {"event": event, "state": message}

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static / "tablet.html", headers={"Cache-Control": "no-store"})

    @app.get("/admin", include_in_schema=False)
    async def admin():
        return FileResponse(static / "admin.html", headers={"Cache-Control": "no-store"})

    def lane_camera(lane_id):
        return next((camera for camera in app.state.settings.cameras if lane_id in camera.lane_ids), None)

    def camera_list():
        result = []
        for camera in app.state.settings.cameras:
            capture = app.state.cameras.snapshot(camera.id)
            result.append({"id": camera.id, "name": camera.name, "lane_ids": camera.lane_ids,
                           "url_configured": True, "connected": capture["connected"],
                           "captured_at": capture["captured_at"].isoformat() if capture["captured_at"] else None})
        return {"cameras": result}

    def save_correction_image(command, event):
        camera = lane_camera(command.lane_id)
        if camera is None:
            return
        capture = app.state.cameras.snapshot(camera.id)
        if not capture["connected"] or capture["frame"] is None:
            return
        try:
            calibration = app.state.calibrations.load(command.lane_id)
            if not calibration or any(calibration.get(k) != v for k, v in camera_binding(camera).items()):
                return
            image = capture["frame"]
            x, y, width, height = cv2.boundingRect(np.int32(calibration["quad"]))
            crop = image[max(0, y):min(image.shape[0], y + height),
                         max(0, x):min(image.shape[1], x + width)]
            ok, encoded = cv2.imencode(".jpg", crop)
            if not ok:
                raise ValueError("JPEG-Kodierung fehlgeschlagen")
            directory = Path(data_dir) / "corrections"
            directory.mkdir(exist_ok=True)
            stem = directory / str(event["sequence"])
            stem.with_suffix(".jpg").write_bytes(encoded.tobytes())
            # Pufferbild ist ein Vergleichsbeleg, nicht zwingend das Bild der
            # letzten stabilisierten Beobachtung. Empfangszeit ausdrücklich angeben.
            stem.with_suffix(".json").write_text(json.dumps({
                "sequence": event["sequence"], "lane_id": command.lane_id,
                "target_id": command.target_id, "camera_id": camera.id,
                "captured_at": capture["captured_at"].isoformat(),
                "accepted_at": event["accepted_at"], **event["manual_input"],
            }, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError, cv2.error, CalibrationError):
            # Eine Bilddatei darf eine bereits bestätigte Kampfrichtereingabe
            # weder zurücknehmen noch als ungespeichert melden.
            logging.exception("Vergleichsbild für Korrektur %s konnte nicht gespeichert werden", event["sequence"])

    @app.get("/api/cameras")
    async def cameras():
        return camera_list()

    async def change_camera(request, camera_id=None):
        async with camera_changes:
            try:
                raw = await request.json()
                previous = next((c for c in app.state.settings.cameras if c.id == camera_id), None)
                if camera_id is not None and previous is None:
                    raise HTTPException(404, "Kamera existiert nicht")
                if previous and not raw.get("url"):
                    raw["url"] = previous.url
                camera = CameraSettings.model_validate(raw)
                if camera_id is not None and camera.id != camera_id:
                    raise ValueError("Kennung kann nicht geändert werden")
                if camera_id is None and any(c.id == camera.id for c in app.state.settings.cameras):
                    raise ValueError("Kennung bereits vorhanden")
                if any(str(n) not in app.state.store.state["lanes"] for n in camera.lane_ids):
                    raise ValueError("Unbekannte Bahn")
                settings = Settings.model_validate({**app.state.settings.model_dump(), "cameras":
                    [c.model_dump() for c in app.state.settings.cameras if c.id != camera.id] + [camera.model_dump()]})
            except (ValueError, TypeError, AttributeError):
                # Validierungsdetails enthalten sonst eventuell die vollständige RTSP-URL.
                raise HTTPException(422, "Ungültige Kamera: Kennung, RTSP-Adresse und eindeutige Bahnzuordnung prüfen.") from None
            save_settings(data_dir, settings)
            await run_in_threadpool(app.state.cameras.configure, settings.cameras)
            app.state.settings = settings
            return camera_list()

    @app.post("/api/cameras")
    async def add_camera(request: Request):
        return await change_camera(request)

    @app.put("/api/cameras/{camera_id}")
    async def edit_camera(camera_id: str, request: Request):
        return await change_camera(request, camera_id)

    @app.delete("/api/cameras/{camera_id}")
    async def remove_camera(camera_id: str):
        async with camera_changes:
            if not any(c.id == camera_id for c in app.state.settings.cameras):
                raise HTTPException(404, "Kamera existiert nicht")
            settings = app.state.settings.model_copy(update={"cameras": [c for c in app.state.settings.cameras if c.id != camera_id]})
            save_settings(data_dir, settings)
            await run_in_threadpool(app.state.cameras.configure, settings.cameras)
            app.state.settings = settings
            return camera_list()

    @app.get("/api/cameras/{camera_id}/frame")
    async def camera_frame(camera_id: str):
        if not any(c.id == camera_id for c in app.state.settings.cameras):
            raise HTTPException(404, "Kamera existiert nicht")
        capture = app.state.cameras.snapshot(camera_id)
        if capture["frame"] is None:
            raise HTTPException(503, "Kein aktuelles Kamerabild verfügbar")
        ok, encoded = await run_in_threadpool(cv2.imencode, ".jpg", capture["frame"])
        if not ok:
            raise HTTPException(503, "Kamerabild konnte nicht kodiert werden")
        return Response(encoded.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    async def health():
        status = health_status()
        return JSONResponse({"status": status, "version": __version__, **api_identity()},
                            status_code=200 if status == "ok" else 503)

    @app.get("/monitor", include_in_schema=False)
    async def monitor():
        return FileResponse(static / "monitor.html", headers={"Cache-Control": "no-store"})

    @app.get("/calibration", include_in_schema=False)
    async def calibration_page():
        return FileResponse(static / "calibration.html")

    @app.get("/api/state")
    async def state():
        return JSONResponse(snapshot(), headers={"Cache-Control": "no-store"})

    @app.get("/api/events")
    async def events(after: int = Query(0, ge=0), limit: int = Query(1000, ge=1, le=1000)):
        return JSONResponse({"events": app.state.store.history(after, limit),
                             "sequence": app.state.store.state["sequence"], **api_identity()},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/observations")
    async def observations(command: Observation, x_lane_revision: int | None = Header(default=None, ge=0)):
        if command.source == "simulator" and not simulation:
            raise HTTPException(403, "Simulationsbetrieb ist deaktiviert.")
        # Optionaler Revisionsschutz für manuelle Simulation; Kameras behalten
        # ihre bisherige Schnittstelle. Prüfung und Verarbeitung ohne await.
        if x_lane_revision is not None and command.event_id not in app.state.store.by_id:
            lane = app.state.store.state["lanes"].get(str(command.lane_id))
            if lane is None or lane["revision"] != x_lane_revision:
                raise Conflict("Bahn wurde zwischenzeitlich geändert. Zustand neu laden.")
        return publish(command)

    @app.put("/api/lanes/{lane_id}/bib")
    async def assign(lane_id: int, command: Assignment):
        if lane_id != command.lane_id:
            raise HTTPException(422, "Bahnnummer in URL und Befehl unterscheiden sich.")
        return publish(command)

    @app.post("/api/lanes/{lane_id}/release")
    async def release(lane_id: int, command: Release):
        if lane_id != command.lane_id:
            raise HTTPException(422, "Bahnnummer in URL und Befehl unterscheiden sich.")
        return publish(command)

    def lane_control(lane_id, command):
        if lane_id != command.lane_id:
            raise HTTPException(422, "Bahnnummer in URL und Befehl unterscheiden sich.")
        return publish(command)

    @app.put("/api/lanes/{lane_id}/mode")
    async def set_mode(lane_id: int, command: ModeChange):
        return lane_control(lane_id, command)

    @app.post("/api/lanes/{lane_id}/manual-target")
    async def manual_target(lane_id: int, command: ManualTarget):
        return lane_control(lane_id, command)

    @app.post("/api/lanes/{lane_id}/override-release")
    async def override_release(lane_id: int, command: OverrideRelease):
        return lane_control(lane_id, command)

    @app.post("/api/lanes/{lane_id}/reset")
    async def manual_reset(lane_id: int, command: ManualReset):
        return lane_control(lane_id, command)

    @app.websocket("/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        queue = asyncio.Queue(maxsize=1)
        subscribers.add(queue)
        editor_id = next(editor_numbers)
        reader = None
        pending = None
        try:
            await socket.send_json(socket_snapshot(editor_id))

            async def receive_until_disconnect():
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    try:
                        raw = message.get("text", "")
                        if len(raw) > 1024:
                            raise ValueError("Entwurf zu groß")
                        data = json.loads(raw)
                        if data["type"] == "draft_clear":
                            if socket in drafts:
                                del drafts[socket]
                                wake_subscribers()
                            continue
                        lane_id, value, bout_id = data["lane_id"], data["value"], data.get("bout_id")
                        if data["type"] != "draft" or type(lane_id) is not int or str(lane_id) not in app.state.store.state["lanes"]:
                            raise ValueError("Ungültige Bahn")
                        if not isinstance(value, str) or len(value) > 15 or (value and not (value.isascii() and value.isdigit())):
                            raise ValueError("Ungültige Startnummer")
                        if bout_id is not None:
                            bout = app.state.store.state["bouts"].get(bout_id) if isinstance(bout_id, str) else None
                            if not bout or bout["lane_id"] != lane_id:
                                raise ValueError("Ungültige Einlage")
                    except (ValueError, KeyError, TypeError):
                        await socket.close(code=1008, reason="Ungültiger Eingabeentwurf")
                        return
                    draft = {"editor_id": editor_id, "lane_id": lane_id, "bout_id": bout_id, "value": value}
                    previous = drafts.get(socket)
                    drafts[socket] = (draft, monotonic())
                    if previous is None or previous[0] != draft:
                        wake_subscribers()

            reader = asyncio.create_task(receive_until_disconnect())
            while True:
                pending = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait([reader, pending], timeout=5, return_when=asyncio.FIRST_COMPLETED)
                if reader in done:
                    await reader
                    break
                if pending not in done:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                # Ein zusammenhängender Stand verhindert, dass zusammengefasste
                # Entwurfsnachrichten eine offizielle Zustandsänderung verdrängen.
                await socket.send_json(socket_snapshot(editor_id))
        except WebSocketDisconnect:
            pass
        finally:
            subscribers.discard(queue)
            if socket in drafts:
                del drafts[socket]
                wake_subscribers()
            tasks = [task for task in (reader, pending) if task is not None]
            for task in tasks:
                task.cancel()
            # ASGI kann beim Trennen bereits den äußeren CancelScope abbrechen.
            # Die eigenen Lesetasks trotzdem vollständig einsammeln.
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)

    def check_lane(lane_id):
        if str(lane_id) not in app.state.store.state["lanes"]:
            raise HTTPException(404, "Schießbahn existiert nicht.")

    async def read_image(upload):
        data = await upload.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise CalibrationError("Bilddatei ist größer als 10 MiB.")
        try:
            image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR) if data else None
        except cv2.error as exc:
            raise CalibrationError("Bilddatei konnte nicht dekodiert werden.") from exc
        if image is None or image.shape[0] * image.shape[1] > 20_000_000:
            raise CalibrationError("Kein lesbares Bild oder mehr als 20 Megapixel.")
        return image

    @app.get("/api/lanes/{lane_id}/calibration")
    async def get_calibration(lane_id: int):
        check_lane(lane_id)
        saved = app.state.calibrations.load(lane_id)
        camera = lane_camera(lane_id)
        if camera is None:
            return {"calibration": saved}
        valid = bool(saved and camera and all(saved.get(key) == value for key, value in camera_binding(camera).items()))
        return {"calibration": saved, "camera_id": camera.id if camera else None, "valid_for_camera": valid}

    @app.post("/api/lanes/{lane_id}/calibration")
    async def set_calibration(lane_id: int, image: UploadFile = File(), quad: str = Form()):
        check_lane(lane_id)
        try:
            points = json.loads(quad)
        except ValueError as exc:
            raise CalibrationError("ROI muss eine JSON-Liste mit vier Bildpunkten sein.") from exc
        camera = lane_camera(lane_id)
        frame = await read_image(image)
        try:
            result = await run_in_threadpool(calibrate, frame, points)
        except (TypeError, ValueError) as exc:
            raise CalibrationError(str(exc)) from exc
        if camera != lane_camera(lane_id):
            raise HTTPException(409, "Kamerazuordnung wurde geändert. Bild neu übernehmen.")
        if camera:
            result.update(camera_binding(camera))
        await run_in_threadpool(app.state.calibrations.save, lane_id, result)
        return {"calibration": result}

    @app.post("/api/lanes/{lane_id}/calibration/align")
    async def align_calibration(lane_id: int, image: UploadFile = File()):
        check_lane(lane_id)
        saved = app.state.calibrations.load(lane_id)
        if saved is None:
            raise CalibrationError("Für diese Bahn wurde noch keine Kalibrierung gespeichert.")
        result = await run_in_threadpool(align, await read_image(image), saved)
        return {"calibration": result}

    return app
