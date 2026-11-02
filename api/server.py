"""Loopback-only replay API. No external service, credentials or fabricated runs.

Run with ``python -m api.server --replay-dir web/public/replays``.
Generation endpoints are deliberately unavailable until the real runner is wired.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_REPLAY_BYTES = 64 * 1024 * 1024
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


class ArtifactError(Exception):
    """An absent or invalid artifact, not a traffic outcome."""


def reject_nonfinite(value: str):
    raise ValueError(f"Non-finite JSON: {value}")


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise ArtifactError("Artifact is not available")
    if path.stat().st_size > MAX_REPLAY_BYTES:
        raise ArtifactError("Artifact exceeds the local API size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
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
    return validated_replay(path)


def validated_replay(path: Path) -> dict:
    data = read_json(path)
    try:
        from export.replay import validate_replay
        validate_replay(data)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        raise ArtifactError(f"Run failed recorded replay validation: {exc}") from exc
    return data


def local_origin(origin: str | None) -> str | None:
    """Allow the local dev viewer only; never wildcard or credentialed CORS."""
    if not origin:
        return None
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        parsed.port  # Reject malformed port syntax.
    except ValueError:
        return None
    if (parsed.scheme == "http" and hostname in {"127.0.0.1", "localhost", "::1"}
            and not parsed.username and not parsed.password and not parsed.path
            and not parsed.query and not parsed.fragment):
        return origin
    return None


def make_handler(replay_dir: Path, jobs=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AfterlightLocal/0.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def send_json(self, code: int, data: dict) -> None:
            body = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = local_origin(self.headers.get("Origin"))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not local_origin("http://" + self.headers.get("Host", "")):
                self.send_json(403, {"error": "Local Host header required"})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    self.send_json(200, {"status": "ready", "mode": "local-recordings", "generation_available": jobs is not None})
                elif path == "/api/catalog":
                    data = catalog(replay_dir)
                    rows = [{**row, "url": f"/api/runs/{row['id']}"} for row in data["runs"]]
                    self.send_json(200, {**data, "runs": rows})
                elif path.startswith("/api/jobs/") and jobs is not None:
                    parts = path.removeprefix("/api/jobs/").split("/")
                    job_id = parts[0]
                    job = jobs.get(job_id)
                    if not job:
                        self.send_json(404, {"error": "Unknown local generation job"})
                    elif len(parts) == 2 and parts[1] == "replay":
                        artifact = jobs.replay_path(job_id)
                        if artifact:
                            self.send_json(200, validated_replay(artifact))
                        else:
                            self.send_json(409, {"error": "No completed replay is available yet", "status": job["status"]})
                    elif len(parts) == 1:
                        self.send_json(200, job)
                    else:
                        self.send_json(404, {"error": "Endpoint not found"})
                elif path.startswith("/api/runs/"):
                    self.send_json(200, replay(replay_dir, path.removeprefix("/api/runs/")))
                else:
                    self.send_json(404, {"error": "Endpoint not found"})
            except ArtifactError as exc:
                self.send_json(422, {"error": str(exc)})
            except OSError:
                self.send_json(503, {"error": "Local artifact storage is unavailable"})

        def do_OPTIONS(self) -> None:
            if not local_origin("http://" + self.headers.get("Host", "")) or not local_origin(self.headers.get("Origin")):
                self.send_json(403, {"error": "Only a loopback viewer origin is allowed"})
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:
            if jobs is None:
                self.send_json(501, {"error": "Local generation is disabled; use recorded runs or explicitly enable the local runner", "generation_available": False})
                return
            # Binding loopback is not sufficient against browser cross-origin or
            # DNS rebinding requests. Validate Host as well as any supplied Origin.
            if not local_origin("http://" + self.headers.get("Host", "")):
                self.send_json(403, {"error": "Local Host header required"})
                return
            if self.headers.get("Origin") and not local_origin(self.headers["Origin"]):
                self.send_json(403, {"error": "Only a loopback viewer origin is allowed"})
                return
            if urlsplit(self.path).path != "/api/runs":
                self.send_json(404, {"error": "Endpoint not found"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.send_json(415, {"error": "Content-Type application/json required"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Request body must contain 1..16384 bytes")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body")
                body = json.loads(raw, parse_constant=reject_nonfinite)
                self.send_json(202, jobs.submit(body))
            except (socket.timeout, TimeoutError):
                self.send_json(408, {"error": "Request body timed out"})
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, default=Path("web/public/replays"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--enable-generation", action="store_true", help="Explicitly enable one-at-a-time real local SUMO jobs")
    parser.add_argument("--job-dir", type=Path, default=Path("local-runtime/jobs"))
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024..65535")
    jobs = None
    if args.enable_generation:
        from api.jobs import JobManager
        jobs = JobManager(args.job_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.replay_dir.resolve(), jobs))
    print(f"Afterlight local recordings: http://127.0.0.1:{args.port}/api/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if jobs is not None:
            print("Waiting for any active SUMO job to finish safely…", flush=True)
            jobs.close()


if __name__ == "__main__":
    main()
