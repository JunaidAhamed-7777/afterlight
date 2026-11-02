"""Local artifact boundary tests; execute on the Omen acceptance machine."""
import json
import tempfile
import unittest
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from pathlib import Path
from api.server import ArtifactError, catalog, replay, make_handler, local_origin


def synthetic_replay():
    # Explicit unit fixture, never a public recording or traffic result.
    return {"schema": "afterlight.replay.v1", "mode": "recorded", "duration_s": 1, "step_s": 1,
            "coordinates": {"position_reference": "front_bumper"}, "scenario": {"network_kind": "fixture"},
            "provenance": dict(source_commit="fixture", network_sha256="fixture", demand_sha256="fixture", sumo_version="fixture"),
            "worlds": {w: {"world_id": w, "status": "completed", "policy": "ordinary" if w == "baseline" else "fixed",
                           "frames": [{"t": 0, "vehicles": []}, {"t": 1, "vehicles": []}]} for w in ("baseline", "afterlight")}}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def test_cors_only_accepts_loopback_viewer_origins(self):
        self.assertEqual(local_origin("http://localhost:5173"), "http://localhost:5173")
        for origin in ("https://example.com", "http://localhost.evil.test", "null", "http://user@localhost:5173", "http://localhost:5173/path"):
            self.assertIsNone(local_origin(origin))

    def test_empty_catalog_has_no_invented_runs(self):
        self.assertEqual(catalog(self.root)["runs"], [])

    def test_rejects_uncatalogued_run(self):
        self.write("secret.json", {"schema": "afterlight.replay.v1", "mode": "recorded"})
        with self.assertRaises(ArtifactError):
            replay(self.root, "secret")

    def test_rejects_traversal(self):
        for name in ("../secret", "foo/bar", "%2e%2e", "", "x.json"):
            with self.assertRaises(ArtifactError):
                replay(self.root, name)

    def test_reads_only_explicit_recorded_artifact(self):
        self.write("catalog.json", {"schema": "afterlight.catalog.v1", "runs": [{"id": "run-1"}]})
        self.write("run-1.json", synthetic_replay())
        self.assertEqual(replay(self.root, "run-1")["mode"], "recorded")
        self.write("run-1.json", {"schema": "afterlight.replay.v1", "mode": "live"})
        with self.assertRaises(ArtifactError):
            replay(self.root, "run-1")

    def test_incomplete_replay_rejected(self):
        self.write("catalog.json", {"schema": "afterlight.catalog.v1", "runs": [{"id": "run-1"}]})
        self.write("run-1.json", {"schema": "afterlight.replay.v1", "mode": "recorded"})
        with self.assertRaises(ArtifactError):
            replay(self.root, "run-1")

    def test_nonfinite_json_rejected(self):
        (self.root / "catalog.json").write_text('{"schema":"afterlight.catalog.v1","runs":[],"bad":NaN}', encoding="utf-8")
        with self.assertRaises(ArtifactError):
            catalog(self.root)

    def test_invalid_catalog_rejected(self):
        self.write("catalog.json", {"runs": []})
        with self.assertRaises(ArtifactError):
            catalog(self.root)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Path(self.temp.name)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_rejects_rebound_host(self):
        request = Request(self.base + "/api/health", headers={"Host": "untrusted.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)

    def test_health_and_empty_catalog(self):
        with urlopen(self.base + "/api/health", timeout=3) as response:
            data = json.load(response)
            self.assertFalse(data["generation_available"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        with urlopen(self.base + "/api/catalog", timeout=3) as response:
            self.assertEqual(json.load(response)["runs"], [])

    def test_local_cors_is_exact_and_external_is_absent(self):
        for origin, allowed in (("http://127.0.0.1:5173", True), ("https://example.com", False)):
            request = Request(self.base + "/api/health", headers={"Origin": origin})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin if allowed else None)

    def test_generation_is_honestly_unavailable(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base + "/api/runs", data=b"{}", method="POST"), timeout=3)
        self.assertEqual(caught.exception.code, 501)
        self.assertFalse(json.load(caught.exception)["generation_available"])


class GenerationHTTPTests(unittest.TestCase):
    def setUp(self):
        class FakeJobs:
            submitted = 0
            def submit(self, body):
                self.submitted += 1
                return {"id": "unit-only", "status": "queued"}
        self.jobs = FakeJobs()
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Path(self.temp.name), self.jobs))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_external_origin_cannot_start_job(self):
        request = Request(self.base + "/api/runs", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json", "Origin": "https://untrusted.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.jobs.submitted, 0)

    def test_local_json_request_gets_actual_job_identifier(self):
        request = Request(self.base + "/api/runs", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"})
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 202)
            self.assertEqual(json.load(response)["id"], "unit-only")
        self.assertEqual(self.jobs.submitted, 1)

    def test_nonfinite_or_nonjson_body_rejected(self):
        for body in (b'{"bad":Infinity}', b'not json'):
            request = Request(self.base + "/api/runs", data=body, method="POST", headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.jobs.submitted, 0)


if __name__ == "__main__":
    unittest.main()
