"""Request-owned exploratory SUMO streaming endpoint for a hosted ASGI runtime.

The worker keeps the simulation context open through lossless gzip delivery.
Disconnects, deadlines and ASGI task cancellation signal only that worker's
RunControl, then await its child-process cleanup before releasing the slot.
There is no detached job, automatic retry, shared scientific output, or cache.
"""
from __future__ import annotations

import asyncio
import base64
from concurrent.futures import TimeoutError as FutureTimeout
from functools import lru_cache
import hashlib
import json
import logging
import math
import re
import threading
from urllib.parse import urlsplit

from sim.control import RunControl, SimulationCancelled
from cloud.cancellation import CancellationStore, CancellationUnavailable, CancellationWatch


REQUEST_BYTES = 4096
REQUEST_READ_SECONDS = 10
TOTAL_SECONDS = 270
CHUNK_BYTES = 64 * 1024
LINE_BYTES = 128 * 1024
WIRE_BYTES = 32 * 1024 * 1024
GZIP_BYTES = 20 * 1024 * 1024
DECODED_BYTES = 128 * 1024 * 1024
QUEUE_ITEMS = 8
ACTIVE = threading.BoundedSemaphore(1)
HEX64 = re.compile(r"[a-f0-9]{64}")
LOGGER = logging.getLogger(__name__)


def run_cloud_simulation(body, control):
    # Health requests do not import/initialize the simulator dependencies.
    from cloud.simulation import run_cloud_simulation as run
    return run(body, control)


def _line(value: dict) -> bytes:
    data = (json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > LINE_BYTES:
        raise ValueError("Stream event exceeds its transport bound")
    return data


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate request key")
        result[key] = value
    return result


def _finite(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("Nonfinite request number")
    return value


def _constant(_):
    raise ValueError("Nonfinite request token")


@lru_cache(maxsize=1)
def _anchors():
    from sim.network import load_graph
    graph = load_graph("city")
    return frozenset(p["id"] for p in graph["pickups"]), frozenset(h["id"] for h in graph["hospitals"])


def _request_body(raw: bytes) -> dict:
    body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant, parse_float=_finite)
    if not isinstance(body, dict) or set(body) != {"request_id", "pickup", "hospital"}:
        raise ValueError("Invalid request fields")
    if not isinstance(body["request_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", body["request_id"]):
        raise ValueError("Invalid request identifier")
    if not isinstance(body["pickup"], str) or not isinstance(body["hospital"], str):
        raise ValueError("Invalid anchor types")
    pickups, hospitals = _anchors()
    if body["pickup"] not in pickups or body["hospital"] not in hospitals:
        raise ValueError("Unknown canonical city anchor")
    return body


def _headers(scope):
    result = {}
    for key, value in scope.get("headers", []):
        name = key.decode("ascii").lower()
        if name in result and name in {"host", "origin", "content-type", "content-length"}:
            raise ValueError("Duplicate authority or content header")
        result[name] = value.decode("latin-1")
    return result


def _same_origin(headers: dict) -> bool:
    host, supplied = headers.get("host", ""), headers.get("origin", "")
    if not host or not supplied or any(c.isspace() for c in host + supplied):
        return False
    try:
        origin = urlsplit(supplied)
        authority = urlsplit("//" + host)
        # Reading these properties also rejects malformed/out-of-range ports.
        _ = origin.port, authority.port
        return bool(origin.scheme in {"http", "https"} and origin.hostname and
                    origin.username is None and origin.password is None and
                    not origin.path and not origin.query and not origin.fragment and
                    authority.hostname and authority.username is None and authority.password is None and
                    not authority.path and not authority.query and not authority.fragment and
                    origin.netloc.lower() == authority.netloc.lower())
    except ValueError:
        return False


async def _json(send, status: int, value: dict, extra_headers=()):
    payload = _line(value)
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"cache-control", b"no-store"), *extra_headers]})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


def _completion(result: dict, body: dict, chunks: int) -> dict:
    if result.get("request_id") != body["request_id"]:
        raise ValueError("Runner request correlation mismatch")
    for key, maximum in (("decoded_bytes", DECODED_BYTES), ("compressed_bytes", GZIP_BYTES)):
        value = result.get(key)
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("Runner artifact exceeds transport bounds")
    for key in ("decoded_sha256", "compressed_sha256"):
        if not isinstance(result.get(key), str) or not HEX64.fullmatch(result[key]):
            raise ValueError("Invalid runner artifact identity")
    worlds = result.get("world_status")
    if not isinstance(worlds, dict) or set(worlds) != {"afterlight", "baseline"} or not all(
        isinstance(value, str) and 0 < len(value) <= 64 for value in worlds.values()
    ):
        raise ValueError("Invalid recorded world statuses")
    if not isinstance(result.get("scenario_id"), str) or not 0 < len(result["scenario_id"]) <= 256:
        raise ValueError("Invalid scenario identity")
    allowed = ("request_id", "scenario_id", "decoded_bytes", "compressed_sha256", "compressed_bytes", "world_status",
               "source_commit", "source_code_sha256", "canonical_map_sha256", "sumo_version", "interpretation")
    return {"type": "complete", "chunks": chunks, "replay_sha256": result["decoded_sha256"],
            **{key: result[key] for key in allowed if key in result}}


async def _stream(body, receive, send, deadline, cancellation_store):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=QUEUE_ITEMS)
    aborted = asyncio.Event()
    state = {"reason": None, "phase": "starting"}
    control = RunControl()
    worker = None
    sent_bytes = 0
    started = False

    def abort(reason):
        if state["reason"] is None:
            state["reason"] = reason
        control.cancel()
        aborted.set()

    def bridge(event):
        control.check_cancelled()
        if event.get("type") not in {"progress", "route", "queue", "replay_chunk"}:
            raise ValueError("Unsupported simulation event")
        if event.get("type") == "progress" and isinstance(event.get("phase"), str) and re.fullmatch(r"[a-z_]{1,64}", event["phase"]):
            state["phase"] = event["phase"]
        data = _line(event)
        pending = asyncio.run_coroutine_threadsafe(queue.put(data), loop)
        try:
            while True:
                try:
                    pending.result(timeout=.05)
                    break
                except FutureTimeout:
                    control.check_cancelled()
        finally:
            if not pending.done():
                pending.cancel()
        control.check_cancelled()

    control.on_progress = bridge

    def run_and_deliver():
        with run_cloud_simulation(body, control) as result:
            # Validate metadata before advertising any replay bytes.
            completion = _completion(result, body, 0)
            count, transferred = 0, 0
            hashed = hashlib.sha256()
            with result["gzip_path"].open("rb") as source:
                while block := source.read(CHUNK_BYTES):
                    control.check_cancelled()
                    transferred += len(block)
                    if transferred > GZIP_BYTES:
                        raise ValueError("Replay transfer exceeds its bound")
                    hashed.update(block)
                    bridge({"type": "replay_chunk", "index": count,
                            "data": base64.b64encode(block).decode("ascii")})
                    count += 1
            control.check_cancelled()
            if transferred != result["compressed_bytes"] or hashed.hexdigest() != result["compressed_sha256"]:
                raise ValueError("Replay bytes changed during transfer")
            completion["chunks"] = count
        # Leaving the context cleans owned children/tempfiles before complete.
        return completion

    def work():
        def notify(reason):
            loop.call_soon_threadsafe(abort, reason)
        with CancellationWatch(cancellation_store, body["request_id"], control, notify):
            return run_and_deliver()

    async def disconnect():
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                abort("disconnected")
                return

    async def expire():
        await asyncio.sleep(max(0, deadline - loop.time()))
        abort("deadline_exceeded")

    async def send_active(message):
        if aborted.is_set():
            return False
        operation = asyncio.create_task(send(message))
        stop = asyncio.create_task(aborted.wait())
        try:
            done, _ = await asyncio.wait({operation, stop}, return_when=asyncio.FIRST_COMPLETED)
            if operation in done:
                await operation
                return True
            return False
        except (OSError, ConnectionError):
            abort("disconnected")
            return False
        finally:
            for task in (operation, stop):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation, stop, return_exceptions=True)

    async def send_line(data):
        nonlocal sent_bytes
        if sent_bytes + len(data) > WIRE_BYTES:
            raise ValueError("Stream exceeds its wire bound")
        if await send_active({"type": "http.response.body", "body": data, "more_body": True}):
            sent_bytes += len(data)
            return True
        return False

    watcher = asyncio.create_task(disconnect())
    timer = asyncio.create_task(expire())
    terminal_error = None
    try:
        if not await send_active({"type": "http.response.start", "status": 200,
            "headers": [(b"content-type", b"application/x-ndjson; charset=utf-8"),
                        (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]}):
            raise SimulationCancelled()
        started = True
        if not await send_line(_line({"type": "accepted", "request_id": body["request_id"]})):
            raise SimulationCancelled()
        worker = asyncio.create_task(asyncio.to_thread(work))
        while not aborted.is_set():
            if not queue.empty():
                if not await send_line(queue.get_nowait()):
                    break
                continue
            if worker.done():
                complete = worker.result()
                if await send_line(_line(complete)):
                    await send_active({"type": "http.response.body", "body": b"", "more_body": False})
                else:
                    raise SimulationCancelled()
                return
            item = asyncio.create_task(queue.get())
            stop = asyncio.create_task(aborted.wait())
            try:
                done, _ = await asyncio.wait({item, worker, stop}, return_when=asyncio.FIRST_COMPLETED)
                if item in done and not aborted.is_set():
                    if not await send_line(item.result()):
                        break
            finally:
                for task in (item, stop):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(item, stop, return_exceptions=True)
    except asyncio.CancelledError:
        abort("disconnected")
        raise
    except SimulationCancelled:
        terminal_error = "cancelled"
        control.cancel()
    except Exception:
        # Server-only traceback, without locals or request data. Never include
        # the request capability, credentials, environment or request body.
        LOGGER.exception("Exploratory simulation failed request_hash=%s phase=%s",
                         hashlib.sha256(body["request_id"].encode()).hexdigest()[:12], state["phase"])
        terminal_error = "simulation_failed"
        control.cancel()
    finally:
        control.cancel()
        if worker is not None:
            # Never cancel the asyncio.to_thread task: doing so abandons its
            # actual running thread and could release the slot before cleanup.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    control.cancel()
                except Exception:
                    break
            if worker.done() and not worker.cancelled():
                worker.exception()  # Retrieve any already-reported exception.
        control.close()
        for task in (watcher, timer):
            task.cancel()
        await asyncio.gather(watcher, timer, return_exceptions=True)
    if state["reason"] != "disconnected":
        code = state["reason"] or terminal_error or "simulation_failed"
        messages = {"deadline_exceeded": "This run reached the hosted time limit. No replay was installed.",
                    "cancelled": "The simulation was cancelled. No replay was installed.",
                    "cancellation_unavailable": "The shared Stop channel became unavailable. The simulation was stopped; no replay was installed.",
                    "simulation_failed": "The simulation could not finish. No replay was installed."}
        terminal = ({"type": "cancelled", "request_id": body["request_id"]} if code == "cancelled" else
                    {"type": "error", "request_id": body["request_id"], "code": code,
                     "message": messages.get(code, messages["simulation_failed"])})
        try:
            if started:
                await asyncio.wait_for(send({"type": "http.response.body", "more_body": False,
                    "body": _line(terminal)}), timeout=1)
            else:
                await asyncio.wait_for(_json(send, 408 if code == "deadline_exceeded" else 503,
                    {"error": messages.get(code, messages["simulation_failed"])}), timeout=1)
        except (OSError, ConnectionError, asyncio.TimeoutError):
            pass


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    deadline = asyncio.get_running_loop().time() + TOTAL_SECONDS
    method = scope.get("method", "GET").upper()
    if method == "GET":
        try:
            CancellationStore.from_environment()
            configured = True
        except CancellationUnavailable:
            configured = False
        await _json(send, 200, {"status": "available" if configured else "not_configured", "generation_supported": configured, "transport": "ndjson",
            "profile": "city/moderate/seed7/fixed20/0.5s/pilot", "deadline_s": TOTAL_SECONDS,
            "max_decoded_bytes": DECODED_BYTES, "max_compressed_bytes": GZIP_BYTES,
            "cancellation": "private_blob_marker", "cancellation_configured": configured, "persistence": False})
        return
    if method != "POST":
        await _json(send, 405, {"error": "Use GET for capabilities or POST for a new journey."}, [(b"allow", b"GET, POST")])
        return
    try:
        headers = _headers(scope)
    except (ValueError, UnicodeError):
        await _json(send, 400, {"error": "Invalid request headers."})
        return
    if not _same_origin(headers):
        await _json(send, 403, {"error": "Open the viewer on the same origin to start a journey."})
        return
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        await _json(send, 415, {"error": "Send a JSON journey request."})
        return
    if "content-length" in headers:
        try:
            length = int(headers["content-length"])
            if length < 0:
                raise ValueError()
        except ValueError:
            await _json(send, 400, {"error": "Invalid request length."})
            return
        if length > REQUEST_BYTES:
            await _json(send, 413, {"error": "Journey request is too large."})
            return
    raw = bytearray()
    body_deadline = min(deadline, asyncio.get_running_loop().time() + REQUEST_READ_SECONDS)
    try:
        while True:
            event = await asyncio.wait_for(receive(), timeout=max(0, body_deadline - asyncio.get_running_loop().time()))
            if event["type"] == "http.disconnect":
                return
            if event["type"] != "http.request":
                raise ValueError()
            raw.extend(event.get("body", b""))
            if len(raw) > REQUEST_BYTES:
                await _json(send, 413, {"error": "Journey request is too large."})
                return
            if not event.get("more_body", False):
                break
        if "content-length" in headers and len(raw) != length:
            raise ValueError("Request length differs from its header")
        body = _request_body(bytes(raw))
    except asyncio.TimeoutError:
        await _json(send, 408, {"error": "Journey request timed out before it was received."})
        return
    except (ValueError, UnicodeError, RecursionError):
        await _json(send, 400, {"error": "Choose a valid pickup and hospital with a new request identifier."})
        return
    try:
        cancellation_store = CancellationStore.from_environment()
    except CancellationUnavailable:
        await _json(send, 503, {"error": "The shared Stop channel is not configured. No simulation was started."})
        return
    if not ACTIVE.acquire(blocking=False):
        await _json(send, 429, {"error": "This server instance is already generating a journey. Try again after it finishes."}, [(b"retry-after", b"10")])
        return
    try:
        await _stream(body, receive, send, deadline, cancellation_store)
    finally:
        ACTIVE.release()
