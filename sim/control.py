"""Optional progress and cancellation for exploratory simulation requests.

Only processes created through this control are terminated. Existing scientific
callers that do not pass a control retain their original execution path.
"""
from __future__ import annotations

import subprocess
import threading
import time
from typing import Callable


class SimulationCancelled(RuntimeError):
    """The caller cancelled an exploratory run; this is not a traffic outcome."""


class RunControl:
    def __init__(self, cancel_event: threading.Event | None = None,
                 on_progress: Callable[[dict], None] | None = None):
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.on_progress = on_progress
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen] = set()
        self._closed = threading.Event()
        self._watcher: threading.Thread | None = None

    def __enter__(self):
        self.check_cancelled()
        return self

    def __exit__(self, *_):
        self.close()

    def cancel(self) -> None:
        self.cancel_event.set()

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise SimulationCancelled("Simulation cancelled by the requesting client")
        if self._closed.is_set():
            raise RuntimeError("Simulation control is closed")

    def emit(self, event: dict) -> None:
        self.check_cancelled()
        if self.on_progress is not None:
            self.on_progress(dict(event))
        self.check_cancelled()

    def progress(self, phase: str, message: str, **values) -> None:
        self.emit({"type": "progress", "phase": phase, "message": message, **values})

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=.75)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                return
            process.wait(timeout=.75)

    def _stop_owned(self) -> None:
        with self._lock:
            processes = tuple(self._processes)
        for process in processes:
            self._stop(process)

    def _watch(self) -> None:
        while not self._closed.wait(.05):
            if self.cancel_event.is_set():
                self._stop_owned()
                return

    def start_process(self, command: list[str], **kwargs) -> subprocess.Popen:
        self.check_cancelled()
        process = subprocess.Popen(command, **kwargs)
        with self._lock:
            self._processes.add(process)
            if self._watcher is None:
                self._watcher = threading.Thread(target=self._watch, name="afterlight-owned-process-cancellation", daemon=True)
                self._watcher.start()
        try:
            self.check_cancelled()
        except BaseException:
            self._stop(process)
            self.release_process(process)
            raise
        return process

    def release_process(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def run_command(self, command: list[str], *, capture_output=False, text=False,
                    check=False, **kwargs) -> subprocess.CompletedProcess:
        if capture_output:
            kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process = self.start_process(command, text=text, **kwargs)
        try:
            while True:
                self.check_cancelled()
                try:
                    stdout, stderr = process.communicate(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            self.check_cancelled()
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            if check:
                result.check_returncode()
            return result
        finally:
            self._stop(process)
            self.release_process(process)

    def start_traci(self, command: list[str], *, label: str, stdout):
        """Launch an owned SUMO handle before connecting, so startup can cancel."""
        import traci
        from sumolib.miscutils import getFreeSocketPort
        port = getFreeSocketPort()
        process = self.start_process([*command, "--remote-port", str(port)], stdout=stdout)
        deadline = time.monotonic() + 30
        try:
            while True:
                self.check_cancelled()
                if process.poll() is not None:
                    raise RuntimeError("SUMO exited before the TraCI connection became ready")
                try:
                    # An unpooled connection is independent of TraCI's global
                    # default/label state and safe for separate request threads.
                    connection = traci.connect(port=port, host="127.0.0.1", numRetries=0,
                                               proc=process, waitBetweenRetries=0)
                    return connection, process
                except traci.exceptions.FatalTraCIError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("SUMO startup did not establish TraCI within 30 seconds")
                    self.cancel_event.wait(.05)
        except BaseException:
            self._stop(process)
            self.release_process(process)
            raise

    def close(self) -> None:
        self._closed.set()
        self._stop_owned()
        if self._watcher is not None and self._watcher is not threading.current_thread():
            self._watcher.join(timeout=2)
