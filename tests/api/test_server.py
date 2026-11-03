"""Local artifact boundary tests; execute on the Omen acceptance machine."""
import json
import hashlib
import gzip
import tempfile
import unittest
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch
from api.server import ArtifactError, catalog, replay, replay_bytes, make_handler, local_origin, validated_replay_bytes


def synthetic_replay():
    # Explicit unit fixture, never a public recording or traffic result.
    return {"schema": "afterlight.replay.v1", "mode": "recorded", "duration_s": 1, "step_s": 1,
            "coordinates": {"position_reference": "front_bumper", "source": "canonical XY meters", "render": "[x,z,-y]"}, "scenario": {"network_kind": "fixture", "id": "unit-only", "seed": 7, "dispatch_s": 0, "pickup_id": "FIXTURE_PICKUP", "hospital_id": "FIXTURE_HOSPITAL"},
            "provenance": dict(source_commit="fixture", network_sha256="a"*64, demand_sha256="b"*64, sumo_version="fixture"),
            "worlds": {w: {"world_id": w, "status": "completed", "policy": "ordinary" if w == "baseline" else "fixed",
                           "metrics": {}, "events": [], "frames": [{"t": 0, "vehicles": [], "signals": [], "queue_count": 0}, {"t": 1, "vehicles": [], "signals": [], "queue_count": 0}]} for w in ("baseline", "afterlight")}}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def test_gzip_catalog_returns_exact_original_bytes_with_both_hashes_bound(self):
        payload=(json.dumps(synthetic_replay(),indent=2)+'\n').encode()
        encoded=gzip.compress(payload,mtime=0)
        (self.root/'packed.json.gz').write_bytes(encoded)
        row={'id':'packed','url':'packed.json.gz','bytes':len(payload),
             'sha256':hashlib.sha256(payload).hexdigest(),'transfer_bytes':len(encoded),
             'transfer_sha256':hashlib.sha256(encoded).hexdigest()}
        self.write('catalog.json',{'schema':'afterlight.catalog.v1','runs':[row]})
        self.assertEqual(replay_bytes(self.root,'packed'),payload)
        row['transfer_sha256']='0'*64
        self.write('catalog.json',{'schema':'afterlight.catalog.v1','runs':[row]})
        with self.assertRaisesRegex(ArtifactError,'transfer.*hash'):replay_bytes(self.root,'packed')

    def test_gzip_decode_is_bounded_and_corruption_is_a_controlled_error(self):
        path=self.root/'packed.json.gz'
        path.write_bytes(gzip.compress(b'x'*1000,mtime=0))
        with patch('api.server.MAX_REPLAY_BYTES',64),self.assertRaisesRegex(ArtifactError,'Decoded.*size limit'):
            validated_replay_bytes(path)
        path.write_bytes(b'not gzip')
        with self.assertRaisesRegex(ArtifactError,'gzip stream is corrupt'):validated_replay_bytes(path)

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

    def test_prettyprinted_replay_http_preserves_declared_exact_bytes(self):
        root=Path(self.temp.name)
        payload=(json.dumps(synthetic_replay(),indent=2)+'\n').encode()
        expected_hash=hashlib.sha256(payload).hexdigest()
        (root/'pretty.json').write_bytes(payload)
        (root/'catalog.json').write_text(json.dumps({'schema':'afterlight.catalog.v1','runs':[
            {'id':'pretty','sha256':expected_hash,'bytes':len(payload)}]}))
        request=Request(self.base+'/api/runs/pretty',headers={'Origin':'http://localhost:5173'})
        with urlopen(request,timeout=3) as response:
            actual=response.read()
            self.assertEqual(actual,payload)
            self.assertEqual(hashlib.sha256(actual).hexdigest(),expected_hash)
            self.assertEqual(int(response.headers['Content-Length']),len(payload))
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(response.headers['Access-Control-Allow-Origin'],'http://localhost:5173')

    def test_wrong_catalog_hash_or_length_is_http_422(self):
        root=Path(self.temp.name);payload=json.dumps(synthetic_replay(),indent=2).encode()
        (root/'bound.json').write_bytes(payload)
        for extra in ({'sha256':'0'*64},{'bytes':len(payload)+1}):
            (root/'catalog.json').write_text(json.dumps({'schema':'afterlight.catalog.v1','runs':[{'id':'bound',**extra}]}))
            with self.subTest(binding=extra),self.assertRaises(HTTPError) as caught:
                urlopen(self.base+'/api/runs/bound',timeout=3)
            self.assertEqual(caught.exception.code,422)
            self.assertEqual((root/'bound.json').read_bytes(),payload)

    def test_complete_looking_malformed_replays_are_http_422_before_serving(self):
        root=Path(self.temp.name)
        mutations=[lambda r:r.update(duration_s=True),
                   lambda r:r['worlds']['afterlight'].pop('metrics'),
                   lambda r:r['worlds']['afterlight'].update(metrics=[]),
                   lambda r:r['worlds']['afterlight'].pop('events'),
                   lambda r:r['worlds']['afterlight']['frames'][0].pop('signals'),
                   lambda r:r['worlds']['afterlight']['frames'][0].update(queue_count=False),
                   lambda r:r['worlds']['afterlight']['frames'][0].update(signals=[{'id':'J','state':'?'}]),
                   lambda r:r['worlds']['afterlight']['frames'][0].update(vehicles=[
                       dict(id='ambulance',type='ambulance',x=0,y=0,z=0,angle_deg=0,speed_mps=0,length_m=5),
                       dict(id='second',type='ambulance',x=1,y=1,z=0,angle_deg=0,speed_mps=0,length_m=5)])]
        for index,mutate in enumerate(mutations):
            data=synthetic_replay();mutate(data)
            payload=json.dumps(data).encode()
            (root/'malformed.json').write_bytes(payload)
            # Even correct catalog bytes/hash cannot replace schema validation.
            (root/'catalog.json').write_text(json.dumps({'schema':'afterlight.catalog.v1','runs':[
                {'id':'malformed','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]}))
            with self.subTest(mutation=index),self.assertRaises(HTTPError) as caught:
                urlopen(self.base+'/api/runs/malformed',timeout=3)
            self.assertEqual(caught.exception.code,422)
            self.assertIn('replay validation',json.load(caught.exception)['error'])
            self.assertEqual((root/'malformed.json').read_bytes(),payload)

    def test_catalog_numeric_overflow_and_depth_are_http_422(self):
        root=Path(self.temp.name)
        prefix=b'{"schema":"afterlight.catalog.v1","runs":[],"extra":'
        for value in (b'{"nested":1e309}',b'[-1e309]',b'['*2000+b'0'+b']'*2000):
            (root/'catalog.json').write_bytes(prefix+value+b'}')
            with self.assertRaises(HTTPError) as caught:urlopen(self.base+'/api/catalog',timeout=3)
            self.assertEqual(caught.exception.code,422)

    def test_replay_integer_overflow_is_http_422_not_handler_failure(self):
        root=Path(self.temp.name);data=synthetic_replay();data['duration_s']=10**1000
        (root/'overflow.json').write_text(json.dumps(data))
        (root/'catalog.json').write_text(json.dumps({'schema':'afterlight.catalog.v1','runs':[{'id':'overflow'}]}))
        with self.assertRaises(HTTPError) as caught:urlopen(self.base+'/api/runs/overflow',timeout=3)
        self.assertEqual(caught.exception.code,422)

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

    def test_job_http_serves_verified_bytes_without_reserializing_or_rereading_path(self):
        expected=synthetic_replay()
        payload=json.dumps(expected,indent=2).encode()
        self.jobs.get=lambda identifier:{'id':identifier,'status':'completed'}
        calls=[]
        def data(identifier):calls.append(identifier);return payload
        self.jobs.replay_bytes=data
        self.jobs.replay_path=lambda identifier:self.fail('HTTP must not reread a separately checked path')
        with urlopen(self.base+'/api/jobs/unit-only/replay',timeout=3) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(int(response.headers['Content-Length']),len(payload))
            self.assertEqual(response.read(),payload)
        self.assertEqual(calls,['unit-only'])

    def test_generated_metadata_serialization_errors_are_controlled_422(self):
        deep=[]
        for _ in range(2000):deep=[deep]
        for value in (float('inf'),object(),deep):
            self.jobs.get=lambda identifier,value=value:{'id':identifier,'status':'failed','extra':value}
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base+'/api/jobs/unit-only',timeout=3)
            self.assertEqual(caught.exception.code,422)
            self.assertIn('safely serialized',json.load(caught.exception)['error'])

    def test_nonfinite_or_nonjson_body_rejected(self):
        for body in (b'{"bad":Infinity}', b'not json', b'{"nested":{"x":1e309}}', b'{"nested":[-1e309]}', b'{"deep":'+b'['*2000+b'0'+b']'*2000+b'}'):
            request = Request(self.base + "/api/runs", data=body, method="POST", headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.jobs.submitted, 0)


if __name__ == "__main__":
    unittest.main()
