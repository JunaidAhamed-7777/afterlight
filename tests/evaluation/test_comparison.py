"""Synthetic accounting/aggregation checks; no measured traffic outcomes."""
import unittest
from evaluation.comparison import grouped_bootstrap_interval, paired_decision_report
def observation():
    return {"dispatch_s": 20, "sensor_lag_s": 1, "observed_at_s": 19, "values": {"queue_sum_veh": 3}}


def candidates(split="validation"):
    return [{"episode_id": "e", "demand_group_id": "g", "split": split, "lead_s": lead,
             "observation": observation(), "demand_sha256": "d", "network_sha256": "n",
             "horizon_s": 100, "drain_end_s": 200, "status": "completed", "validity_reasons": [],
             "ambulance_journey_s": 30 + lead, "civilian_mean_excess_s": 5,
             "accounting": {"scheduled": 2, "inserted": 2, "completed": 2, "running": 0, "not_inserted": 0}}
            for lead in (0, 5, 10, 20, 30)]



class ComparisonTests(unittest.TestCase):
    def test_all_episodes_retained_and_failure_headlines(self):
        rows = candidates("test")
        rows[0]["status"] = "censored"
        report = paired_decision_report(rows, {"e": 0}, {"e": 5}, civilian_weight=1)
        self.assertEqual(report["episodes"], 1)
        self.assertEqual(report["selected_failures"], 1)
        self.assertEqual(report["comparator_failures"], 0)
        self.assertIsNone(report["conditional_mean_delta_j_s"])
        self.assertEqual(report["paired_feasible_episodes"], 0)

    def test_paired_direction_and_oracle_only_regret(self):
        report = paired_decision_report(candidates("test"), {"e": 5}, {"e": 10}, civilian_weight=1)
        self.assertEqual(report["conditional_mean_delta_j_s"], -5)
        self.assertEqual(report["records"][0]["conditional_regret_s"], 5)
        self.assertEqual(report["conditional_improved_fraction"], 1)
        with self.assertRaises(ValueError):
            paired_decision_report(candidates("test"), {}, {"e": 10}, civilian_weight=1)

    def test_group_uncertainty_refuses_per_second_pseudoreplication(self):
        records = [{"demand_group_id": "same", "paired_delta_j_s": i} for i in range(100)]
        self.assertIsNone(grouped_bootstrap_interval(records)["interval"])
        records = [{"demand_group_id": str(i), "paired_delta_j_s": -5} for i in range(12)]
        report = grouped_bootstrap_interval(records, resamples=100)
        self.assertEqual(report["interval"], [-5, -5])


if __name__ == "__main__":
    unittest.main()
