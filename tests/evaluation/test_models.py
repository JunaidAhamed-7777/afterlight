"""Deterministic model contract tests; no fitting or benchmark invocation."""
import unittest
from evaluation.protocol import digest
from models.residual import choose_candidate, feature_vector, fit_residual, predict_residual, select_fixed_lead, validate_candidate_rows


def observation():
    return {"dispatch_s": 20, "sensor_lag_s": 1, "observed_at_s": 19, "values": {"queue_sum_veh": 3}}


def candidates(split="validation"):
    return [{"episode_id": "e", "demand_group_id": "g", "split": split, "lead_s": lead,
             "observation": observation(), "demand_sha256": "d", "network_sha256": "n",
             "horizon_s": 100, "drain_end_s": 200, "status": "completed", "validity_reasons": [],
             "ambulance_journey_s": 30 + lead, "civilian_mean_excess_s": 5,
             "accounting": {"scheduled": 2, "inserted": 2, "completed": 2, "running": 0, "not_inserted": 0}}
            for lead in (0, 5, 10, 20, 30)]


class ModelContractTests(unittest.TestCase):
    def test_lag_and_feature_allowlist(self):
        self.assertEqual(feature_vector(observation(), 5, 8, ["queue_sum_veh"]), [3, 5, 8])
        with self.assertRaises(ValueError):
            feature_vector({**observation(), "observed_at_s": 20}, 5, 8, ["queue_sum_veh"])
        with self.assertRaises(ValueError):
            feature_vector(observation(), 5, 8, ["seed"])
        with self.assertRaises(ValueError):
            feature_vector({**observation(), "values": {"queue_sum_veh": 3, "future_departures": 8}}, 5, 8, ["queue_sum_veh"])

    def test_fixed_lead_requires_all_validation_candidates(self):
        self.assertEqual(select_fixed_lead(candidates(), 1)["lead_s"], 0)
        with self.assertRaises(ValueError):
            select_fixed_lead(candidates("test"), 1)
        with self.assertRaises(ValueError):
            validate_candidate_rows(candidates()[:-1])
        rows = candidates()
        rows[0]["observation"] = {**observation(), "observed_at_s": 18}
        with self.assertRaises(ValueError):
            validate_candidate_rows(rows)

    def test_failed_lead_is_not_rewarded_by_dropped_episode(self):
        rows = candidates()
        rows[0]["status"] = "censored"
        result = select_fixed_lead(rows, 1)
        self.assertEqual(result["lead_s"], 5)
        self.assertFalse(result["conclusive"])
        rows[0]["status"] = "infrastructure_error"
        with self.assertRaises(ValueError):
            select_fixed_lead(rows, 1)

    def test_fixed_lead_mean_avoids_sum_overflow(self):
        rows = candidates()
        second = candidates()
        for row in second:
            row["episode_id"] = "e2"
        for row in rows + second:
            row["ambulance_journey_s"] = 1e308
            row["civilian_mean_excess_s"] = 0
        report = select_fixed_lead(rows + second, 1)
        self.assertEqual(report["scores"][0]["common_feasible_mean_j_s"], 1e308)

    def test_fixed_lead_compares_common_feasible_cohort(self):
        rows = candidates()
        second = candidates()
        for row in second:
            row["episode_id"] = "hard"
            row["demand_group_id"] = "g2"
            row["demand_sha256"] = "d2"
            row["ambulance_journey_s"] = 1000 if row["lead_s"] == 0 else 40
        # Lead 30 fails the hard episode, so no lead may improve its conditional
        # mean by silently dropping that episode. All score means use easy e.
        second[-1]["status"] = "censored"
        report = select_fixed_lead(rows + second, 1)
        self.assertEqual(report["common_feasible_episodes"], 1)
        self.assertEqual(report["lead_s"], 0)
        self.assertEqual(report["scores"][0]["common_feasible_mean_j_s"], 35)

    def test_fit_rejects_relabelled_heldout_group_before_importing_sklearn(self):
        protocol = {"group_assignments": {"g": "test"}, "feature_schema": [{"name": "queue_sum_veh"}],
                    "civilian_weight": 1, "model_specification": {"max_depth": 3, "min_samples_leaf": 5}}
        envelope = {"sha256": digest(protocol), "protocol": protocol}
        with self.assertRaises(ValueError):
            fit_residual(candidates("train"), feature_names=["queue_sum_veh"], civilian_weight=1, frozen_protocol=envelope)
        protocol["group_assignments"]["g"] = "train"
        # Changed content without re-freezing must not be accepted.
        with self.assertRaises(ValueError):
            fit_residual(candidates("train"), feature_names=["queue_sum_veh"], civilian_weight=1, frozen_protocol=envelope)

    def test_units_and_boolean_action_rejected(self):
        with self.assertRaises(ValueError):
            feature_vector({**observation(), "values": {"downstream_occupancy": 50}}, 5, 10, ["downstream_occupancy"])
        rows = candidates()
        rows[0]["lead_s"] = False
        with self.assertRaises(ValueError):
            validate_candidate_rows(rows)

    def test_analytical_selection_tie_break(self):
        choice = choose_candidate(observation(), dict.fromkeys((0, 5, 10, 20, 30), 10), ["queue_sum_veh"])
        self.assertEqual(choice["lead_s"], 0)
        self.assertTrue(choice["prediction_not_measurement"])

    def test_json_tree_hash_and_cycle_checks(self):
        model = {"schema": "afterlight.residual-tree.v1", "feature_names": ["queue_sum_veh"],
                 "nodes": [{"left": -1, "right": -1, "feature": -2, "threshold": -2, "value": -3}]}
        envelope = {"sha256": digest(model), "model": model}
        self.assertEqual(predict_residual(envelope, [3, 5, 8]), -3)
        model["nodes"][0]["value"] = 4
        with self.assertRaises(ValueError):
            predict_residual(envelope, [3, 5, 8])
        model["nodes"] = [{"left": 0, "right": 0, "feature": 0, "threshold": 3, "value": 1}]
        with self.assertRaises(ValueError):
            predict_residual({"sha256": digest(model), "model": model}, [3, 5, 8])


if __name__ == "__main__":
    unittest.main()
