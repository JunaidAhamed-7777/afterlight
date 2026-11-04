"""Synthetic cancellation protocol checks; no SUMO or cloud storage requests."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from api import cancel, simulate
from cloud import cancellation
from sim.control import RunControl, SimulationCancelled
from tests.api.test_cloud_transport import BODY, Exchange, Fixture


TOKEN = "vercel_blob_rw_UnitPrivateStore_UnitSecret123"
REQUEST_ID = "a" * 32


class StoreTests(unittest.TestCase):
    def test_only_explicit_prefixed_private_credential_is_used(self):
        for environment in ({}, {"BLOB_READ_WRITE_TOKEN": TOKEN}, {cancellation.TOKEN_ENV: "not-a-blob-token"}):
            with self.subTest(environment=list(environment)), patch.dict("os.environ", environment, clear=True):
                with self.assertRaises(cancellation.CancellationUnavailable):
                    cancellation.CancellationStore.from_environment()
        with patch.dict("os.environ", {cancellation.TOKEN_ENV: TOKEN, "BLOB_READ_WRITE_TOKEN": "wrong"}, clear=True):
            store = cancellation.CancellationStore.from_environment()
        self.assertEqual(store._host, "unitprivatestore.private.blob.vercel-storage.com")

    def test_hmac_names_are_stable_scoped_and_never_expose_capability_or_token(self):
        store = cancellation.CancellationStore(TOKEN)
        name = store.pathname(REQUEST_ID)
        self.assertEqual(name, store.pathname(REQUEST_ID))
        self.assertNotEqual(name, store.pathname("b" * 32))
        self.assertNotEqual(name, cancellation.CancellationStore(TOKEN + "changed").pathname(REQUEST_ID))
        self.assertNotIn(REQUEST_ID, name)
        self.assertNotIn(TOKEN, name)
        for value in (None, 12, "A" * 32, "a" * 31, "../" + "a" * 32):
            with self.assertRaises(ValueError):
                store.pathname(value)

    def test_private_reads_bypass_cache_and_only404_means_not_cancelled(self):
        store = cancellation.CancellationStore(TOKEN)
        with patch.object(store, "_request", return_value=(404, b"not found")) as request:
            self.assertFalse(store.is_cancelled(REQUEST_ID))
        args, kwargs = request.call_args
        self.assertEqual(args[0], store._host)
        self.assertEqual(args[1], "GET")
        self.assertTrue(args[2].endswith("?cache=0"))
        self.assertIn("no-store", kwargs["headers"]["cache-control"])
        with patch.object(store, "_request", return_value=(200, cancellation.MARKER)):
            self.assertTrue(store.is_cancelled(REQUEST_ID))
        for status, body in ((200, b"wrong"), (401, b"private"), (403, b"quota"), (429, b"limit"), (302, b""), (500, b"error")):
            with self.subTest(status=status), patch.object(store, "_request", return_value=(status, body)):
                with self.assertRaises(cancellation.CancellationUnavailable):
                    store.is_cancelled(REQUEST_ID)

    def test_put_ack_requires_exact_private_path_and_uses_no_random_suffix(self):
        store = cancellation.CancellationStore(TOKEN)
        name = store.pathname(REQUEST_ID)
        payload = json.dumps({"pathname": name, "url": "https://" + store._host + "/" + name}).encode()
        with patch.object(store, "_request", return_value=(200, payload)) as request:
            store.request_cancel(REQUEST_ID)
        args = request.call_args.args
        self.assertEqual(args[:2], ("vercel.com", "PUT"))
        self.assertTrue(args[2].startswith("/api/blob/?pathname="))
        self.assertEqual(args[3], cancellation.MARKER)
        self.assertEqual(args[4]["x-vercel-blob-access"], "private")
        self.assertEqual(args[4]["x-add-random-suffix"], "0")
        self.assertEqual(args[4]["x-allow-overwrite"], "1")
        self.assertEqual(args[4]["x-api-version"], "12")
        for status, data in ((403, payload), (200, b"not json"), (200, b"[]"),
                             (200, json.dumps({"pathname": name, "url": "https://wrong.test/" + name}).encode())):
            with self.subTest(status=status, data=data[:20]), patch.object(store, "_request", return_value=(status, data)):
                with self.assertRaises(cancellation.CancellationUnavailable):
                    store.request_cancel(REQUEST_ID)

    def test_delete_is_limited_to_this_request_private_marker(self):
        store = cancellation.CancellationStore(TOKEN)
        with patch.object(store, "_request", return_value=(200, b"{}")) as request:
            store.remove(REQUEST_ID)
        args = request.call_args.args
        self.assertEqual(args[:3], ("vercel.com", "POST", "/api/blob/delete"))
        self.assertEqual(json.loads(args[3]), {"urls": ["https://" + store._host + "/" + store.pathname(REQUEST_ID)]})

    def test_http_auth_is_bounded_and_redirects_are_not_followed(self):
        store = cancellation.CancellationStore(TOKEN)
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status, response.read.return_value = 302, b"moved"
        with patch.object(cancellation.http.client, "HTTPSConnection", return_value=connection) as constructor:
            self.assertEqual(store._request(store._host, "GET", "/known?cache=0"), (302, b"moved"))
        constructor.assert_called_once_with(store._host, timeout=2)
        self.assertEqual(connection.request.call_args.kwargs["headers"]["authorization"], "Bearer " + TOKEN)
        response.read.assert_called_once_with(cancellation.RESPONSE_BYTES + 1)
        connection.close.assert_called_once()
        response.read.return_value = b"x" * (cancellation.RESPONSE_BYTES + 1)
        with patch.object(cancellation.http.client, "HTTPSConnection", return_value=connection):
            with self.assertRaises(cancellation.CancellationUnavailable):
                store._request(store._host, "GET", "/known")


class WatchTests(unittest.TestCase):
    def test_preexisting_cancel_prevents_work_and_cleans_unique_marker(self):
        store, control, notify = MagicMock(), RunControl(), MagicMock()
        store.is_cancelled.return_value = True
        with self.assertRaises(SimulationCancelled):
            with cancellation.CancellationWatch(store, REQUEST_ID, control, notify):
                self.fail("A pre-cancelled run reached work")
        self.assertTrue(control.cancel_event.is_set())
        notify.assert_called_once_with("cancelled")
        store.remove.assert_called_once_with(REQUEST_ID)
        control.close()

    def test_channel_error_cancels_before_work_and_is_not_mislabelled_user_cancel(self):
        store, control, notify = MagicMock(), RunControl(), MagicMock()
        store.is_cancelled.side_effect = cancellation.CancellationUnavailable("auth/quota/network")
        with self.assertRaises(SimulationCancelled):
            with cancellation.CancellationWatch(store, REQUEST_ID, control, notify):
                self.fail("A run without its Stop channel reached work")
        notify.assert_called_once_with("cancellation_unavailable")
        store.remove.assert_not_called()
        control.close()

    def test_poll_detects_new_cancel_then_joins_before_context_returns(self):
        store, control = MagicMock(), RunControl()
        detected = threading.Event()
        store.is_cancelled.side_effect = [False, True]
        def notify(reason):
            self.assertEqual(reason, "cancelled")
            detected.set()
        with patch.object(cancellation, "POLL_SECONDS", .005):
            with cancellation.CancellationWatch(store, REQUEST_ID, control, notify) as watch:
                self.assertTrue(detected.wait(1))
            self.assertFalse(watch.thread.is_alive())
        self.assertTrue(control.cancel_event.is_set())
        store.remove.assert_called_once()
        control.close()

    def test_success_joins_poll_thread_without_deleting_uncreated_marker(self):
        store, control = MagicMock(), RunControl()
        store.is_cancelled.return_value = False
        with cancellation.CancellationWatch(store, REQUEST_ID, control, lambda _: self.fail("Unexpected cancel")) as watch:
            pass
        self.assertFalse(watch.thread.is_alive())
        store.remove.assert_not_called()
        control.close()


class CancelEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def run_request(self, **kwargs):
        request = Exchange(body={"request_id": REQUEST_ID}, **kwargs)
        await cancel.app(request.scope, request.receive, request.send)
        return request

    async def test_acknowledgement_after_successful_marker_write_only(self):
        store = MagicMock()
        store.request_cancel.side_effect = lambda value: self.assertEqual(value, REQUEST_ID)
        with patch.object(cancel.CancellationStore, "from_environment", return_value=store):
            response = await self.run_request()
        self.assertEqual(response.status, 202)
        self.assertEqual(response.rows, [{"request_id": REQUEST_ID, "cancel_requested": True}])
        store.request_cancel.assert_called_once_with(REQUEST_ID)
        self.assertNotIn("stopped", json.dumps(response.rows))

    async def test_storage_errors_are_retryable_unconfirmed_without_secret_detail(self):
        store = MagicMock()
        store.request_cancel.side_effect = cancellation.CancellationUnavailable("secret private path")
        with patch.object(cancel.CancellationStore, "from_environment", return_value=store):
            response = await self.run_request()
        self.assertEqual(response.status, 503)
        self.assertNotIn("cancel_requested", response.rows[0])
        self.assertNotIn("secret", json.dumps(response.rows))

    async def test_strict_body_origin_type_and_size_guards_never_write(self):
        invalid = [b"{}", b"null", b"[]", b"{", b'{"request_id":"' + b"a" * 32 + b'","pickup":"P001"}',
                   b'{"request_id":"' + b"A" * 32 + b'"}',
                   b'{"request_id":"' + b"a" * 32 + b'","request_id":"' + b"a" * 32 + b'"}']
        with patch.object(cancel.CancellationStore, "from_environment") as factory:
            for raw in invalid:
                with self.subTest(raw=raw[:40]):
                    self.assertEqual((await self.run_request(raw=raw)).status, 400)
            self.assertEqual((await self.run_request(origin="https://wrong.test")).status, 403)
            self.assertEqual((await self.run_request(raw=b" " * 4097)).status, 413)
            self.assertEqual((await self.run_request(method="GET")).status, 405)
        factory.assert_not_called()


class SharedTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_marker_cancel_emits_cancelled_only_after_worker_cleanup(self):
        flag = threading.Event()
        store = MagicMock()
        store.is_cancelled.side_effect = lambda _: flag.is_set()
        fixture = Fixture(block=True)
        async def send(message):
            if b'"type":"cancelled"' in message.get("body", b""):
                self.assertTrue(fixture.cleaned.is_set())
        request = Exchange(on_send=send)
        with patch.object(simulate.CancellationStore, "from_environment", return_value=store), \
             patch.object(simulate, "run_cloud_simulation", fixture), patch.object(cancellation, "POLL_SECONDS", .005):
            task = asyncio.create_task(request.run())
            self.assertTrue(await asyncio.to_thread(fixture.entered.wait, 2))
            flag.set()
            await asyncio.wait_for(task, 3)
        self.assertEqual(request.rows[-1], {"type": "cancelled", "request_id": REQUEST_ID})
        self.assertNotIn("complete", [row["type"] for row in request.rows])
        self.assertTrue(fixture.cleaned.is_set())
        store.remove.assert_called_once_with(REQUEST_ID)
        self.assertTrue(simulate.ACTIVE.acquire(blocking=False))
        simulate.ACTIVE.release()

    async def test_marker_channel_failure_stops_run_with_explicit_error(self):
        store = MagicMock()
        store.is_cancelled.side_effect = cancellation.CancellationUnavailable("private quota")
        with patch.object(simulate.CancellationStore, "from_environment", return_value=store), patch.object(simulate, "run_cloud_simulation") as runner:
            response = await Exchange().run()
        runner.assert_not_called()
        self.assertEqual(response.rows[-1]["type"], "error")
        self.assertEqual(response.rows[-1]["code"], "cancellation_unavailable")
        self.assertNotIn("private quota", json.dumps(response.rows))

    async def test_missing_configuration_prevents_acceptance_and_all_simulation(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(simulate, "run_cloud_simulation") as runner:
            health = await Exchange(method="GET", origin=None).run()
            response = await Exchange().run()
        self.assertFalse(health.rows[0]["generation_supported"])
        self.assertEqual(response.status, 503)
        self.assertNotIn("accepted", [row.get("type") for row in response.rows])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
