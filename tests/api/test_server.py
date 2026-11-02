"""Local artifact boundary tests; execute on the Omen acceptance machine."""
import json
import tempfile
import unittest
from pathlib import Path
from api.server import ArtifactError, catalog, replay


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

    def test_invalid_catalog_rejected(self):
        self.write("catalog.json", {"runs": []})
        with self.assertRaises(ArtifactError):
            catalog(self.root)


if __name__ == "__main__":
    unittest.main()
