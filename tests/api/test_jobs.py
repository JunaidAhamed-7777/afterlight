"""Synthetic job lifecycle tests; never starts SUMO or publishes sample data."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from api.jobs import JobManager, RequestError, OutputConflict, parameters


def synthetic_replay():
    return {"schema": "afterlight.replay.v1", "mode": "recorded", "duration_s": 1, "step_s": 1,
            "coordinates": {"position_reference": "front_bumper"}, "scenario": {"network_kind": "fixture"},
            "provenance": dict(source_commit="fixture", network_sha256="fixture", demand_sha256="fixture", sumo_version="fixture"),
            "worlds": {w: {"world_id": w, "status": "completed", "policy": "ordinary" if w == "baseline" else "fixed",
                           "frames": [{"t": 0, "vehicles": []}, {"t": 1, "vehicles": []}]} for w in ("baseline", "afterlight")}}


class JobTests(unittest.TestCase):
    def test_parameter_allowlist_and_route_membership(self):
        self.assertEqual(parameters({"network": "fixture"})["seed"], 7)
        for value in ({"output": "../private"}, {"seed": True}, {"seed": -1}, {"policy": "invented"},
                      {"pickup": "NOT_A_PICKUP"}, {"lead": 12}, {"network": "external"}):
            with self.assertRaises(RequestError):
                parameters(value)

    def test_idempotent_request_is_not_started_twice(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def runner(args):
            calls.append(args)
            entered.set()
            release.wait(timeout=3)
            raise RuntimeError("unit-only terminal failure")
        request_id = "a" * 32
        body = {"network": "fixture", "request_id": request_id}
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), runner)
            try:
                first = manager.submit(body)
                self.assertTrue(entered.wait(timeout=2))
                second = manager.submit(body)
                self.assertEqual(first["id"], second["id"])
                with self.assertRaises(RequestError):
                    manager.submit({**body, "seed": 8})
                release.set()
                manager.close()
                self.assertEqual(len(calls), 1)
                recovered = JobManager(Path(root), lambda args: self.fail("must not rerun persisted request"))
                try:
                    self.assertEqual(recovered.get(request_id)["status"], "failed")
                    self.assertEqual(recovered.submit(body)["id"], request_id)
                finally:
                    recovered.close()
            finally:
                release.set()
                manager.close()

    def test_one_job_limit_and_genuine_artifact_gate(self):
        entered, release = threading.Event(), threading.Event()
        def runner(args):
            entered.set()
            release.wait(timeout=3)
            args.output.mkdir(parents=True)
            (args.output / "replay.json").write_text(json.dumps(synthetic_replay()), encoding="utf-8")
            return {"scenario_id": "unit-fixture"}
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), runner)
            try:
                job = manager.submit({"network": "fixture"})
                self.assertTrue(entered.wait(timeout=2))
                with self.assertRaises(RequestError):
                    manager.submit({"network": "fixture"})
                self.assertIsNone(manager.replay_path(job["id"]))
                release.set()
                manager.close()
                self.assertEqual(manager.get(job["id"])["status"], "completed")
                self.assertTrue(manager.replay_path(job["id"]).is_file())
                self.assertIsNone(manager.get("../unknown"))
            finally:
                release.set()
                manager.close()

    def test_rejects_preexisting_job_directory_without_touching_it(self):
        with tempfile.TemporaryDirectory() as root:
            existing = Path(root) / "reserved"
            existing.mkdir()
            (existing / "keep.txt").write_text("unchanged", encoding="utf-8")
            manager = JobManager(Path(root), lambda args: self.fail("runner must not start"))
            with patch("api.jobs.uuid4", return_value=SimpleNamespace(hex="reserved")):
                job = manager.submit({"network": "fixture"})
            manager.close()
            self.assertEqual(manager.get(job["id"])["status"], "failed")
            self.assertEqual(sorted(p.name for p in existing.iterdir()), ["keep.txt"])

    def test_runner_output_ownership_race_preserves_existing_files(self):
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output / "other-owner.txt").write_text("keep", encoding="utf-8")
            raise OutputConflict("concurrent creation")
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), runner)
            job = manager.submit({"network": "fixture"})
            manager.close()
            self.assertEqual(manager.get(job["id"])["status"], "failed")
            self.assertEqual(sorted(p.name for p in (Path(root) / job["id"]).iterdir()), ["other-owner.txt"])

    def test_persistence_failure_does_not_report_completed(self):
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output / "replay.json").write_text(json.dumps(synthetic_replay()), encoding="utf-8")
            return {"scenario_id": "unit-fixture"}
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), runner)
            with patch("api.jobs.os.fsync", side_effect=OSError("fixture disk failure")):
                job = manager.submit({"network": "fixture"})
                manager.close()
            self.assertEqual(manager.get(job["id"])["status"], "failed")
            self.assertIn("persistence_error", manager.get(job["id"]))
            self.assertIsNone(manager.replay_path(job["id"]))

    def test_corrupt_persisted_record_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as root:
            job_id = "b" * 32
            folder = Path(root) / job_id
            folder.mkdir()
            (folder / "job.json").write_text("[]", encoding="utf-8")
            manager = JobManager(Path(root))
            try:
                self.assertIsNone(manager.get(job_id))
                record = {"id": job_id, "status": "completed", "parameters": parameters({"network": "fixture"})}
                (folder / "job.json").write_text(json.dumps(record), encoding="utf-8")
                recovered = manager.get(job_id)
                self.assertEqual(recovered["status"], "failed")
                self.assertIn("recovery_error", recovered)
                self.assertIsNone(manager.replay_path(job_id))
                self.assertEqual(json.loads((folder / "job.json").read_text())["status"], "completed")
            finally:
                manager.close()

    def test_runner_failure_retained_not_fabricated(self):
        def runner(args):
            raise RuntimeError("unit fixture failure")
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), runner)
            job = manager.submit({"network": "fixture"})
            manager.close()
            actual = manager.get(job["id"])
            self.assertEqual(actual["status"], "failed")
            self.assertIn("unit fixture failure", actual["error"])
            self.assertIsNone(manager.replay_path(job["id"]))
            self.assertTrue((Path(root) / job["id"] / "job.json").is_file())


if __name__ == "__main__":
    unittest.main()
