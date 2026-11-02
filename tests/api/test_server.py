"""Local artifact boundary tests; execute on the Omen acceptance machine."""
import json
import tempfile
import unittest
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from pathlib import Path
from api.server import ArtifactError, catalog, replay, make_handler


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

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
        self.write("run-1.json", {"schema": "afterlight.replay.v1", "mode": "recorded"})
        self.assertEqual(replay(self.root, "run-1")["mode"], "recorded")
        self.write("run-1.json", {"schema": "afterlight.replay.v1", "mode": "live"})
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

    def test_health_and_empty_catalog(self):
        with urlopen(self.base + "/api/health", timeout=3) as response:
            data = json.load(response)
            self.assertFalse(data["generation_available"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        with urlopen(self.base + "/api/catalog", timeout=3) as response:
            self.assertEqual(json.load(response)["runs"], [])

    def test_generation_is_honestly_unavailable(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base + "/api/runs", data=b"{}", method="POST"), timeout=3)
        self.assertEqual(caught.exception.code, 501)
        self.assertFalse(json.load(caught.exception)["generation_available"])


if __name__ == "__main__":
    unittest.main()
