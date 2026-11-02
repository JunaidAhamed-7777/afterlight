"""Bounded local generation jobs; a completed replay is still recorded evidence.

No work starts on import. The server must explicitly enable generation. A single
worker prevents accidental parallel SUMO batches from repeated UI requests.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Callable
from uuid import uuid4


class RequestError(ValueError):
    pass


class OutputConflict(RequestError):
    """Runner refused an output directory it does not own."""


def parameters(value: object) -> dict:
    if not isinstance(value, dict):
        raise RequestError("Request must be a JSON object")
    allowed = {"network", "seed", "regime", "policy", "lead", "pickup", "hospital"}
    if set(value) - allowed:
        raise RequestError("Request contains unsupported parameters")
    result = {"network": "city", "seed": 7, "regime": "moderate", "policy": "fixed", "lead": 10,
              "pickup": None, "hospital": None, **value}
    for name, choices in {"network": ("fixture", "city"), "regime": ("sparse", "moderate", "heavy", "asymmetric"),
                          "policy": ("fixed", "immediate", "ordinary", "analytical"), "lead": (0, 5, 10, 20, 30)}.items():
        if isinstance(result[name], bool) or result[name] not in choices:
            raise RequestError(f"Unsupported {name}")
    if isinstance(result["seed"], bool) or not isinstance(result["seed"], int) or not 0 <= result["seed"] <= 2**31-1:
        raise RequestError("Seed must be an integer from 0 to 2147483647")
    from sim.network import load_graph
    graph = load_graph(result["network"])
    for name, rows in (("pickup", graph["pickups"]), ("hospital", graph["hospitals"])):
        if result[name] is not None and result[name] not in {row["id"] for row in rows}:
            raise RequestError(f"Unknown {name} for this network")
    return result


def real_runner(args):
    from sim.run import run_pair, OutputPathError
    try:
        return run_pair(args)
    except OutputPathError as exc:
        raise OutputConflict(str(exc)) from exc


class JobManager:
    def __init__(self, output_root: Path, runner: Callable = real_runner):
        self.output_root = output_root.resolve()
        self.runner = runner
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="afterlight-local")
        self.closed = False

    def submit(self, body: object) -> dict:
        params = parameters(body)
        with self.lock:
            if self.closed:
                raise RequestError("Generation is shutting down")
            if any(job["status"] in {"queued", "running"} for job in self.jobs.values()):
                raise RequestError("A local simulation is already running; wait for its actual result")
            job_id = uuid4().hex
            job = {"id": job_id, "status": "queued", "parameters": params, "created_at": time.time(),
                   "mode": "local-generation", "message": "Queued for real SUMO execution; no result yet"}
            self.jobs[job_id] = job
            self.executor.submit(self._run, job_id, params)
            return deepcopy(job)

    def _run(self, job_id: str, params: dict) -> None:
        with self.lock:
            self.jobs[job_id].update(status="running", started_at=time.time(), message="Running independent baseline and AFTERLIGHT worlds")
            record = deepcopy(self.jobs[job_id])
        output = self.output_root / job_id
        safe_output = False
        args = SimpleNamespace(**params, output=output, dispatch=60.0, demand_end=180.0,
                               horizon=240.0, drain=360.0, step=.5, sample=1.0, split="pilot")
        try:
            safe_output = output.resolve().parent == self.output_root and not output.exists()
            if not safe_output:
                raise RequestError("Job output must be a new contained directory")
            result = self.runner(args)
            from export.replay import validate_replay
            replay_path = output / "replay.json"
            if replay_path.resolve().parent != output.resolve() or output.resolve().parent != self.output_root:
                raise RequestError("Generated replay escaped its job directory")
            replay = json.loads(replay_path.read_text(encoding="utf-8"))
            validate_replay(replay)
            record.update(status="completed", finished_at=time.time(), result=result,
                          replay_url=f"/api/jobs/{job_id}/replay",
                          message="Real paired execution finished; inspect validity and censoring before interpreting")
        except Exception as exc:
            if isinstance(exc, OutputConflict):
                safe_output = False
            record.update(status="failed", finished_at=time.time(), error=str(exc),
                          message="Generation failed; inspect available local artifacts")
        try:
            if not safe_output or output.resolve().parent != self.output_root:
                raise OSError("Refusing persistence into an unowned or escaped path")
            output.mkdir(parents=True, exist_ok=True)
            temporary = output / "job.json.tmp"
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(record, handle, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(output / "job.json")
        except (OSError, ValueError, RuntimeError) as exc:
            record.update(status="failed", finished_at=time.time(), persistence_error=str(exc),
                          message="Job state could not be saved; do not treat this as a completed result")
            record.pop("replay_url", None)
        # Terminal success becomes observable only after its flushed record exists.
        with self.lock:
            self.jobs[job_id] = record

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            return deepcopy(self.jobs.get(job_id))

    def replay_path(self, job_id: str) -> Path | None:
        job = self.get(job_id)
        if not job or job["status"] != "completed":
            return None
        output = self.output_root / job_id
        path = output / "replay.json"
        if output.resolve().parent != self.output_root or path.resolve().parent != output.resolve():
            return None
        return path

    def close(self) -> None:
        with self.lock:
            self.closed = True
        # Never abandon an active SUMO child by killing its coordinating thread.
        self.executor.shutdown(wait=True, cancel_futures=False)
