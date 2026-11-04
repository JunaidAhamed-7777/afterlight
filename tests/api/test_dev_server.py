"""Real loopback transport with synthetic ASGI apps; no SUMO or traffic evidence."""
import asyncio
from contextlib import contextmanager
import http.client
import json
import socket
import threading
import unittest
from unittest.mock import patch

from cloud.dev_server import make_server


@contextmanager
def running(application):
    server = make_server(0, application=application)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def json_app(scope, receive, send):
    event = await receive()
    payload = json.dumps({"method": scope["method"], "path": scope["path"],
                          "body": event["body"].decode(), "headers": len(scope["headers"])}).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


class DevServerTests(unittest.TestCase):
    def test_get_and_exact_post_body_reach_asgi_with_connection_close(self):
        with running(json_app) as server:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            for method, body in (("GET", None), ("POST", b'{"synthetic":"only"}')):
                client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                client.request(method, "/api/simulate", body=body, headers={"Content-Type": "application/json"})
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.version, 10)
                self.assertEqual(response.getheader("Connection"), "close")
                self.assertEqual(response.getheader("Cache-Control"), "no-store")
                value = json.loads(response.read())
                self.assertEqual(value["body"], (body or b"").decode())
                self.assertEqual((value["method"], value["path"]), (method, "/api/simulate"))
                client.close()

    def test_first_ndjson_event_arrives_before_application_can_finish(self):
        release = threading.Event()
        finished = threading.Event()

        async def stream(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/x-ndjson")]})
            await send({"type": "http.response.body", "body": b'{"event":"first"}\n', "more_body": True})
            while not release.is_set():
                await asyncio.sleep(.01)
            await send({"type": "http.response.body", "body": b'{"event":"last"}\n', "more_body": False})
            finished.set()

        with running(stream) as server:
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            try:
                client.request("POST", "/api/simulate", body=b"{}")
                response = client.getresponse()
                self.assertEqual(response.readline(), b'{"event":"first"}\n')
                self.assertFalse(finished.is_set(), "response must stream before ASGI completion")
                release.set()
                self.assertEqual(response.read(), b'{"event":"last"}\n')
                self.assertTrue(finished.wait(1))
            finally:
                release.set()
                client.close()

    def test_disconnect_is_delivered_after_the_actual_request_body(self):
        observed = []
        disconnected = threading.Event()

        async def wait_for_disconnect(scope, receive, send):
            observed.append(await receive())
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"ready\n", "more_body": True})
            observed.append(await receive())
            disconnected.set()

        with running(wait_for_disconnect) as server:
            client = socket.create_connection(server.server_address, timeout=2)
            stream = client.makefile("rb")
            client.sendall((f"POST /api/simulate HTTP/1.0\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                            "Content-Length: 4\r\n\r\nbody").encode())
            while stream.readline() != b"\r\n":
                pass
            self.assertEqual(stream.readline(), b"ready\n")
            client.shutdown(socket.SHUT_RDWR)
            stream.close()
            client.close()
            self.assertTrue(disconnected.wait(2))
            self.assertEqual(observed, [{"type": "http.request", "body": b"body", "more_body": False},
                                        {"type": "http.disconnect"}])

    def test_normal_completion_cancels_pending_disconnect_receive_without_thread_hang(self):
        cleaned = threading.Event()

        async def complete(scope, receive, send):
            await receive()
            watcher = asyncio.create_task(receive())
            try:
                await send({"type": "http.response.start", "status": 200})
                await send({"type": "http.response.body", "body": b"done", "more_body": False})
            finally:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
                cleaned.set()

        with running(complete) as server:
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            client.request("GET", "/api/simulate")
            self.assertEqual(client.getresponse().read(), b"done")
            self.assertTrue(cleaned.wait(1))
            client.close()

    def test_request_bounds_and_routes_reject_before_asgi(self):
        async def forbidden(*_args):
            self.fail("Rejected request reached the ASGI application")

        cases = [
            ("/unknown", "Content-Length: 0\r\n", 404),
            ("/api/simulate", "Content-Length: 4097\r\n", 413),
            ("/api/simulate", "Content-Length: -1\r\n", 400),
            ("/api/simulate", "Content-Length: wrong\r\n", 400),
            ("/api/simulate", "Content-Length: 0\r\nContent-Length: 0\r\n", 400),
            ("/api/simulate", "Transfer-Encoding: chunked\r\n", 400),
            ("/api/simulate", "", 411),
        ]
        with running(forbidden) as server:
            for path, headers, expected in cases:
                with self.subTest(headers=headers), socket.create_connection(server.server_address, timeout=2) as client:
                    client.sendall((f"POST {path} HTTP/1.0\r\nHost: 127.0.0.1:{server.server_port}\r\n" + headers + "\r\n").encode())
                    self.assertIn(f" {expected} ".encode(), client.recv(4096).split(b"\r\n", 1)[0])

    def test_foreign_host_is_rejected_and_port_has_no_external_bind_option(self):
        with running(json_app) as server:
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            client.request("GET", "/api/simulate", headers={"Host": "attacker.example"})
            self.assertEqual(client.getresponse().status, 400)
            client.close()
        for port in (-1, 65536, True, "8766"):
            with self.assertRaises(ValueError):
                make_server(port, application=json_app)

    def test_default_app_is_lazy_and_importing_server_does_not_launch_listener(self):
        with patch("cloud.dev_server.ThreadingHTTPServer") as server, patch("api.simulate.app", json_app):
            make_server(8766)
            self.assertEqual(server.call_args.args[0], ("127.0.0.1", 8766))

    def test_default_router_sends_cancel_and_simulate_to_their_own_asgi_apps(self):
        seen = []

        def endpoint(name, status):
            async def application(scope, receive, send):
                seen.append((name, scope["path"], (await receive())["body"]))
                await send({"type": "http.response.start", "status": status})
                await send({"type": "http.response.body", "body": name.encode(), "more_body": False})
            return application

        with patch("api.cancel.app", endpoint("cancel", 202)), patch("api.simulate.app", endpoint("simulate", 200)), running(None) as server:
            for path, expected, body in (("cancel", 202, b'{"request_id":"synthetic-only"}'),
                                         ("simulate", 200, b"{}")):
                client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                client.request("POST", "/api/" + path, body=body, headers={"Content-Type": "application/json"})
                response = client.getresponse()
                self.assertEqual(response.status, expected)
                self.assertEqual(response.read(), path.encode())
                client.close()
        self.assertEqual(seen, [("cancel", "/api/cancel", b'{"request_id":"synthetic-only"}'),
                                ("simulate", "/api/simulate", b"{}")])


if __name__ == "__main__":
    unittest.main()
