"""Serve the committed application preview on loopback; no Node installation needed."""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ASSET_ROUTES = {
    "/brand/mark.svg": "brand/mark.svg",
    "/brand/social-preview.jpg": "brand/social-preview.jpg",
    "/fonts/InterVariable.woff2": "fonts/InterVariable.woff2",
    "/fonts/Inter-LICENSE.txt": "fonts/Inter-LICENSE.txt",
    "/media/afterlight-desktop-demo.mp4": "media/afterlight-desktop-demo.mp4",
}


def verify() -> dict:
    manifest = json.loads((ROOT / "preview/manifest.json").read_text(encoding="utf-8"))
    for section in ("source_files", "output_files", "runtime_assets"):
        for name, expected in manifest[section].items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError(f"Missing or unsafe preview input: {name}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Preview input changed: {name}; rebuild before testing")
    return manifest


def resolve_request(raw: str) -> Path | None:
    path = unquote(urlsplit(raw).path)
    parts = path.split("/")
    if any(p in ("..", ".") or ":" in p or "\\" in p or "\x00" in p for p in parts):
        return None
    if path.startswith("/assets/exports/"):
        base, relative = ROOT / "assets/exports", path.removeprefix("/assets/exports/")
    elif path == "/assets/map/city_manifest.json":
        base, relative = ROOT / "assets/map", "city_manifest.json"
    elif path == "/THIRD_PARTY_NOTICES.txt":
        base, relative = ROOT / "web/public", "THIRD_PARTY_NOTICES.txt"
        current = ROOT
        for part in ("web", "public", relative):
            current = current / part
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                return None
    elif path in PUBLIC_ASSET_ROUTES:
        base, relative = ROOT / "web/public", PUBLIC_ASSET_ROUTES[path]
        current = ROOT
        for part in ("web", "public", *relative.split("/")):
            current = current / part
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                return None
    elif path.lstrip("/").split("/", 1)[0].casefold() in {"brand", "fonts", "media"}:
        # These namespaces expose only the exact files above. Do not let an
        # unlisted or differently cased path fall through to compiled output.
        return None
    elif path in ("/assets/previews/city_overview.png", "/assets/previews/city_expanded.png",
                  "/assets/previews/ambulance_model.png", "/assets/previews/ghost_model.png"):
        base, relative = ROOT / "assets/previews", path.rsplit("/", 1)[1]
    elif path.startswith("/replays/"):
        base, relative = ROOT / "web/public/replays", path.removeprefix("/replays/")
    elif path.startswith("/study/"):
        base, relative = ROOT / "web/public/study", path.removeprefix("/study/")
        # Only explicitly public study files are served. Reject redirected
        # folders/files as well as lexical traversal, including Windows junctions.
        current = ROOT
        for part in ("web", "public", "study", *relative.split("/")):
            current = current / part
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                return None
    else:
        base, relative = ROOT / "preview/site", path.lstrip("/") or "index.html"
    candidate = (base / relative).resolve()
    return candidate if candidate.is_relative_to(base.resolve()) and candidate.is_file() else None


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        self.respond(False)

    def do_GET(self) -> None:
        self.respond(True)

    def respond(self, body: bool) -> None:
        if self.headers.get("Host") not in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
        }:
            self.send_error(403)
            return
        path = resolve_request(self.path)
        if path is None:
            self.send_error(404)
            return
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        mime = {".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".txt": "text/plain; charset=utf-8",
                ".glb": "model/gltf-binary", ".svg": "image/svg+xml", ".woff2": "font/woff2",
                ".jpg": "image/jpeg", ".mp4": "video/mp4"}.get(path.suffix)
        self.send_response(200)
        self.send_header("Content-Type", mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if body:
            self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = verify()
    print(f"Preview compiled from {manifest['source_commit']}", flush=True)
    if args.verify_only:
        return
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Static: http://127.0.0.1:{args.port}/", flush=True)
        print(f"Local API: http://127.0.0.1:{args.port}/local.html", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
