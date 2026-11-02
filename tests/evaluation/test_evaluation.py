"""Synthetic unit inputs only: not simulation results or benchmark evidence."""
import tempfile
import unittest
from pathlib import Path
from evaluation.metrics import Accounting, excess_queue_area, objective, verify_pair
from evaluation.protocol import digest, freeze_protocol, pilot_summary
from evaluation.splits import assign_groups, assert_disjoint


def complete():
    return {"status": "completed", "validity_reasons": [], "ambulance_journey_s": 30,
            "civilian_mean_excess_s": 10, "accounting": {"scheduled": 2, "inserted": 2,
            "completed": 2, "running": 0, "not_inserted": 0}}


class MetricsTests(unittest.TestCase):
    def test_objective_and_infeasibility(self):
        row = complete()
        self.assertEqual(objective(row, 2), 50)
        for status in ("invalid", "censored", "infrastructure_error"):
            self.assertIsNone(objective({**row, "status": status}, 2))
        self.assertIsNone(objective({**row, "validity_reasons": ["collision"]}, 2))
        self.assertIsNone(objective({**row, "ambulance_journey_s": None}, 2))

    def test_accounting_rejects_missing_traffic(self):
        with self.assertRaises(ValueError):
            Accounting(10, 9, 8, 0, 1)
        with self.assertRaises(ValueError):
            Accounting(True, 1, 1, 0, 0)
        row = complete()
        row["accounting"] = dict(scheduled=3, inserted=2, completed=1, running=1, not_inserted=1)
        self.assertIsNone(objective(row, 1))

    def test_nonfinite_rejected(self):
        for weight in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                objective(complete(), weight)

    def test_common_window_irregular_queue_grids(self):
        p = [{"t": 0, "queue_count": 5}, {"t": 3, "queue_count": 1}, {"t": 10, "queue_count": 0}]
        b = [{"t": 0, "queue_count": 2}, {"t": 5, "queue_count": 0}, {"t": 10, "queue_count": 0}]
        self.assertEqual(excess_queue_area(p, b, 1, 8), 9)
        with self.assertRaises(ValueError):
            excess_queue_area(p, b, 0, 11)
        with self.assertRaises(ValueError):
            excess_queue_area([p[0], p[0]], b, 0, 1)

    def test_pair_provenance(self):
        row = {**complete(), "episode_id": "e", "demand_group_id": "g", "demand_sha256": "d",
               "network_sha256": "n", "horizon_s": 100, "drain_end_s": 200}
        verify_pair(row, row)
        with self.assertRaises(ValueError):
            verify_pair(row, {**row, "demand_sha256": "other"})


class SplitTests(unittest.TestCase):
    def test_group_assignment_is_order_independent(self):
        groups = [{"demand_group_id": f"g{i}", "regime": "ordinary"} for i in range(20)]
        self.assertEqual(assign_groups(groups, salt="v1"), assign_groups(groups[::-1], salt="v1"))
        groups[0]["regime"] = "heldout"
        self.assertEqual(assign_groups(groups, salt="v1", heldout_regimes=["heldout"])["g0"], "test")

    def test_dispatch_and_candidate_leakage_rejected(self):
        rows = [{"demand_group_id": "g", "episode_id": "dispatch1", "split": "train"},
                {"demand_group_id": "g", "episode_id": "dispatch2", "split": "test"}]
        with self.assertRaises(ValueError):
            assert_disjoint(rows)
        rows[1]["split"] = "train"
        self.assertEqual(assert_disjoint(rows)["train"], 1)
        with self.assertRaises(ValueError):
            assert_disjoint(rows, {"g": "validation"})


class ProtocolTests(unittest.TestCase):
    def protocol(self):
        return {"schema": "afterlight.protocol.v1", "source_commit": "test-fixture", "group_assignments":
                {"g1": "train", "g2": "validation", "g3": "test"}, "feature_schema": [{"name": "queue_sum_veh", "unit": "vehicles", "source": "lagged lane observations", "sensor_lag_s": 1}],
                "candidate_leads_s": [0, 5, 10, 20, 30], "civilian_weight": 1, "horizon_s": 100,
                "drain_end_s": 200, "recovery_window_s": [50, 200], "tie_break": "smallest_lead",
                "invalid_rules": ["collision"], "heldout_regimes": [], "model_specification": {"max_depth": 3},
                "analytical_estimator": {"version": "test-fixture", "config": {}}}

    def test_freeze_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            result = freeze_protocol(self.protocol(), path)
            self.assertEqual(result["sha256"], digest(self.protocol()))
            with self.assertRaises(FileExistsError):
                freeze_protocol(self.protocol(), path)

    def test_freeze_rejects_missing_feature_provenance(self):
        protocol = self.protocol()
        protocol["feature_schema"] = [{"name": "queue_sum_veh"}]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                freeze_protocol(protocol, Path(directory) / "protocol.json")

    def test_pilot_deduplicates_schedules_not_labels(self):
        rows = [{"episode_id": "e", "demand_group_id": "g", "split": "pilot", "runtime_s": 1,
                 "lead_s": lead, "request_plan": [10, 20], "status": "completed"} for lead in (0, 5)]
        report = pilot_summary(rows)
        self.assertEqual(report["effective_schedules_by_episode"]["e"], 1)
        self.assertEqual(report["rollouts"], 2)
        rows[0]["split"] = "test"
        with self.assertRaises(ValueError):
            pilot_summary(rows)


if __name__ == "__main__":
    unittest.main()
