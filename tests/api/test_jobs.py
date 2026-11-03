"""Synthetic job lifecycle tests; never starts SUMO or publishes sample data."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from api.jobs import JobManager, RequestError, OutputConflict, parameters, load_job_replay


def synthetic_replay():
    return {"schema": "afterlight.replay.v1", "mode": "recorded", "duration_s": 1, "step_s": 1,
            "coordinates": {"position_reference": "front_bumper", "source": "canonical XY meters", "render": "[x,z,-y]"}, "scenario": {"network_kind": "fixture", "id": "unit-only", "seed": 7, "dispatch_s": 0, "pickup_id": "FIXTURE_PICKUP", "hospital_id": "FIXTURE_HOSPITAL", "regime": "moderate"},
            "provenance": dict(source_commit="fixture", network_sha256="a"*64, demand_sha256="b"*64, sumo_version="fixture"),
            "worlds": {w: {"world_id": w, "status": "completed", "policy": "ordinary" if w == "baseline" else "fixed", "lead_s": 10,
                           "metrics": {}, "events": [], "frames": [{"t": 0, "vehicles": [], "signals": [], "queue_count": 0}, {"t": 1, "vehicles": [], "signals": [], "queue_count": 0}]} for w in ("baseline", "afterlight")}}


class JobTests(unittest.TestCase):
    def test_city_job_uses_expanded_network_drain_without_changing_fixture(self):
        for network, expected in [('city', (360.0, 540.0, 2.0)), ('fixture', (240.0, 360.0, 1.0))]:
            calls = []
            def runner(args):
                calls.append(args)
                raise RuntimeError('unit-only protocol capture; no SUMO execution')
            with tempfile.TemporaryDirectory() as root:
                manager = JobManager(Path(root), runner)
                manager.submit({'network': network})
                manager.close()
                self.assertEqual(len(calls), 1)
                args = calls[0]
                self.assertEqual((args.horizon, args.drain, args.sample), expected)
                self.assertEqual((args.dispatch, args.demand_end, args.step), (60.0, 180.0, .5))

    def test_recovery_rejects_deterministically_overdeep_persisted_job(self):
        from api.artifacts import MAX_JSON_DEPTH
        with tempfile.TemporaryDirectory() as root:
            identifier='a'*32;directory=Path(root)/identifier;directory.mkdir()
            (directory/'job.json').write_bytes(b'{"extra":'+b'['*MAX_JSON_DEPTH+b'0'+b']'*MAX_JSON_DEPTH+b'}')
            manager=JobManager(Path(root),lambda args:self.fail('Recovery must never execute a world'))
            try:self.assertIsNone(manager.get(identifier))
            finally:manager.close()

    def test_source_change_requires_server_restart_before_new_work(self):
        current = {"source_commit": "initial", "source_code_sha256": "initial"}
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), lambda args: self.fail("stale source must not execute"),
                                 source_snapshot_fn=lambda: dict(current))
            try:
                current["source_code_sha256"] = "changed"
                with self.assertRaisesRegex(RequestError, "restart"):
                    manager.submit({"network": "fixture"})
                self.assertEqual(list(Path(root).iterdir()), [])
            finally:
                manager.close()

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

    def test_changed_replay_cannot_be_reused_as_same_job(self):
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output / "replay.json").write_text(json.dumps(synthetic_replay()), encoding="utf-8")
            return {"scenario_id": "unit-fixture"}
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root), runner)
            job = manager.submit({"network": "fixture"})
            manager.close()
            path = manager.replay_path(job["id"])
            data = json.loads(path.read_text())
            data["scenario"]["seed"] = 9
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertIsNone(manager.replay_path(job["id"]))
            self.assertEqual(manager.get(job["id"])["status"], "failed")

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

    def test_postrun_source_change_is_infrastructure_failure_with_raw_evidence(self):
        current={'source_commit':'initial','source_code_sha256':'initial'}
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output/'replay.json').write_text(json.dumps(synthetic_replay()))
            current['source_commit']='changed-during-run'
            return {'scenario_id':'unit-fixture'}
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(Path(root),runner,source_snapshot_fn=lambda:dict(current))
            job=manager.submit({'network':'fixture'});manager.close()
            actual=manager.get(job['id'])
            self.assertEqual(actual['status'],'failed')
            self.assertEqual(actual['failure_kind'],'infrastructure_source_changed')
            self.assertNotIn('replay_url',actual)
            self.assertTrue((Path(root)/job['id']/'replay.json').exists())
            self.assertEqual(json.loads((Path(root)/job['id']/'job.json').read_text())['status'],'failed')

    def test_source_change_during_artifact_validation_prevents_completion(self):
        current={'source_commit':'initial','source_code_sha256':'initial'}
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output/'replay.json').write_text(json.dumps(synthetic_replay()))
            return {'scenario_id':'unit-fixture'}
        def changed_after_validation(*args):
            result=load_job_replay(*args)
            current['source_code_sha256']='changed-during-validation'
            return result
        with tempfile.TemporaryDirectory() as root,patch('api.jobs.load_job_replay',side_effect=changed_after_validation):
            manager=JobManager(Path(root),runner,source_snapshot_fn=lambda:dict(current))
            job=manager.submit({'network':'fixture'});manager.close()
            self.assertEqual(manager.get(job['id'])['failure_kind'],'infrastructure_source_changed')
            self.assertNotIn('replay_url',manager.get(job['id']))

    def test_oversize_replay_cannot_be_completed(self):
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output/'replay.json').write_text(json.dumps(synthetic_replay()))
            return {'scenario_id':'unit-fixture'}
        with tempfile.TemporaryDirectory() as root,patch('api.artifacts.MAX_REPLAY_BYTES',100):
            manager=JobManager(Path(root),runner)
            job=manager.submit({'network':'fixture'});manager.close()
            actual=manager.get(job['id'])
            self.assertEqual(actual['status'],'failed')
            self.assertIn('size limit',actual['error'])
            self.assertTrue((Path(root)/job['id']/'replay.json').exists())

    def test_recovery_and_serving_use_the_same_size_cap(self):
        def runner(args):
            args.output.mkdir(parents=True)
            (args.output/'replay.json').write_text(json.dumps(synthetic_replay()))
            return {'scenario_id':'unit-fixture'}
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(Path(root),runner)
            job=manager.submit({'network':'fixture'});manager.close()
            self.assertEqual(manager.get(job['id'])['status'],'completed')
            recovered=JobManager(Path(root),runner)
            try:
                with patch('api.artifacts.MAX_REPLAY_BYTES',100):
                    self.assertIsNone(manager.replay_data(job['id']))
                    self.assertEqual(manager.get(job['id'])['failure_kind'],'artifact_integrity')
                    self.assertEqual(recovered.get(job['id'])['status'],'failed')
            finally:recovered.close()

    def test_verified_response_uses_exact_bytes_hashed_not_a_second_read(self):
        import hashlib
        from api.artifacts import read_bytes
        expected=synthetic_replay()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'replay.json';path.write_text(json.dumps(expected))
            original=path.read_bytes();expected_hash=hashlib.sha256(original).hexdigest()
            def read_then_change(target):
                payload=read_bytes(target)
                altered=synthetic_replay();altered['scenario']['seed']=999
                target.write_text(json.dumps(altered))
                return payload
            with patch('api.jobs.read_bytes',side_effect=read_then_change) as reader:
                data,actual_hash=load_job_replay(path,parameters({'network':'fixture'}),expected_hash)
            self.assertEqual(reader.call_count,1)
            self.assertEqual(data,expected);self.assertEqual(actual_hash,expected_hash)
            self.assertEqual(json.loads(path.read_text())['scenario']['seed'],999)

    def test_unbounded_numeric_duration_is_controlled_artifact_failure(self):
        from api.artifacts import ArtifactError
        data=synthetic_replay();data['duration_s']=10**1000
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'huge-integer.json';path.write_text(json.dumps(data))
            with self.assertRaises(ArtifactError):load_job_replay(path,parameters({'network':'fixture'}))

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
