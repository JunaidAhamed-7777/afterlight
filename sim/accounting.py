"""All-demand lifecycle accounting independent of completion-only SUMO averages."""
from __future__ import annotations
from dataclasses import dataclass, field
import math


@dataclass
class Accounting:
    scheduled: dict[str, dict]
    inserted: dict[str, float] = field(default_factory=dict)
    completed: dict[str, float] = field(default_factory=dict)

    def depart(self, ids, now: float):
        for vid in ids:
            if vid not in self.scheduled:
                raise ValueError(f'Unexpected physical vehicle {vid}')
            if vid in self.inserted:
                raise ValueError(f'Duplicate insertion {vid}')
            self.inserted[vid] = now

    def arrive(self, ids, now: float):
        for vid in ids:
            if vid not in self.inserted:
                raise ValueError(f'Arrival without insertion {vid}')
            if vid in self.completed:
                raise ValueError(f'Duplicate arrival {vid}')
            self.completed[vid] = now

    def counts(self, *, civilians_only=True) -> dict[str, int]:
        ids = {v for v in self.scheduled if not civilians_only or v != 'ambulance'}
        inserted = ids & self.inserted.keys()
        completed = ids & self.completed.keys()
        return {'scheduled': len(ids), 'inserted': len(inserted), 'completed': len(completed),
                'running': len(inserted - completed), 'not_inserted': len(ids - inserted)}

    def rows(self) -> list[dict]:
        return [{'id': vid, 'type': v['type'], 'scheduled_depart_s': v['depart_s'],
                 'actual_depart_s': self.inserted.get(vid), 'arrival_s': self.completed.get(vid),
                 'reference_s': v['reference_s'],
                 'journey_from_schedule_s': self.completed[vid] - v['depart_s'] if vid in self.completed else None,
                 'excess_s': max(0, self.completed[vid] - v['depart_s'] - v['reference_s']) if vid in self.completed else None}
                for vid, v in self.scheduled.items()]

    def completed_civilian_mean_excess(self) -> float | None:
        counts = self.counts()
        if counts['completed'] != counts['scheduled']:
            return None
        rows = [r for r in self.rows() if r['id'] != 'ambulance']
        return sum(r['excess_s'] for r in rows) / len(rows) if rows else 0.0
