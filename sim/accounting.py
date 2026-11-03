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


    def civilian_excess_tail(self, status: str) -> dict:
        """Descriptive individual-vehicle tail, never a completion-only sample."""
        counts = self.counts()
        count = counts['scheduled']
        eligible = status == 'completed' and counts['completed'] == count and count > 0
        value = None
        if eligible:
            values = []
            for vid, vehicle in self.scheduled.items():
                if vid == 'ambulance':
                    continue
                inputs = (self.completed[vid], vehicle['depart_s'], vehicle['reference_s'])
                try:
                    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in inputs):
                        raise ValueError('Individual civilian tail requires finite lifecycle inputs')
                    excess = inputs[0] - inputs[1] - inputs[2]
                    if not math.isfinite(excess):
                        raise ValueError('Individual civilian tail arithmetic is nonfinite')
                except OverflowError as error:
                    raise ValueError('Individual civilian tail arithmetic exceeds finite range') from error
                values.append(max(0, excess))
            values.sort()
            # Exact nearest rank: ceil(0.95*n), one-based; no interpolation.
            value = values[(95 * count + 99) // 100 - 1]
        return {'civilian_excess_p95_s': value,
                'civilian_excess_p95_population': {
                    'scope': 'all_scheduled_civilian_vehicles_in_this_world',
                    'scheduled_count': count, 'completed_count': counts['completed'],
                    'included_count': count if eligible else 0,
                    'eligibility': 'valid_completed_world_all_civilians_completed_nonempty',
                    'percentile': 95, 'method': 'nearest_rank_ceil_p_times_n_no_interpolation',
                    'value_definition': 'max(0, arrival_s - scheduled_departure_s - per_vehicle_reference_s)',
                    'reference': 'saved demand external-lane free-flow lower bound; excludes internal junctions and acceleration',
                    'units': 'seconds', 'ambulance_excluded': True}}


def reconcile_tripinfo(ledger: Accounting, path) -> list[str]:
    """Replace discovery-step timestamps with SUMO's authoritative trip times.

    TraCI's arrived/departed lists describe the last step, not necessarily the
    exact timestamp stored in tripinfo. The simulator is closed/flushed first.
    """
    import xml.etree.ElementTree as ET
    reasons = []
    seen = set()
    for trip in ET.parse(path).getroot().findall('tripinfo'):
        vid = trip.attrib['id']
        if vid not in ledger.scheduled or vid in seen:
            reasons.append('tripinfo_identity_mismatch')
            continue
        seen.add(vid)
        departure = float(trip.attrib['depart'])
        arrival = float(trip.attrib['arrival'])
        if not math.isfinite(departure) or not math.isfinite(arrival):
            reasons.append('nonfinite_tripinfo_time')
            continue
        if (departure >= 0) != (vid in ledger.inserted) or (arrival >= 0) != (vid in ledger.completed):
            reasons.append('tripinfo_lifecycle_mismatch')
        if departure >= 0:
            ledger.inserted[vid] = departure
        if arrival >= 0:
            ledger.completed[vid] = arrival
        vaporized = trip.get('vaporized', '')
        # SUMO 1.28 writes "end" for unfinished/undeparted vehicles flushed at
        # the common endpoint. They remain running/not-inserted in our ledger
        # and make the world censored, rather than a physical removal failure.
        # Real removals (collision/TraCI/vaporizer/etc.) and an "end" marker on
        # a claimed completed trip remain invalid.
        unfinished_at_end = vaporized == 'end' and arrival == -1
        if vaporized not in ('', 'false', '0') and not unfinished_at_end:
            reasons.append('vaporized_vehicle')
    if seen != set(ledger.scheduled):
        reasons.append('tripinfo_missing_scheduled_vehicle')
    return sorted(set(reasons))
