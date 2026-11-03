"""Algebraic synthetic checks only; not empirical action diversity or policy gain."""
import itertools
import math
import unittest
from models.analytical import AnalyticalConfig, ESTIMATOR_VERSION, _queue_residual_bounds, estimate_candidates


def observed(total=10, maximum=10, count=3, occupancy=0):
    return {'dispatch_s':60,'sensor_lag_s':1,'observed_at_s':59,'values':{
        'queue_sum_veh':total,'queue_max_veh':maximum,'downstream_occupancy':occupancy,
        'route_distance_m':400,'route_junction_count':count,'eta_remaining_s':40+2*total,'phase_elapsed_s':2}}


def score(snapshot,lead=10,config=AnalyticalConfig()):
    return next(row for row in estimate_candidates(snapshot,config)['scores'] if row['lead_s']==lead)


class AnalyticalRevisionTests(unittest.TestCase):
    def test_single_busy_junction_cannot_borrow_empty_junction_service(self):
        row=score(observed())
        self.assertEqual(row['effective_service_per_junction_s'],6)
        self.assertEqual(row['residual_queue_delay_bounds_s'],{'optimistic':14,'conservative':14})
        self.assertEqual(row['predicted_ambulance_s'],54)
        self.assertEqual(row['predicted_ambulance_s'],score(observed(count=1))['predicted_ambulance_s'])

    def test_equal_sum_with_different_concentration_changes_residual_not_freeflow(self):
        concentrated=score(observed(30,30,3))
        distributed=score(observed(30,10,3))
        self.assertEqual(concentrated['predicted_ambulance_s'],94)
        self.assertEqual(distributed['predicted_ambulance_s'],82)
        self.assertEqual(concentrated['predicted_civilian_delay_surrogate_s'],distributed['predicted_civilian_delay_surrogate_s'])

    def test_unknown_distribution_exposes_both_bounds(self):
        row=score(observed(17,10,3))
        self.assertEqual(row['residual_queue_delay_bounds_s'],{'optimistic':16,'conservative':22})
        self.assertEqual(row['predicted_ambulance_s'],62)

    def test_small_exhaustive_allocations_respect_surrogate_bounds(self):
        # Pure integer queues, no simulation or future information. Convex
        # concentration upper bound should match the worst feasible allocation.
        groups={}
        for queues in itertools.product(range(4),repeat=3):
            groups.setdefault((sum(queues),max(queues)),[]).append(queues)
        for (total,maximum),allocations in groups.items():
            for service in (0,1,2.5,6):
                with self.subTest(total=total,maximum=maximum,service=service):
                    low,high=_queue_residual_bounds(total,maximum,3,2,service)
                    residuals=[sum(max(0,2*q-service) for q in queues) for queues in allocations]
                    self.assertLessEqual(low,min(residuals)+1e-12)
                    self.assertAlmostEqual(high,max(residuals))
                    self.assertLessEqual(low,high)

    def test_occupancy_one_prevents_predicted_discharge(self):
        for row in estimate_candidates(observed(17,10,3,1))['scores']:
            self.assertEqual(row['predicted_ambulance_s'],74)
            self.assertEqual(row['residual_queue_delay_bounds_s'],{'optimistic':34,'conservative':34})

    def test_zero_junction_route_has_no_queue_service_or_civilian_penalty(self):
        for row in estimate_candidates(observed(0,0,0))['scores']:
            self.assertEqual(row['predicted_ambulance_s'],40)
            self.assertEqual(row['predicted_civilian_delay_surrogate_s'],0)

    def test_inconsistent_aggregates_are_rejected_not_clamped(self):
        for total,maximum,count in ((1,2,3),(10,2,3),(2,0,3),(1,1,0)):
            with self.subTest(total=total,maximum=maximum,count=count),self.assertRaises(ValueError):
                estimate_candidates(observed(total,maximum,count))

    def test_eta_shorter_than_its_observed_queue_component_is_rejected(self):
        snapshot=observed();snapshot['values']['eta_remaining_s']=19
        with self.assertRaisesRegex(ValueError,'ETA'):estimate_candidates(snapshot)

    def test_custom_service_headway_does_not_rewrite_fixed_eta_component(self):
        snapshot=observed()
        row=score(snapshot,10,AnalyticalConfig(queue_headway_s=3))
        # Frozen ETA remains 40 freeflow + 2*10 observed queue seconds.
        # Custom predictor instead leaves 3*10 - 6 = 24 queue seconds.
        self.assertEqual(row['predicted_ambulance_s'],64)
        self.assertEqual(score(snapshot,0,AnalyticalConfig(queue_headway_s=3))['predicted_ambulance_s'],70)
        self.assertEqual(estimate_candidates(snapshot)['eta_queue_headway_s'],2)
        snapshot['values']['eta_remaining_s']=19
        with self.assertRaisesRegex(ValueError,'ETA'):
            estimate_candidates(snapshot,AnalyticalConfig(queue_headway_s=1))

    def test_phase_stage_elapsed_is_not_assumed_green_age(self):
        a=observed();b=observed();b['values']['phase_elapsed_s']=100
        self.assertEqual(estimate_candidates(a)['scores'],estimate_candidates(b)['scores'])

    def test_intermediate_overflow_fails_closed(self):
        for changes in ({'route_junction_count':1e308,'queue_max_veh':2,'queue_sum_veh':2},
                        {'queue_sum_veh':1e308,'queue_max_veh':1e308,'route_junction_count':1,'eta_remaining_s':1e308}):
            snapshot=observed();snapshot['values'].update(changes)
            with self.assertRaises(ValueError):estimate_candidates(snapshot)
        with self.assertRaises(ValueError):estimate_candidates(observed(),AnalyticalConfig(civilian_cost_scale=1e308))

    def test_large_finite_cycle_does_not_overflow_denominator(self):
        rows=estimate_candidates(observed(),AnalyticalConfig(ordinary_cycle_s=1e308))['scores']
        self.assertTrue(all(math.isfinite(row['analytical_cost_s']) for row in rows))
        self.assertGreater(rows[-1]['predicted_civilian_delay_surrogate_s'],0)

    def test_prediction_and_version_disclosure(self):
        result=estimate_candidates(observed())
        self.assertEqual(result['version'],ESTIMATOR_VERSION)
        self.assertEqual(ESTIMATOR_VERSION,'queue-concentration-v2')
        self.assertTrue(result['prediction_not_measurement'])
        self.assertFalse(result['uses_future_demand'])
