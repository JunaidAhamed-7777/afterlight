"""Synthetic selector-freeze guards, not real validation or held-out evidence."""
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from evaluation.comparison import paired_decision_report
from evaluation.protocol import digest
from evaluation.selectors import analytical_artifact, fixed_lead_artifact, freeze_selectors, recompute_frozen_decisions
from models.analytical import AnalyticalConfig, estimate_candidates
from models.residual import DEFAULT_FEATURES


def fixtures():
    config = AnalyticalConfig()
    protocol = {"schema": "afterlight.protocol.v1", "source_commit": "synthetic-fixture", "civilian_weight": 1,
                "group_assignments": {"training": "train", "validation": "validation", "heldout": "test"},
                "feature_schema": [{"name": n, "unit": "fixture", "source": "synthetic", "sensor_lag_s": 1} for n in DEFAULT_FEATURES],
                "horizon_s": 100, "drain_end_s": 200,
                "analytical_estimator": {"version": "queue-lost-service-v1", "config": asdict(config)},
                "episode_inventory": [{"episode_id": group, "demand_group_id": group, "split": split,
                    "demand_sha256": group, "network_sha256": "network", "dispatch_s": 20}
                    for group, split in (("training", "train"), ("validation", "validation"), ("heldout", "test"))]}
    envelope = {"sha256": digest(protocol), "protocol": protocol}
    observation = {"dispatch_s": 20, "sensor_lag_s": 1, "observed_at_s": 19, "values": {
        "queue_sum_veh": 10, "queue_max_veh": 10, "downstream_occupancy": 0,
        "route_distance_m": 500, "route_junction_count": 3, "eta_remaining_s": 40, "phase_elapsed_s": 2}}
    costs = {r["lead_s"]: r["analytical_cost_s"] for r in estimate_candidates(observation)["scores"]}
    def rows(group, split):
        return [{"episode_id": group, "demand_group_id": group, "split": split, "lead_s": lead,
                 "source_commit": "synthetic-fixture", "demand_sha256": group, "network_sha256": "network",
                 "horizon_s": 100, "drain_end_s": 200, "status": "completed", "validity_reasons": [],
                 "ambulance_journey_s": 20 + (lead - 5)**2, "civilian_mean_excess_s": 0,
                 "accounting": {"scheduled": 1, "inserted": 1, "completed": 1, "running": 0, "not_inserted": 0},
                 "observation": observation, "analytical_cost_s": costs[lead],
                 "analytical_config_sha256": digest(protocol["analytical_estimator"])} for lead in (0, 5, 10, 20, 30)]
    return envelope, rows("validation", "validation"), rows("heldout", "test")


class SelectorFreezeTests(unittest.TestCase):
    def test_frozen_selectors_recompute_actions_and_reject_oracle_map(self):
        protocol, validation, heldout = fixtures()
        selected = fixed_lead_artifact(validation, protocol)
        comparator = analytical_artifact(protocol)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selectors.json"
            frozen = freeze_selectors(protocol, selected, comparator, path)
            chosen, baseline = recompute_frozen_decisions(heldout, protocol, frozen)
            report = paired_decision_report(heldout, chosen, baseline, civilian_weight=1,
                                           frozen_protocol=protocol, frozen_selectors=frozen)
            self.assertEqual(chosen, {"heldout": 5})
            self.assertEqual(report["selector_freeze_sha256"], frozen["sha256"])
            self.assertEqual(report["evaluation_mode"], "test_protocol_bound")
            with self.assertRaises(ValueError):
                paired_decision_report(heldout, {"heldout": 0}, baseline, civilian_weight=1,
                                       frozen_protocol=protocol, frozen_selectors=frozen)
            with self.assertRaises(FileExistsError):
                freeze_selectors(protocol, selected, comparator, path)

    def test_analytical_scores_and_lag_must_match_frozen_inputs(self):
        protocol, validation, heldout = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            artifact = analytical_artifact(protocol)
            frozen = freeze_selectors(protocol, artifact, artifact, Path(directory) / "selectors.json")
            heldout[0]["analytical_cost_s"] += 1
            with self.assertRaises(ValueError):
                recompute_frozen_decisions(heldout, protocol, frozen)
            protocol, validation, heldout = fixtures()
            heldout[0]["observation"]["sensor_lag_s"] = 0
            with self.assertRaises(ValueError):
                recompute_frozen_decisions(heldout, protocol, frozen)

    def test_fixed_lead_cannot_be_selected_on_test_rows(self):
        protocol, validation, heldout = fixtures()
        with self.assertRaises(ValueError):
            fixed_lead_artifact(heldout, protocol)


if __name__ == "__main__":
    unittest.main()
