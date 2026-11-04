"""Synthetic ASGI transport checks; no SUMO, traffic outcomes or cloud requests.

The opaque gzip fixture tests wire integrity, not replay/scientific validity.
Real runner/route/physics correctness belongs to the separate engine checks.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager, nullcontext
import gzip
import hashlib
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from unittest.mock import patch

from api import simulate
from sim.control import SimulationCancelled


BODY = {"request_id": "a" * 32, "pickup": "P001", "hospital": "HOSP_EAST"}


class Exchange:
    def __init__(self, body=None, *, raw=None, method="POST", origin="https://viewer.test", headers=None, on_send=None):
        self.incoming = asyncio.Queue()
        self.outgoing = []
        self.on_send = on_send
        if raw is None:
            raw = json.dumps(BODY if body is None else body).encode()
        self.raw = raw
        self.incoming.put_nowait({"type": "http.request", "body": raw, "more_body": False})
        values = [(b"host", b"viewer.test"), (b"content-type", b"application/json")]
        if origin is not None:
            values.append((b"origin", origin.encode()))
        self.scope = {"type": "http", "method": method, "path": "/api/simulate", "headers": values if headers is None else headers}

    async def receive(self):
        return await self.incoming.get()

    async def send(self, message):
        if self.on_send:
            await self.on_send(message)
        self.outgoing.append(message)

    async def run(self):
        await simulate.app(self.scope, self.receive, self.send)
        return self

    @property
    def status(self):
        return next(message["status"] for message in self.outgoing if message["type"] == "http.response.start")

    @property
    def rows(self):
        payload = b"".join(message.get("body", b"") for message in self.outgoing)
        return [json.loads(line) for line in payload.splitlines() if line]


class Fixture:
    def __init__(self, *, block=False, fail=None, burst=0, mutate=None, size=150000, queues=()):
        self.block, self.fail, self.burst, self.mutate = block, fail, burst, mutate
        self.entered = threading.Event()
        self.cleaned = threading.Event()
        self.calls = 0
        self.produced = 0
        self.raw = random.Random(77).randbytes(size)
        self.encoded = gzip.compress(self.raw, mtime=0)
        self.queues = queues

    @contextmanager
    def __call__(self, body, control):
        self.calls += 1
        self.control = control
        self.entered.set()
        try:
            with tempfile.TemporaryDirectory(prefix="afterlight-transport-unit-") as directory:
                path = Path(directory) / "unit-only.json.gz"
                path.write_bytes(self.encoded)
                control.progress("unit-transport", "Explicit synthetic transport fixture")
                if self.fail:
                    raise self.fail
                for queue in self.queues:
                    control.emit(queue)
                for index in range(self.burst):
                    self.produced += 1
                    control.progress("unit-backpressure", "Fixture event", completed_steps=index, total_steps=self.burst)
                while self.block:
                    control.cancel_event.wait(.005)
                    control.check_cancelled()
                control.emit({"type": "route", "route_edges": ["unit-edge"], "pickup": body["pickup"],
                              "hospital": body["hospital"], "canonical_map_sha256": "c" * 64,
                              "cost_m": 1, "cost_definition": "unit transport fixture only"})
                metadata = {"request_id": body["request_id"], "scenario_id": "synthetic-transport-only",
                    "gzip_path": path, "replay_path": Path(directory) / "never-served-unit.json",
                    "decoded_sha256": hashlib.sha256(self.raw).hexdigest(), "decoded_bytes": len(self.raw),
                    "compressed_sha256": hashlib.sha256(self.encoded).hexdigest(), "compressed_bytes": len(self.encoded),
                    "world_status": {"baseline": "completed", "afterlight": "completed"},
                    "source_commit": "unit-only", "interpretation": "Synthetic transport fixture; no traffic result"}
                if self.mutate:
                    self.mutate(metadata)
                yield metadata
        finally:
            control.close()
            self.cleaned.set()


class CloudTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Transport-only fixtures cannot make cloud calls. Shared-marker
        # integration and failure behavior have their own explicit checks.
        self.addCleanup(patch.stopall)
        patch.object(simulate.CancellationStore, "from_environment").start()
        patch.object(simulate, "CancellationWatch", side_effect=lambda *_: nullcontext()).start()

    async def wait_thread(self, event):
        self.assertTrue(await asyncio.to_thread(event.wait, 2), "Synthetic worker did not reach expected boundary")

    async def test_health_does_not_initialize_or_start_simulation(self):
        with patch.object(simulate, "run_cloud_simulation") as runner:
            response = await Exchange(method="GET", origin=None).run()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.rows[0]["transport"], "ndjson")
        self.assertEqual(response.rows[0]["deadline_s"], 270)
        runner.assert_not_called()

    async def test_stream_integrity_and_worker_cleanup_before_completion(self):
        fixture = Fixture()
        async def sent(message):
            # A bounded queue owns copied chunk bytes; the producer may close
            # its file/context while the network drains those queued copies.
            if b'"type":"complete"' in message.get("body", b""):
                self.assertTrue(fixture.cleaned.is_set(), "Complete advertised before cleanup")
        with patch.object(simulate, "run_cloud_simulation", fixture):
            response = await Exchange(on_send=sent).run()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.rows[0], {"type": "accepted", "request_id": BODY["request_id"]})
        self.assertTrue(any(row["type"] == "route" for row in response.rows))
        chunks = [row for row in response.rows if row["type"] == "replay_chunk"]
        self.assertEqual([row["index"] for row in chunks], list(range(len(chunks))))
        self.assertGreater(len(chunks), 1)
        blocks = [base64.b64decode(row["data"], validate=True) for row in chunks]
        self.assertTrue(all(0 < len(block) <= 65536 for block in blocks))
        encoded = b"".join(blocks)
        self.assertEqual(encoded, fixture.encoded)
        self.assertEqual(gzip.decompress(encoded), fixture.raw)
        complete = response.rows[-1]
        self.assertEqual(complete["type"], "complete")
        self.assertEqual(complete["chunks"], len(chunks))
        self.assertEqual(complete["compressed_sha256"], hashlib.sha256(encoded).hexdigest())
        self.assertEqual(complete["replay_sha256"], hashlib.sha256(fixture.raw).hexdigest())
        self.assertEqual(complete["decoded_bytes"], len(fixture.raw))
        self.assertFalse({"gzip_path", "replay_path", "decoded_sha256"} & set(complete))
        self.assertFalse(response.outgoing[-1]["more_body"])
        self.assertTrue(fixture.cleaned.is_set())

    async def test_disconnect_waits_for_owned_worker_cleanup_and_never_completes(self):
        fixture = Fixture(block=True)
        request = Exchange()
        with patch.object(simulate, "run_cloud_simulation", fixture):
            task = asyncio.create_task(request.run())
            await self.wait_thread(fixture.entered)
            await request.incoming.put({"type": "http.disconnect"})
            await asyncio.wait_for(task, 3)
        self.assertTrue(fixture.cleaned.is_set())
        self.assertTrue(fixture.control.cancel_event.is_set())
        self.assertNotIn("complete", [row["type"] for row in request.rows])

    async def test_actual_callback_queue_samples_forward_unchanged_with_world_time_and_count(self):
        samples = [{"type": "queue", "world_id": "baseline", "t": 60.5, "queue_count": 7},
                   {"type": "queue", "world_id": "baseline", "t": 61.0, "queue_count": 8},
                   {"type": "queue", "world_id": "afterlight", "t": 60.5, "queue_count": 3}]
        fixture = Fixture(queues=samples, size=100)
        with patch.object(simulate, "run_cloud_simulation", fixture):
            response = await Exchange().run()
        self.assertEqual([row for row in response.rows if row["type"] == "queue"], samples)
        self.assertEqual(response.rows[-1]["type"], "complete")

    async def test_ASGI_task_cancellation_cleans_worker_before_propagating(self):
        fixture = Fixture(block=True)
        with patch.object(simulate, "run_cloud_simulation", fixture):
            task = asyncio.create_task(Exchange().run())
            await self.wait_thread(fixture.entered)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(fixture.cleaned.is_set())
        self.assertTrue(simulate.ACTIVE.acquire(blocking=False))
        simulate.ACTIVE.release()

    async def test_slow_client_backpressure_is_bounded_and_disconnect_unblocks_producer(self):
        fixture = Fixture(burst=1000)
        stalled = asyncio.Event()
        async def slow(message):
            if b'"type":"progress"' in message.get("body", b""):
                stalled.set()
                await asyncio.Event().wait()
        request = Exchange(on_send=slow)
        with patch.object(simulate, "run_cloud_simulation", fixture):
            task = asyncio.create_task(request.run())
            await asyncio.wait_for(stalled.wait(), 2)
            await asyncio.sleep(.08)
            self.assertLessEqual(fixture.produced, simulate.QUEUE_ITEMS + 2)
            await request.incoming.put({"type": "http.disconnect"})
            await asyncio.wait_for(task, 3)
        self.assertTrue(fixture.cleaned.is_set())
        self.assertNotIn("complete", [row["type"] for row in request.rows])

    async def test_busy_instance_rejects_without_starting_another_worker_then_releases(self):
        fixture = Fixture(block=True)
        first = Exchange()
        with patch.object(simulate, "run_cloud_simulation", fixture):
            task = asyncio.create_task(first.run())
            await self.wait_thread(fixture.entered)
            busy = await Exchange().run()
            self.assertEqual(busy.status, 429)
            self.assertEqual(fixture.calls, 1)
            await first.incoming.put({"type": "http.disconnect"})
            await asyncio.wait_for(task, 3)
        next_fixture = Fixture(size=100)
        with patch.object(simulate, "run_cloud_simulation", next_fixture):
            next_response = await Exchange().run()
        self.assertEqual(next_response.rows[-1]["type"], "complete")

    async def test_deadline_cancels_and_cleans_before_sending_controlled_error(self):
        fixture = Fixture(block=True)
        async def check_cleanup(message):
            if b'"type":"error"' in message.get("body", b""):
                self.assertTrue(fixture.cleaned.is_set())
        with patch.object(simulate, "run_cloud_simulation", fixture), patch.object(simulate, "TOTAL_SECONDS", .15):
            response = await asyncio.wait_for(Exchange(on_send=check_cleanup).run(), 3)
        self.assertEqual(fixture.calls, 1)
        self.assertEqual(response.rows[-1]["code"], "deadline_exceeded")
        self.assertNotIn("complete", [row["type"] for row in response.rows])
        self.assertTrue(fixture.cleaned.is_set())

    async def test_worker_exception_is_not_exposed_as_a_traceback_or_local_path(self):
        fixture = Fixture(fail=RuntimeError("/private/token-secret/run/traces.py: sensitive detail"))
        with patch.object(simulate, "run_cloud_simulation", fixture), self.assertLogs(simulate.LOGGER, level="ERROR") as logs:
            response = await Exchange().run()
        server_log = "\n".join(logs.output)
        self.assertIn("request_hash=" + hashlib.sha256(BODY["request_id"].encode()).hexdigest()[:12], server_log)
        self.assertIn("phase=starting", server_log)
        self.assertIn("RuntimeError", server_log)
        self.assertNotIn(BODY["request_id"], server_log)
        self.assertNotIn('"pickup"', server_log)
        payload = json.dumps(response.rows)
        self.assertEqual(response.rows[-1]["code"], "simulation_failed")
        for forbidden in ("private", "token-secret", "traces.py", "RuntimeError", "Traceback"):
            self.assertNotIn(forbidden, payload)
        self.assertTrue(fixture.cleaned.is_set())

    async def test_changed_gzip_or_invalid_result_identity_never_gets_complete(self):
        for mutation in (lambda value: value.update(compressed_sha256="0" * 64),
                         lambda value: value.update(request_id="b" * 32),
                         lambda value: value.update(decoded_bytes=simulate.DECODED_BYTES + 1)):
            with self.subTest(mutation=mutation):
                fixture = Fixture(mutate=mutation, size=100)
                with patch.object(simulate, "run_cloud_simulation", fixture), self.assertLogs(simulate.LOGGER, level="ERROR"):
                    response = await Exchange().run()
                self.assertEqual(response.rows[-1]["code"], "simulation_failed")
                self.assertNotIn("complete", [row["type"] for row in response.rows])
                self.assertTrue(fixture.cleaned.is_set())

    async def test_send_disconnect_during_chunks_cancels_worker_and_context(self):
        fixture = Fixture()
        async def fail_send(message):
            if b'"type":"replay_chunk"' in message.get("body", b""):
                raise OSError("Client closed socket")
        with patch.object(simulate, "run_cloud_simulation", fixture):
            response = await Exchange(on_send=fail_send).run()
        self.assertTrue(fixture.cleaned.is_set())
        self.assertNotIn("complete", [row["type"] for row in response.rows])

    async def test_invalid_or_unsafe_requests_rejected_before_acceptance_or_worker(self):
        invalid = [b"", b"{", b"null", b"[]", b'"text"',
            json.dumps({**BODY, "command": "sumo"}).encode(),
            json.dumps({**BODY, "request_id": "A" * 32}).encode(),
            json.dumps({**BODY, "pickup": "P999"}).encode(),
            json.dumps({**BODY, "hospital": "unknown"}).encode(),
            json.dumps({**BODY, "pickup": 1}).encode(),
            b'{"request_id":"' + b"a" * 32 + b'","pickup":"P001","pickup":"P080","hospital":"HOSP_EAST"}',
            b'{"request_id":"' + b"a" * 32 + b'","pickup":1e400,"hospital":"HOSP_EAST"}',
            b"[" * 1500 + b"]" * 1500]
        with patch.object(simulate, "run_cloud_simulation") as runner:
            for raw in invalid:
                with self.subTest(raw=raw[:70]):
                    response = await Exchange(raw=raw).run()
                    self.assertEqual(response.status, 400)
                    self.assertNotIn("accepted", [row.get("type") for row in response.rows])
        runner.assert_not_called()

    async def test_missing_cross_origin_and_ambiguous_headers_rejected(self):
        with patch.object(simulate, "run_cloud_simulation") as runner:
            for origin in (None, "null", "https://other.test", "https://viewer.test.evil.test",
                           "https://user@viewer.test", "https://viewer.test/path", "https://viewer.test/",
                           "https:\n//viewer.test"):
                with self.subTest(origin=origin):
                    response = await Exchange(origin=origin).run()
                    self.assertEqual(response.status, 403)
            headers = [(b"host", b"viewer.test"), (b"origin", b"https://viewer.test"),
                       (b"origin", b"https://evil.test"), (b"content-type", b"application/json")]
            self.assertEqual((await Exchange(headers=headers).run()).status, 400)
        runner.assert_not_called()

    async def test_body_bound_type_and_method_guards_do_not_start_worker(self):
        with patch.object(simulate, "run_cloud_simulation") as runner:
            self.assertEqual((await Exchange(raw=b" " * (simulate.REQUEST_BYTES + 1)).run()).status, 413)
            headers = [(b"host", b"viewer.test"), (b"origin", b"https://viewer.test"),
                       (b"content-type", b"application/json"), (b"content-length", b"9999")]
            self.assertEqual((await Exchange(headers=headers).run()).status, 413)
            headers[-1] = (b"content-length", b"0")
            self.assertEqual((await Exchange(headers=headers).run()).status, 400)
            headers = [(key, b"text/plain" if key == b"content-type" else value) for key, value in headers if key != b"content-length"]
            self.assertEqual((await Exchange(headers=headers).run()).status, 415)
            self.assertEqual((await Exchange(method="DELETE").run()).status, 405)
        runner.assert_not_called()

    async def test_body_receive_timeout_and_early_disconnect_do_not_run(self):
        for event in (None, {"type": "http.disconnect"}):
            request = Exchange()
            request.incoming.get_nowait()
            if event:
                request.incoming.put_nowait(event)
            with patch.object(simulate, "run_cloud_simulation") as runner, patch.object(simulate, "REQUEST_READ_SECONDS", .01):
                await request.run()
                runner.assert_not_called()
            if event is None:
                self.assertEqual(request.status, 408)
            else:
                self.assertEqual(request.outgoing, [])


if __name__ == "__main__":
    unittest.main()
