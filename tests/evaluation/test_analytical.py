"""Analytical contract unit cases, not measured gains or action-diversity evidence."""
import unittest
from models.analytical import AnalyticalConfig, choose_lead, estimate_candidates


def snapshot(queue=0, occupancy=0):
    return {"dispatch_s": 30, "sensor_lag_s": 1, "observed_at_s": 29, "values": {
        "queue_sum_veh": queue, "queue_max_veh": queue, "downstream_occupancy": occupancy,
        "route_distance_m": 500, "route_junction_count": 3, "eta_remaining_s": 40 + queue * 2,
        "phase_elapsed_s": 2}}


class AnalyticalTests(unittest.TestCase):
    def test_empty_queue_does_not_reward_early_clearance(self):
        result = choose_lead(snapshot())
        self.assertEqual(result["lead_s"], 0)
        self.assertIsNone(result["model_sha256"])
        self.assertTrue(result["prediction_not_measurement"])

    def test_occupancy_cannot_create_extra_discharge(self):
        empty = estimate_candidates(snapshot(10, 0))["scores"]
        full = estimate_candidates(snapshot(10, 1))["scores"]
        self.assertGreaterEqual(full[-1]["predicted_ambulance_s"], empty[-1]["predicted_ambulance_s"])
        self.assertEqual(len(empty), 5)

    def test_finite_observations_cannot_overflow_estimator(self):
        observation = snapshot()
        observation["values"]["queue_sum_veh"] = 1e308
        with self.assertRaises(ValueError):
            estimate_candidates(observation)

    def test_model_requires_protocol_and_matching_analytical_metadata(self):
        with self.assertRaises(ValueError):
            choose_lead(snapshot(), model={"model": {}, "sha256": "not-trained"})
        with self.assertRaises(ValueError):
            choose_lead(snapshot(), civilian_weight=1, config=AnalyticalConfig(civilian_weight=2))


if __name__ == "__main__":
    unittest.main()
