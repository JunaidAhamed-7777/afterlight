"""Loopback-only replay API. No external service, credentials or fabricated runs.

Run with ``python -m api.server --replay-dir web/public/replays``.
Generation endpoints are deliberately unavailable until the real runner is wired.
"""
from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_REPLAY_BYTES = 64 * 1024 * 1024
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


class ArtifactError(Exception):
    """An absent or invalid artifact, not a traffic outcome."""


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise ArtifactError("Artifact is not available")
    if path.stat().st_size > MAX_REPLAY_BYTES:
        raise ArtifactError("Artifact exceeds the local API size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArtifactError("Artifact is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ArtifactError("Artifact root must be an object")
    return value


def catalog(replay_dir: Path) -> dict:
    path = replay_dir / "catalog.json"
    if not path.exists():
        return {"schema": "afterlight.catalog.v1", "runs": []}
    data = read_json(path)
    if data.get("schema") != "afterlight.catalog.v1" or not isinstance(data.get("runs"), list):
        raise ArtifactError("Catalog schema is invalid")
    # The API exposes only catalogued recordings, never arbitrary filesystem paths.
    for row in data["runs"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not SAFE_ID.fullmatch(row["id"]):
            raise ArtifactError("Catalog contains an invalid run ID")
    return data


def replay(replay_dir: Path, run_id: str) -> dict:
    if not SAFE_ID.fullmatch(run_id):
        raise ArtifactError("Invalid run ID")
    if run_id not in {row["id"] for row in catalog(replay_dir)["runs"]}:
        raise ArtifactError("Run is not in the published catalog")
    path = replay_dir / f"{run_id}.json"
    if path.resolve().parent != replay_dir.resolve():
        raise ArtifactError("Run path is outside the replay directory")
    data = read_json(path)
    if data.get("schema") != "afterlight.replay.v1" or data.get("mode") != "recorded":
        raise ArtifactError("Run is not a supported recorded replay")
    return data


def make_handler(replay_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AfterlightLocal/0.1"

        def send_json(self, code: int, data: dict) -> None:
            body = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    self.send_json(200, {"status": "ready", "mode": "local-recordings", "generation_available": False})
                elif path == "/api/catalog":
                    data = catalog(replay_dir)
                    rows = [{**row, "url": f"/api/runs/{row['id']}"} for row in data["runs"]]
                    self.send_json(200, {**data, "runs": rows})
                elif path.startswith("/api/runs/"):
                    self.send_json(200, replay(replay_dir, path.removeprefix("/api/runs/")))
                else:
                    self.send_json(404, {"error": "Endpoint not found"})
            except ArtifactError as exc:
                self.send_json(422, {"error": str(exc)})
            except OSError:
                self.send_json(503, {"error": "Local artifact storage is unavailable"})

        def do_POST(self) -> None:
            self.send_json(501, {"error": "Live generation is not implemented in this checkpoint; use actual recorded runs", "generation_available": False})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, default=Path("web/public/replays"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024..65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.replay_dir.resolve()))
    print(f"Afterlight local recordings: http://127.0.0.1:{args.port}/api/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
