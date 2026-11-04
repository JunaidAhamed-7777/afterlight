"""Private, uncached cross-instance cancellation flags for exploratory requests.

Only the prefixed private-store credential is read. Request IDs are capabilities;
an HMAC also keeps their corresponding storage names out of client-visible URLs.
No simulation, replay, user data or scientific evidence is stored here.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import threading
from urllib.parse import urlencode


TOKEN_ENV = "AFTERLIGHT_CANCEL_READ_WRITE_TOKEN"
TIMEOUT_SECONDS = 2
POLL_SECONDS = 1
RESPONSE_BYTES = 16 * 1024
MARKER = b"afterlight-cancel-v1\n"


class CancellationUnavailable(RuntimeError):
    """The shared cancellation channel could not be verified."""


def valid_request_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None


class CancellationStore:
    def __init__(self, token: str):
        # This is the official read/write token layout. Do not fall back to a
        # different store's token or OIDC credential if this one is unavailable.
        match = re.fullmatch(r"vercel_blob_rw_([A-Za-z0-9]+)_([A-Za-z0-9]+)", token)
        if not match or len(token) > 4096:
            raise CancellationUnavailable("Shared cancellation is not configured.")
        self._token = token
        self._store_id = match.group(1)
        self._host = self._store_id.lower() + ".private.blob.vercel-storage.com"

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get(TOKEN_ENV, ""))

    def pathname(self, request_id):
        if not valid_request_id(request_id):
            raise ValueError("Invalid cancellation request identifier")
        digest = hmac.new(self._token.encode(), ("afterlight-cancel-v1:" + request_id).encode(), hashlib.sha256).hexdigest()
        return "afterlight-cancellations/v1/" + digest + ".txt"

    def _request(self, host, method, path, body=None, headers=None):
        # Fixed HTTPS hosts; no redirects, proxy configuration or arbitrary URL
        # supplied by a caller can receive the private bearer credential.
        connection = http.client.HTTPSConnection(host, timeout=TIMEOUT_SECONDS)
        values = {"authorization": "Bearer " + self._token, **(headers or {})}
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            payload = response.read(RESPONSE_BYTES + 1)
            if len(payload) > RESPONSE_BYTES:
                raise CancellationUnavailable("Shared cancellation returned an invalid response.")
            return response.status, payload
        except (OSError, http.client.HTTPException) as error:
            raise CancellationUnavailable("Shared cancellation could not be reached.") from None
        finally:
            connection.close()

    def _api(self, method, path, body, headers=None):
        return self._request("vercel.com", method, "/api/blob" + path, body, {
            "x-api-version": "12", "x-vercel-blob-store-id": self._store_id,
            **(headers or {}),
        })

    def request_cancel(self, request_id):
        pathname = self.pathname(request_id)
        status, payload = self._api("PUT", "/?" + urlencode({"pathname": pathname}), MARKER, {
            "x-vercel-blob-access": "private", "x-add-random-suffix": "0",
            "x-allow-overwrite": "1", "x-content-type": "text/plain; charset=utf-8",
            "x-cache-control-max-age": "0", "content-type": "text/plain; charset=utf-8",
        })
        if status not in {200, 201}:
            raise CancellationUnavailable("The cancellation request could not be saved.")
        try:
            result = json.loads(payload)
            if result.get("pathname") != pathname or result.get("url") != "https://" + self._host + "/" + pathname:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise CancellationUnavailable("Shared cancellation returned an invalid acknowledgement.") from None

    def is_cancelled(self, request_id):
        status, payload = self._request(self._host, "GET", "/" + self.pathname(request_id) + "?cache=0", headers={
            "cache-control": "no-cache, no-store", "pragma": "no-cache",
        })
        if status == 404:
            return False
        if status != 200 or payload != MARKER:
            raise CancellationUnavailable("The shared cancellation state could not be verified.")
        return True

    def remove(self, request_id):
        url = "https://" + self._host + "/" + self.pathname(request_id)
        status, _ = self._api("POST", "/delete", json.dumps({"urls": [url]}).encode(), {"content-type": "application/json"})
        if status not in {200, 204}:
            raise CancellationUnavailable("The cancellation marker could not be removed.")


class CancellationWatch:
    """Own one bounded polling thread; join it before releasing the run slot."""
    def __init__(self, store, request_id, control, notify):
        self.store, self.request_id, self.control, self.notify = store, request_id, control, notify
        self.stop = threading.Event()
        self.thread = None
        self.detected = False

    def _poll(self):
        try:
            if self.store.is_cancelled(self.request_id):
                self.detected = True
                self.control.cancel()
                self.notify("cancelled")
                return False
            return True
        except CancellationUnavailable:
            # Never keep an expensive run alive when its explicit Stop channel
            # is unavailable (auth, quota, network and malformed reads included).
            self.control.cancel()
            self.notify("cancellation_unavailable")
            return False

    def _run(self):
        while not self.stop.wait(POLL_SECONDS):
            if not self._poll():
                return

    def __enter__(self):
        # Honor a Cancel arriving before the simulation worker starts, and
        # authenticate the shared channel before creating a SUMO process.
        if not self._poll():
            try:
                self.control.check_cancelled()
            finally:
                self.__exit__()
        self.thread = threading.Thread(target=self._run, name="afterlight-shared-cancellation", daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        if self.detected:
            try:
                self.store.remove(self.request_id)
            except CancellationUnavailable:
                pass  # Bounded best effort; this unique capability is not reused.
