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

    def test_missing_failed_schedule_is_not_diversity(self):
        rows = [{"episode_id": "e", "demand_group_id": "g", "split": "pilot", "runtime_s": 1,
                 "lead_s": 0, "request_plan": None, "status": "infrastructure_error"}]
        self.assertEqual(pilot_summary(rows)["effective_schedules_by_episode"], {})


if __name__ == "__main__":
    unittest.main()
