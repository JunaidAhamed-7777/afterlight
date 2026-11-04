"""Small loopback ASGI bridge: ``python -m cloud.dev_server --port 8766``.

This development server needs only the standard library. It forwards the real
request-scoped endpoint without buffering its NDJSON response or starting jobs
at import time. Production hosting supplies its own ASGI transport.
"""
from __future__ import annotations

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import select
import socket
from urllib.parse import urlsplit


REQUEST_BYTES = 4096
REQUEST_READ_SECONDS = 10


def make_handler(application):
    class ASGIHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, _format, *_args):
            pass

        def _problem(self, status, message):
            payload = (json.dumps({"error": message}) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()

        def _dispatch(self):
            self.close_connection = True
            path = urlsplit(self.path)
            if path.path not in {"/api/simulate", "/api/cancel"}:
                self._problem(404, "Unknown endpoint.")
                return
            try:
                hosts = self.headers.get_all("Host", [])
                authority = urlsplit("//" + hosts[0]) if len(hosts) == 1 else None
                if (not authority or authority.hostname not in {"127.0.0.1", "localhost"} or
                        authority.port != self.server.server_port or authority.username is not None or
                        authority.password is not None or authority.path or authority.query or authority.fragment):
                    raise ValueError()
            except ValueError:
                self._problem(400, "Use this server's loopback address.")
                return
            if self.headers.get_all("Transfer-Encoding"):
                self._problem(400, "Chunked request bodies are not supported.")
                return
            lengths = self.headers.get_all("Content-Length", [])
            if self.command == "POST" and not lengths:
                self._problem(411, "Send a bounded JSON request with Content-Length.")
                return
            try:
                if len(lengths) > 1 or (lengths and not lengths[0].isascii()) or (lengths and not lengths[0].isdecimal()):
                    raise ValueError()
                length = int(lengths[0]) if lengths else 0
            except ValueError:
                self._problem(400, "Invalid request length.")
                return
            if length > REQUEST_BYTES:
                self._problem(413, "Journey request is too large.")
                return
            self.connection.settimeout(REQUEST_READ_SECONDS)
            try:
                body = self.rfile.read(length) if length else b""
            except TimeoutError:
                self._problem(408, "Journey request timed out.")
                return
            if len(body) != length:
                self._problem(400, "Journey request ended before its declared length.")
                return
            # Bounded socket writes also keep an unresponsive loopback client
            # from blocking the request's ASGI cancellation/deadline handling.
            self.connection.settimeout(1)
            started = False
            finished = False
            disconnected = False
            delivered_body = False

            async def receive():
                nonlocal delivered_body, disconnected
                if not delivered_body:
                    delivered_body = True
                    return {"type": "http.request", "body": body, "more_body": False}
                # Poll only after the body event. A cancellable async pause,
                # rather than an endless executor thread, permits normal ASGI
                # completion to close its event loop immediately.
                while not disconnected:
                    try:
                        readable, _, exceptional = select.select([self.connection], [], [self.connection], 0)
                        if exceptional or (readable and not self.connection.recv(1, socket.MSG_PEEK)):
                            disconnected = True
                            break
                    except (OSError, ValueError):
                        disconnected = True
                        break
                    await asyncio.sleep(.05)
                return {"type": "http.disconnect"}

            async def send(message):
                nonlocal started, finished, disconnected
                if disconnected:
                    raise ConnectionResetError("The client disconnected")
                try:
                    if message["type"] == "http.response.start":
                        if started:
                            raise RuntimeError("ASGI response started twice")
                        headers = []
                        for name, value in message.get("headers", []):
                            name, value = name.decode("ascii"), value.decode("latin-1")
                            if not name or any(c in name + value for c in "\r\n"):
                                raise ValueError("Invalid ASGI response header")
                            if name.lower() not in {"connection", "transfer-encoding"}:
                                headers.append((name, value))
                        self.send_response(message["status"])
                        for name, value in headers:
                            self.send_header(name, value)
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.flush()
                        started = True
                    elif message["type"] == "http.response.body":
                        if not started or finished:
                            raise RuntimeError("ASGI response body is out of order")
                        self.wfile.write(message.get("body", b""))
                        self.wfile.flush()
                        finished = not message.get("more_body", False)
                    else:
                        raise RuntimeError("Unsupported ASGI response event")
                except OSError:
                    disconnected = True
                    raise

            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                     "http_version": self.request_version.removeprefix("HTTP/"), "method": self.command,
                     "scheme": "http", "path": path.path, "raw_path": path.path.encode("ascii"),
                     "query_string": path.query.encode("latin-1"), "root_path": "",
                     "headers": [(name.lower().encode("ascii"), value.encode("latin-1"))
                                 for name, value in self.headers.raw_items()],
                     "client": self.client_address, "server": self.server.server_address}
            try:
                asyncio.run(application(scope, receive, send))
                if not started:
                    self._problem(500, "The ASGI endpoint returned no response.")
            except (OSError, asyncio.CancelledError):
                pass  # The endpoint owns cancellation and request-worker cleanup.
            except Exception:
                if not started:
                    self._problem(500, "The ASGI endpoint could not respond.")

        do_GET = _dispatch
        do_POST = _dispatch
        do_PUT = _dispatch
        do_DELETE = _dispatch
        do_PATCH = _dispatch
        do_OPTIONS = _dispatch
        do_HEAD = _dispatch

    return ASGIHandler


async def endpoint_router(scope, receive, send):
    if scope.get("path") == "/api/cancel":
        from api.cancel import app
    else:
        from api.simulate import app
    await app(scope, receive, send)


def make_server(port=8766, *, application=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Choose a valid loopback port")
    if application is None:
        application = endpoint_router
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(application))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Choose a port from 0 through 65535")
    with make_server(args.port) as server:
        print(f"AFTERLIGHT request-owned simulator: http://127.0.0.1:{server.server_port}/api/simulate", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
