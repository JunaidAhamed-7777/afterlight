"""Acknowledge a durable private cancellation flag, never claim work has stopped."""
from __future__ import annotations

import asyncio
import json

from api.simulate import _constant, _finite, _headers, _json, _same_origin, _unique
from cloud.cancellation import CancellationStore, CancellationUnavailable, valid_request_id

REQUEST_BYTES = 4096
REQUEST_SECONDS = 10


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    if scope.get("method", "GET").upper() != "POST":
        await _json(send, 405, {"error": "Use POST to request cancellation."}, [(b"allow", b"POST")])
        return
    try:
        headers = _headers(scope)
    except (ValueError, UnicodeError):
        await _json(send, 400, {"error": "Invalid request headers."})
        return
    if not _same_origin(headers):
        await _json(send, 403, {"error": "Request cancellation from the same viewer origin."})
        return
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        await _json(send, 415, {"error": "Send a JSON cancellation request."})
        return
    raw = bytearray()
    try:
        length = int(headers["content-length"]) if "content-length" in headers else None
        if length is not None and length < 0:
            raise ValueError()
        if length is not None and length > REQUEST_BYTES:
            await _json(send, 413, {"error": "Cancellation request is too large."})
            return
        deadline = asyncio.get_running_loop().time() + REQUEST_SECONDS
        while True:
            event = await asyncio.wait_for(receive(), max(0, deadline - asyncio.get_running_loop().time()))
            if event["type"] == "http.disconnect":
                return
            if event["type"] != "http.request":
                raise ValueError()
            raw.extend(event.get("body", b""))
            if len(raw) > REQUEST_BYTES:
                await _json(send, 413, {"error": "Cancellation request is too large."})
                return
            if not event.get("more_body", False):
                break
        if length is not None and length != len(raw):
            raise ValueError()
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_float=_finite, parse_constant=_constant)
        if not isinstance(body, dict) or set(body) != {"request_id"} or not valid_request_id(body["request_id"]):
            raise ValueError()
    except asyncio.TimeoutError:
        await _json(send, 408, {"error": "Cancellation request timed out."})
        return
    except (ValueError, UnicodeError, RecursionError):
        await _json(send, 400, {"error": "Supply the current journey request identifier."})
        return
    try:
        store = CancellationStore.from_environment()
        await asyncio.to_thread(store.request_cancel, body["request_id"])
    except CancellationUnavailable:
        await _json(send, 503, {"error": "Cancellation could not be confirmed. Try Stop again.", "request_id": body["request_id"]})
        return
    await _json(send, 202, {"request_id": body["request_id"], "cancel_requested": True})
