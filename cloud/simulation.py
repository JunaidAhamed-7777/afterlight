"""One real request-owned paired SUMO run, prepared for streamed delivery.

The ASGI caller owns wire framing. It must keep this context open while reading
gzip_path, check control.check_cancelled() between chunks, and never send a
completion event after a cancellation. Every exit closes owned children before
removing only this request's fresh temporary directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace

from export.replay import validate_replay
from sim.control import RunControl
from sim.network import ROOT, load_graph, shortest_route
from sim.run import run_pair


MAX_DECODED_BYTES = 128 * 1024 * 1024
MAX_COMPRESSED_BYTES = 20 * 1024 * 1024
BLOCK_BYTES = 64 * 1024


def cloud_parameters(request: dict) -> dict:
    """The public request selects anchors, not executable arguments or physics."""
    if not isinstance(request, dict) or set(request) != {"request_id", "pickup", "hospital"}:
        raise ValueError("Provide only request_id, pickup and hospital")
    if not isinstance(request["request_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", request["request_id"]):
        raise ValueError("request_id must be 32 lowercase hexadecimal characters")
    if not isinstance(request["pickup"], str) or not isinstance(request["hospital"], str):
        raise ValueError("Choose a canonical city pickup and hospital")
    graph = load_graph("city")
    if request["pickup"] not in {point["id"] for point in graph["pickups"]}:
        raise ValueError("Unknown canonical city pickup")
    if request["hospital"] not in {point["id"] for point in graph["hospitals"]}:
        raise ValueError("Unknown canonical city hospital")
    return {"network": "city", "seed": 7, "regime": "moderate", "policy": "fixed", "lead": 20,
            "pickup": request["pickup"], "hospital": request["hospital"]}


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("Replay JSON contains a nonfinite number")
    return value


def _reject_constant(raw: str):
    raise ValueError(f"Replay JSON contains a forbidden constant: {raw}")


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Replay JSON contains duplicate object keys")
        result[key] = value
    return result


def _validate_protocol(replay: dict, params: dict) -> None:
    scenario = replay["scenario"]
    expected = {"network_kind": "city", "seed": 7, "regime": "moderate", "dispatch_s": 60.0,
                "pickup_id": params["pickup"], "hospital_id": params["hospital"], "split": "pilot"}
    if any(scenario.get(key) != value for key, value in expected.items()):
        raise ValueError("Cloud replay differs from the requested exploratory journey")
    priority = replay["worlds"]["afterlight"]
    if priority["policy"] != "fixed" or priority.get("lead_s") != 20:
        raise ValueError("Cloud replay differs from its fixed 20-second priority policy")
    if replay.get("step_s") != .5 or replay.get("duration_s") != 900:
        raise ValueError("Cloud replay differs from the bounded exploratory capture protocol")
    graph = load_graph("city")
    pickup = next(point for point in graph["pickups"] if point["id"] == params["pickup"])
    hospital = next(point for point in graph["hospitals"] if point["id"] == params["hospital"])
    expected_route = shortest_route(graph, pickup["edge_id"], hospital["destination_node"])
    if scenario.get("route_edges") != expected_route:
        raise ValueError("Cloud replay route differs from canonical Dijkstra for the requested anchors")
    expected_map = hashlib.sha256((ROOT / "assets/map/city_manifest.json").read_bytes()).hexdigest()
    if replay["provenance"].get("canonical_map_sha256") != expected_map:
        raise ValueError("Cloud replay differs from the current canonical map bytes")
    for world in replay["worlds"].values():
        if world["status"] == "infrastructure_error":
            raise ValueError("An infrastructure failure is not a completed traffic recording")
        expected_metrics = {"simulation_step_s": .5, "horizon_s": 360.0, "drain_end_s": 900.0}
        if any(world["metrics"].get(key) != value for key, value in expected_metrics.items()):
            raise ValueError("Cloud replay differs from the fixed simulation integration and horizon")


@contextmanager
def run_cloud_simulation(request: dict, control: RunControl, temporary_root: Path | None = None):
    params = cloud_parameters(request)
    control.check_cancelled()
    workspace = tempfile.TemporaryDirectory(prefix=f"afterlight-{request['request_id'][:12]}-", dir=temporary_root)
    try:
        output = Path(workspace.name) / "run"
        args = SimpleNamespace(**params, output=output, dispatch=60.0, demand_end=180.0,
                               horizon=360.0, drain=540.0, step=.5, sample=.5, split="pilot")
        control.progress("preparing", "Preparing a new exploratory SUMO pair")
        result = run_pair(args, control=control)
        control.progress("validating_export", "Verifying the completed replay and requested journey")
        replay_path = output / "replay.json"
        with replay_path.open("rb") as source:
            payload = source.read(MAX_DECODED_BYTES + 1)
        if len(payload) > MAX_DECODED_BYTES:
            raise ValueError("Generated replay exceeds the bounded decoded size")
        decoded_sha256 = hashlib.sha256(payload).hexdigest()
        if result.get("sha256") != decoded_sha256 or result.get("bytes") != len(payload):
            raise ValueError("Completed replay bytes differ from the runner's recorded identity")
        replay = json.loads(payload.decode("utf-8"), parse_float=_finite_float,
                            parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        validate_replay(replay)
        _validate_protocol(replay, params)
        provenance = replay["provenance"]
        metadata = {
            "request_id": request["request_id"], "scenario_id": replay["scenario"]["id"],
            "decoded_sha256": decoded_sha256, "decoded_bytes": len(payload),
            "world_status": {key: value["status"] for key, value in replay["worlds"].items()},
            "source_commit": provenance.get("source_commit"),
            "source_code_sha256": provenance.get("source_code_sha256"),
            "canonical_map_sha256": provenance.get("canonical_map_sha256"),
            "sumo_version": provenance["sumo_version"],
            "interpretation": "New exploratory paired SUMO execution; not a frozen-study or learned-model result",
        }
        del payload, replay
        control.progress("compressing", "Compressing the original recorded frames without resampling")
        gzip_path = Path(workspace.name) / "replay.json.gz"
        original_hash = hashlib.sha256()
        with replay_path.open("rb") as source, gzip_path.open("wb") as destination:
            with gzip.GzipFile(filename="", fileobj=destination, mode="wb", compresslevel=6, mtime=0) as compressed:
                while block := source.read(BLOCK_BYTES):
                    control.check_cancelled()
                    original_hash.update(block)
                    compressed.write(block)
                    if destination.tell() > MAX_COMPRESSED_BYTES:
                        raise ValueError("Generated replay exceeds the bounded public transfer size")
        if original_hash.hexdigest() != decoded_sha256:
            raise ValueError("Replay changed while packaging its original bytes")
        compressed_bytes = gzip_path.stat().st_size
        if compressed_bytes > MAX_COMPRESSED_BYTES:
            raise ValueError("Generated replay exceeds the bounded public transfer size")
        compressed_hash = hashlib.sha256()
        with gzip_path.open("rb") as source:
            while block := source.read(BLOCK_BYTES):
                control.check_cancelled()
                compressed_hash.update(block)
        control.progress("ready", "Both real traffic worlds are ready for transfer")
        yield {**metadata, "replay_path": replay_path, "gzip_path": gzip_path,
               "compressed_sha256": compressed_hash.hexdigest(), "compressed_bytes": compressed_bytes}
        control.check_cancelled()
    finally:
        try:
            control.close()
        finally:
            workspace.cleanup()
