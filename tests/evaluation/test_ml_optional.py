"""Opt-in Omen-only synthetic fit/inference contract, never benchmark evidence.

Default test runs skip this module's fit. Explicitly enable only when the optional
ML environment is prepared: $env:AFTERLIGHT_RUN_ML_TESTS='1'. No file is trained or
published; all model objects are disposable in-memory unit-test fixtures.
"""
import importlib.util
import os
import unittest
from evaluation.protocol import digest
from models.residual import feature_vector, fit_residual, predict_residual

ENABLED = os.environ.get("AFTERLIGHT_RUN_ML_TESTS") == "1" and importlib.util.find_spec("sklearn") is not None


@unittest.skipUnless(ENABLED, "optional synthetic ML contract disabled; requires explicit Omen opt-in and sklearn")
class OptionalMLContractTests(unittest.TestCase):
    def test_json_tree_matches_sklearn_predictions(self):
        from sklearn.tree import DecisionTreeRegressor
        estimator_spec = {"version": "synthetic-test-estimator", "config": {}}
        protocol = {"schema": "afterlight.protocol.v1", "source_commit": "synthetic-unit-fixture",
                    "group_assignments": {"g1": "train", "g2": "train", "v": "validation", "t": "test"},
                    "feature_schema": [{"name": "queue_sum_veh", "unit": "vehicles", "source": "synthetic unit fixture", "sensor_lag_s": 1}],
                    "civilian_weight": 1, "horizon_s": 100, "drain_end_s": 200,
                    "analytical_estimator": estimator_spec, "model_specification": {"max_depth": 3, "min_samples_leaf": 1},
                    "episode_inventory": [{"episode_id": eid, "demand_group_id": group, "split": split,
                        "demand_sha256": demand, "network_sha256": "n", "dispatch_s": 10}
                        for eid, group, split, demand in (("e1", "g1", "train", "d1"), ("e2", "g2", "train", "d2"),
                                                        ("v", "v", "validation", "dv"), ("t", "t", "test", "dt"))]}
        rows = []
        for index, queue in enumerate((1, 10), start=1):
            for lead in (0, 5, 10, 20, 30):
                rows.append({"episode_id": f"e{index}", "demand_group_id": f"g{index}", "split": "train", "lead_s": lead,
                             "source_commit": "synthetic-unit-fixture", "demand_sha256": f"d{index}", "network_sha256": "n",
                             "horizon_s": 100, "drain_end_s": 200, "status": "completed", "validity_reasons": [],
                             "ambulance_journey_s": lead + 2 * queue, "civilian_mean_excess_s": 0,
                             "accounting": {"scheduled": 1, "inserted": 1, "completed": 1, "running": 0, "not_inserted": 0},
                             "observation": {"dispatch_s": 10, "sensor_lag_s": 1, "observed_at_s": 9, "values": {"queue_sum_veh": queue}},
                             "analytical_cost_s": lead, "analytical_config_sha256": digest(estimator_spec)})
        envelope = fit_residual(rows, feature_names=["queue_sum_veh"], civilian_weight=1,
                                frozen_protocol={"sha256": digest(protocol), "protocol": protocol}, max_depth=3, min_samples_leaf=1)
        vectors = [feature_vector(r["observation"], r["lead_s"], r["analytical_cost_s"], ["queue_sum_veh"]) for r in rows]
        labels = [r["ambulance_journey_s"] - r["analytical_cost_s"] for r in rows]
        reference = DecisionTreeRegressor(max_depth=3, min_samples_leaf=1, random_state=0).fit(vectors, labels)
        for vector, expected in zip(vectors, reference.predict(vectors)):
            self.assertAlmostEqual(predict_residual(envelope, vector), expected)
        self.assertEqual(envelope["model"]["training_groups"], ["g1", "g2"])
        self.assertEqual(envelope["model"]["excluded_infeasible_labels"], 0)


if __name__ == "__main__":
    unittest.main()
