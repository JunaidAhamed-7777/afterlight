import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from sim.traci_cache import ObservationCache


class SubscriptionTests(unittest.TestCase):
    def connection(self):
        from traci import constants as tc
        lane_values = {tc.LAST_STEP_VEHICLE_HALTING_NUMBER: 3, tc.LAST_STEP_OCCUPANCY: 12.5}
        conn = SimpleNamespace(lane=Mock(), vehicle=Mock())
        conn.lane.getAllSubscriptionResults.return_value = {'in_0': lane_values, 'out_0': lane_values}
        conn.vehicle.getAllSubscriptionResults.return_value = {}
        return conn, tc

    def test_missing_queue_observation_fails_instead_of_assuming_zero(self):
        conn, _ = self.connection()
        conn.lane.getAllSubscriptionResults.return_value = {'in_0': {}}
        with self.assertRaisesRegex(RuntimeError, 'Incomplete latest SUMO lane'):
            ObservationCache(conn, {'signals': {'j': {'links': [{'from_lane': 'in_0', 'to_lane': 'out_0'}]}}})

    def test_uses_latest_exact_values_and_includes_outgoing_lane(self):
        conn, tc = self.connection()
        cache = ObservationCache(conn, {'signals': {'j': {'links': [{'from_lane': 'in_0', 'to_lane': 'out_0'}]}}})
        self.assertEqual(conn.lane.subscribe.call_count, 2)
        self.assertEqual(cache.halting('in_0'), 3)
        self.assertEqual(cache.occupancy('out_0'), 12.5)
        values = {tc.VAR_POSITION: (10.123456, -20), tc.VAR_ANGLE: 90.123456,
                  tc.VAR_TYPE: 'bike', tc.VAR_SPEED: 0.0, tc.VAR_LENGTH: 1.8, tc.VAR_WIDTH: .6}
        conn.vehicle.getAllSubscriptionResults.return_value = {'civilian_1': values}
        cache.refresh(['civilian_1'])
        self.assertEqual(cache.poses(), [{'id': 'civilian_1', 'type': 'bike', 'x': 10.1235,
            'y': -20, 'z': 0.0, 'angle_deg': 90.1235, 'speed_mps': 0.0, 'length_m': 1.8, 'width_m': .6}])
        conn.vehicle.getAllSubscriptionResults.return_value = {}
        cache.refresh(())
        self.assertEqual(cache.poses(), [])


if __name__ == '__main__':
    unittest.main()
