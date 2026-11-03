"""Read the exact latest SUMO observations through TraCI subscriptions.

Subscriptions replace per-vehicle/per-lane socket round trips. They neither
predict traffic nor change the simulation clock. Missing subscription data is
an error: an incomplete observation must never quietly become an empty queue.
"""
from __future__ import annotations


class ObservationCache:
    def __init__(self, conn, network: dict):
        from traci import constants as tc
        self.conn = conn
        self.tc = tc
        self.vehicle_variables = (tc.VAR_POSITION, tc.VAR_ANGLE, tc.VAR_TYPE,
                                  tc.VAR_SPEED, tc.VAR_LENGTH, tc.VAR_WIDTH)
        # Include outgoing lanes because the frozen dispatch observation uses
        # downstream occupancy; do not infer it from incoming queues.
        self.lane_ids = sorted({lane for signal in network['signals'].values()
            for link in signal['links'] for lane in (link['from_lane'], link['to_lane'])})
        for lane in self.lane_ids:
            conn.lane.subscribe(lane, (tc.LAST_STEP_VEHICLE_HALTING_NUMBER, tc.LAST_STEP_OCCUPANCY))
        self.vehicles = {}
        self.lanes = {}
        self.refresh(())

    def refresh(self, departed_ids) -> None:
        for vehicle in departed_ids:
            self.conn.vehicle.subscribe(vehicle, self.vehicle_variables)
        self.lanes = self.conn.lane.getAllSubscriptionResults()
        for lane in self.lane_ids:
            values = self.lanes.get(lane, {})
            if not {self.tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
                    self.tc.LAST_STEP_OCCUPANCY} <= values.keys():
                raise RuntimeError(f'Incomplete latest SUMO lane subscription: {lane}')
        self.vehicles = self.conn.vehicle.getAllSubscriptionResults()
        for vehicle, values in self.vehicles.items():
            if not set(self.vehicle_variables) <= values.keys():
                raise RuntimeError(f'Incomplete latest SUMO vehicle subscription: {vehicle}')

    def halting(self, lane: str) -> int:
        return self.lanes[lane][self.tc.LAST_STEP_VEHICLE_HALTING_NUMBER]

    def occupancy(self, lane: str) -> float:
        return self.lanes[lane][self.tc.LAST_STEP_OCCUPANCY]

    def speed(self, vehicle: str) -> float:
        return self.vehicles[vehicle][self.tc.VAR_SPEED]

    def poses(self) -> list[dict]:
        tc = self.tc
        result = []
        for vehicle in sorted(self.vehicles):
            values = self.vehicles[vehicle]
            x, y = values[tc.VAR_POSITION]
            result.append({'id': vehicle, 'type': values[tc.VAR_TYPE],
                'x': round(x, 4), 'y': round(y, 4), 'z': 0.0,
                'angle_deg': round(values[tc.VAR_ANGLE], 4),
                'speed_mps': round(values[tc.VAR_SPEED], 4),
                'length_m': values[tc.VAR_LENGTH], 'width_m': values[tc.VAR_WIDTH]})
        return result
