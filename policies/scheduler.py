"""A conservative, SUMO-independent legal signal state machine.

Green states must come from the network's conflict-checked SUMO program. Every
change goes through yellow for *all* previously green links, then all-red. This
intentionally conservative controller is shared by every preemption policy.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math


@dataclass(frozen=True)
class Timing:
    min_green_s: float = 8.0
    ordinary_green_s: float = 25.0
    yellow_s: float = 3.0
    all_red_s: float = 1.0
    max_hold_s: float = 35.0
    request_timeout_s: float = 90.0
    recovery_green_s: float = 25.0

    def __post_init__(self):
        values = vars(self)
        if any(not math.isfinite(v) or v <= 0 for v in values.values()):
            raise ValueError("All timing parameters must be finite and positive")
        if self.ordinary_green_s < self.min_green_s or self.recovery_green_s < self.min_green_s:
            raise ValueError("Ordinary and recovery greens must meet minimum green")
        if self.max_hold_s < self.min_green_s:
            raise ValueError("Maximum hold must meet minimum green")


@dataclass
class Request:
    at_s: float
    phase: int
    junction: str
    onset_s: float | None = None
    released: bool = False


@dataclass
class Scheduler:
    junction: str
    greens: tuple[str, ...]
    timing: Timing = field(default_factory=Timing)
    phase: int = 0
    stage: str = "green"
    entered_s: float = 0.0
    target: int = 0
    request: Request | None = None
    events: list[dict] = field(default_factory=list)
    last_served: list[float] = field(default_factory=list)
    recovering: bool = False
    last_time: float = 0.0
    in_recovery_service: bool = False
    target_recovery: bool = False

    def __post_init__(self):
        if not self.greens or len({len(s) for s in self.greens}) != 1:
            raise ValueError("Nonempty equal-length green states required")
        if any(not any(c in "gG" for c in s) or any(c not in "rRgG" for c in s) for s in self.greens):
            raise ValueError("Green states may contain only green/red links")
        self.last_served = [0.0] * len(self.greens)
        self.events.append({"t": 0.0, "kind": "green", "junction": self.junction, "phase": self.phase})

    @property
    def state(self) -> str:
        if self.stage == "all_red":
            return "r" * len(self.greens[0])
        if self.stage == "yellow":
            return "".join("y" if c in "gG" else "r" for c in self.greens[self.phase])
        return self.greens[self.phase]

    def plan(self, request_at_s: float, phase: int, *, planned_at_s: float | None = None) -> None:
        if self.request is not None:
            raise ValueError("Only one frozen request per junction per run is supported")
        if not math.isfinite(request_at_s) or request_at_s < self.last_time:
            raise ValueError("Request must be finite and not in the past")
        if not 0 <= phase < len(self.greens):
            raise ValueError("Unknown priority phase")
        planned_at_s = self.last_time if planned_at_s is None else planned_at_s
        if not math.isfinite(planned_at_s) or not self.last_time <= planned_at_s <= request_at_s:
            raise ValueError("Plan timestamp must be between current time and request")
        self.request = Request(request_at_s, phase, self.junction)
        self.events.append({"t": planned_at_s, "kind": "request_planned", "junction": self.junction,
                            "request_at_s": request_at_s, "phase": phase})

    def _event(self, now: float, kind: str, **extra) -> None:
        self.events.append({"t": now, "kind": kind, "junction": self.junction, **extra})

    def _begin_change(self, now: float, target: int, *, recovery: bool = False) -> None:
        self.target = target
        self.target_recovery = recovery
        self.stage = "yellow"
        self.entered_s = now
        self._event(now, "yellow", phase=self.phase, target=target)

    def _recovery_phase(self, now: float, queues: list[float]) -> int:
        # One bounded debt-aware service before ordinary cycling resumes.
        # Non-priority phases win ties; queue count is current observation only.
        candidates = [i for i in range(len(self.greens)) if i != self.phase]
        if not candidates:
            return self.phase
        return max(candidates, key=lambda i: ((now - self.last_served[i]) * (1 + queues[i]), -i))

    def advance(self, now: float, *, passed: bool = False, queues: list[float] | None = None) -> str:
        if not math.isfinite(now) or now < self.last_time:
            raise ValueError("Signal time must be finite and monotonic")
        self.last_time = now
        q = queues if queues is not None else [0.0] * len(self.greens)
        if len(q) != len(self.greens) or any(not math.isfinite(x) or x < 0 for x in q):
            raise ValueError("One finite nonnegative queue observation per phase required")
        elapsed = now - self.entered_s
        req = self.request
        active = req is not None and not req.released and now >= req.at_s
        if active and not any(e['kind'] == 'request' for e in self.events):
            self._event(now, "request", phase=req.phase)
        if req is not None and not req.released and (passed or (active and now - req.at_s >= self.timing.request_timeout_s)):
            req.released = True
            self.recovering = active or req.onset_s is not None
            self._event(now, "release", reason="passage" if passed else "request_timeout")
            active = False
        if self.stage == "yellow":
            if elapsed >= self.timing.yellow_s:
                self.stage, self.entered_s = "all_red", now
                self._event(now, "all_red")
            return self.state
        if self.stage == "all_red":
            if elapsed >= self.timing.all_red_s:
                self.phase, self.stage, self.entered_s = self.target, "green", now
                self.last_served[self.phase] = now
                self.in_recovery_service = self.target_recovery
                self.target_recovery = False
                self._event(now, "green", phase=self.phase)
                if active and self.phase == req.phase and req.onset_s is None:
                    req.onset_s = now
                    self._event(now, "priority_green", phase=self.phase)
            return self.state
        self.last_served[self.phase] = now
        if active and self.phase == req.phase:
            if req.onset_s is None:
                req.onset_s = now
                self._event(now, "priority_green", phase=self.phase)
            if now - req.onset_s >= self.timing.max_hold_s:
                req.released = True
                self.recovering = True
                active = False
                self._event(now, "release", reason="max_hold")
            else:
                return self.state
        if elapsed < self.timing.min_green_s:
            return self.state
        if active:
            self._begin_change(now, req.phase)
        elif self.recovering:
            self.recovering = False
            self._begin_change(now, self._recovery_phase(now, q), recovery=True)
            self._event(now, "recovery_requested", phase=self.target)
        elif elapsed >= (self.timing.recovery_green_s if self.in_recovery_service else self.timing.ordinary_green_s):
            self._begin_change(now, (self.phase + 1) % len(self.greens))
        return self.state
