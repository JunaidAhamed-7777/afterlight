"""Pilot planning is pure; these tests never invoke the simulator."""
import unittest
from evaluation.pilot import prepare_plan, validate_plan
from evaluation.protocol import digest, pilot_summary


class PilotTests(unittest.TestCase):
    def test_default_plan_is_twelve_whole_episodes_seven_worlds(self):
        envelope = prepare_plan()
        plan = envelope["plan"]
        self.assertEqual(envelope["sha256"], digest(plan))
        self.assertEqual(plan["split"], "pilot")
        self.assertEqual(len(plan["cases"]), 12)
        self.assertEqual(len(plan["policies"]), 7)
        self.assertEqual({c["regime"] for c in plan["cases"]}, {"sparse", "moderate", "asymmetric", "heavy"})
        self.assertEqual(len({c["seed"] for c in plan["cases"]}), 12)

    def test_invalid_or_unsafe_plan_rejected_before_simulator_import(self):
        envelope = prepare_plan()
        envelope["plan"]["cases"][0]["id"] = "../escape"
        envelope["sha256"] = digest(envelope["plan"])
        with self.assertRaises(ValueError):
            validate_plan(envelope)
        envelope = prepare_plan()
        envelope["plan"]["split"] = "test"
        envelope["sha256"] = digest(envelope["plan"])
        with self.assertRaises(ValueError):
            validate_plan(envelope)

    def test_real_outcome_margin_not_only_schedule_signature(self):
        rows = []
        for eid, best in (("a", 5), ("b", 20)):
            for lead in (0, 5, 10, 20, 30):
                rows.append({"episode_id": eid, "demand_group_id": eid, "split": "pilot", "runtime_s": 1,
                    "lead_s": lead, "request_plan": [100 - lead], "status": "completed", "validity_reasons": [],
                    "ambulance_journey_s": 20 if lead == best else 30, "civilian_mean_excess_s": 0,
                    "accounting": {"scheduled": 1, "inserted": 1, "completed": 1, "running": 0, "not_inserted": 0}})
        report = pilot_summary(rows)
        self.assertEqual(report["distinct_useful_oracle_leads"], [5, 20])
        self.assertTrue(report["multiple_useful_actions_observed"])
        for row in rows:
            row["ambulance_journey_s"] = 30
        self.assertFalse(pilot_summary(rows)["multiple_useful_actions_observed"])

    def clipped_rows(self):
        return [{"episode_id": "clipped", "demand_group_id": "g", "split": "pilot", "runtime_s": 1 + lead,
                 "lead_s": lead, "request_plan": {"J": max(0, 20 - lead)},
                 "status": "completed", "validity_reasons": [],
                 "ambulance_journey_s": 10 if lead in (20, 30) else 30,
                 "civilian_mean_excess_s": 0,
                 "accounting": {"scheduled": 1, "inserted": 1, "completed": 1, "running": 0, "not_inserted": 0}}
                for lead in (0, 5, 10, 20, 30)]

    def test_duplicate_best_labels_do_not_zero_distinct_schedule_margin(self):
        rows = self.clipped_rows()
        report = pilot_summary(rows)
        episode = report["outcome_diversity_by_episode"]["clipped"]
        self.assertEqual(episode["runner_up_margin_j_s"], 20)
        self.assertEqual(episode["oracle_lead_s"], 20)
        self.assertEqual(episode["equivalent_best_leads_s"], [20, 30])
        self.assertEqual(episode["distinct_candidate_schedules"], 4)
        self.assertEqual(episode["feasible_candidates"], 5)
        self.assertEqual(episode["feasible_schedules"], 4)
        self.assertTrue(episode["useful_margin_observed"])
        self.assertFalse(report["multiple_useful_actions_observed"])

    def test_shared_best_lead_prevents_false_action_diversity(self):
        first = self.clipped_rows()  # Equivalent best leads {20, 30}.
        second = self.clipped_rows()
        for row in second:
            row["episode_id"] = "second"
            row["demand_group_id"] = "g2"
            row["request_plan"] = {"J": 100 - row["lead_s"]}
            row["ambulance_journey_s"] = 10 if row["lead_s"] == 30 else 30
        report = pilot_summary(first + second)
        self.assertEqual(report["distinct_useful_oracle_leads"], [20, 30])
        self.assertEqual(report["useful_margin_episodes"], 2)
        self.assertEqual(report["common_useful_best_leads"], [30])
        self.assertFalse(report["multiple_useful_actions_observed"])

    def test_disjoint_equivalent_best_sets_support_diversity_diagnostic(self):
        first = self.clipped_rows()  # Equivalent best leads {20, 30}.
        second = self.clipped_rows()
        for row in second:
            row["episode_id"] = "second"
            row["demand_group_id"] = "g2"
            row["request_plan"] = {"J": 100 - row["lead_s"]}
            row["ambulance_journey_s"] = 10 if row["lead_s"] == 5 else 30
        report = pilot_summary(first + second)
        self.assertEqual(report["common_useful_best_leads"], [])
        self.assertEqual(report["useful_margin_episodes"], 2)
        self.assertTrue(report["multiple_useful_actions_observed"])

    def test_conflicting_duplicate_schedule_metrics_fail_without_choosing(self):
        for field, value in (("ambulance_journey_s", 9), ("validity_reasons", ["collision"]),
                             ("queue_samples", [{"t": 0, "queue_count": 1}])):
            rows = self.clipped_rows()
            rows[-1][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "conflicting measured"):
                    pilot_summary(rows)
                # The summary never mutates/discards either retained raw row.
                self.assertEqual(len(rows), 5)
                self.assertEqual(rows[-1][field], value)

    def test_one_unique_schedule_cannot_show_a_useful_runner_up(self):
        rows = self.clipped_rows()
        for row in rows:
            row["request_plan"] = {"J": 0}
            row["ambulance_journey_s"] = 10
        report = pilot_summary(rows)
        episode = report["outcome_diversity_by_episode"]["clipped"]
        self.assertIsNone(episode["runner_up_margin_j_s"])
        self.assertEqual(episode["distinct_candidate_schedules"], 1)
        self.assertFalse(episode["useful_margin_observed"])

    def test_missing_failed_schedule_is_not_diversity(self):
        rows = [{"episode_id": "e", "demand_group_id": "g", "split": "pilot", "runtime_s": 1,
                 "lead_s": 0, "request_plan": None, "status": "infrastructure_error"}]
        self.assertEqual(pilot_summary(rows)["effective_schedules_by_episode"], {})


if __name__ == "__main__":
    unittest.main()
