"""Zielbeobachtungen ohne Video über denselben REST-Eingang wie Kameras senden."""

import argparse
from datetime import datetime, timezone
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def send_observation(url, lane_id, action, target_id=None):
    with urlopen(url.rstrip("/") + "/api/state", timeout=10) as response:
        session_id = json.load(response)["session_id"]
    command = {"event_id": str(uuid4()), "lane_id": lane_id,
               "kind": "reset" if action == "reset" else "target",
               "source": "simulator", "observed_at": datetime.now(timezone.utc).isoformat()}
    if action != "reset":
        command.update(target_id=target_id, state={"hit": "fallen", "standing": "standing", "unknown": "unknown"}[action])
    request = Request(url.rstrip("/") + "/api/observations", data=json.dumps(command).encode(),
                      headers={"Content-Type": "application/json", "X-Session-ID": session_id}, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description="Einzelne Zielzustände oder Rückstellung simulieren")
    parser.add_argument("action", choices=["hit", "reset", "standing", "unknown"])
    parser.add_argument("lane", type=int)
    parser.add_argument("target", nargs="?", type=int, choices=range(1, 6))
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    args = parser.parse_args()
    if args.lane < 1 or (args.action == "reset") != (args.target is None):
        parser.error("Positive Bahnnummer angeben; Zielnummer nur bei hit, standing oder unknown.")
    try:
        result = send_observation(args.url, args.lane, args.action, args.target)
    except HTTPError as exc:
        parser.exit(1, f"Serverfehler {exc.code}: {exc.read().decode()}\n")
    except URLError as exc:
        parser.exit(1, f"Server nicht erreichbar: {exc.reason}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
