"""Synthetic causal-contract fixtures only; no simulator or performance claims."""
from copy import deepcopy
import unittest

from sim.audit import audit_paired_dispatch


def paired_fixture(policy='fixed', lead=10):
    observation = {'dispatch_s': 10, 'sensor_lag_s': 1, 'observed_at_s': 9,
                   'values': {'queue_sum_veh': 2, 'queue_max_veh': 2, 'downstream_occupancy': .2,
                              'route_distance_m': 100, 'route_junction_count': 2,
                              'eta_remaining_s': 30, 'phase_elapsed_s': 4}}
    etas = {'J1': 12, 'J2': 40}
    worlds = {}
    for name, choice in (('baseline', 'ordinary'), ('afterlight', policy)):
        selected = lead if choice in ('fixed', 'analytical') else None
        plan = {} if choice == 'ordinary' else ({j: 10 for j in etas} if choice == 'immediate'
                else {j: max(10, eta-lead) for j, eta in etas.items()})
        decision = {'t': 10, 'kind': 'dispatch', 'policy': choice, 'selected_lead_s': selected,
                    'observation': deepcopy(observation), 'absolute_etas': dict(etas), 'request_plan': plan,
                    'candidate_prediction': {'version': 'synthetic, never execute', 'label': name}}
        worlds[name] = {'policy': choice, 'lead_s': selected, 'decision': decision,
            'frames': [{'t': t, 'vehicles': [{'id': 'civilian', 'x': t}],
                        'signals': [{'id': 'J1', 'state': 'G' if name == 'afterlight' and t >= 10 else 'r'}]}
                       for t in (0, 5, 10, 11)],
            'events': [{'t': 0, 'kind': 'green', 'junction': 'J1', 'phase': 0}, decision]}
    return {'scenario': {'dispatch_s': 10}, 'worlds': worlds}


class PairedDispatchTests(unittest.TestCase):
    def test_all_current_policy_modes_and_candidate_leads(self):
        for policy in ('ordinary', 'immediate', 'fixed', 'analytical'):
            for lead in (0, 5, 10, 20, 30):
                with self.subTest(policy=policy, lead=lead):
                    result = audit_paired_dispatch(paired_fixture(policy, lead))
                    self.assertEqual(result['frozen_request_timing'], {'baseline': 'passed', 'afterlight': 'passed'})
                    self.assertEqual(result['pre_dispatch_frames'], 2)

    def test_dispatch_boundary_and_later_world_divergence_are_allowed(self):
        replay = paired_fixture()
        world = replay['worlds']['afterlight']
        world['frames'][2]['vehicles'][0]['x'] = 999
        world['events'].append({'t': 10, 'kind': 'request', 'junction': 'J1'})
        audit_paired_dispatch(replay)

    def test_pre_dispatch_traffic_signal_and_event_divergence_rejected(self):
        for mutate in (lambda w: w['frames'][1]['vehicles'][0].update(x=999),
                       lambda w: w['frames'][1]['signals'][0].update(state='G'),
                       lambda w: w['events'][0].update(phase=1),
                       lambda w: w['frames'].pop(1)):
            replay = paired_fixture(); mutate(replay['worlds']['afterlight'])
            with self.assertRaisesRegex(ValueError, 'before dispatch'):
                audit_paired_dispatch(replay)

    def test_shared_observation_and_absolute_etas_must_match(self):
        for field in ('observation', 'absolute_etas'):
            replay = paired_fixture()
            decision = replay['worlds']['afterlight']['decision']
            if field == 'observation': decision[field]['values']['queue_sum_veh'] = 3
            else:
                decision[field]['J2'] = 41
                decision['request_plan']['J2'] = 31
            with self.assertRaisesRegex(ValueError, field): audit_paired_dispatch(replay)

    def test_zero_lead_is_not_immediate(self):
        replay = paired_fixture('fixed', 0)
        replay['worlds']['afterlight']['decision']['request_plan'] = {'J1': 10, 'J2': 10}
        with self.assertRaisesRegex(ValueError, 'formula'): audit_paired_dispatch(replay)

    def test_clipping_at_dispatch_and_each_junction_is_checked(self):
        replay = paired_fixture('fixed', 20)
        self.assertEqual(replay['worlds']['afterlight']['decision']['request_plan'], {'J1': 10, 'J2': 20})
        audit_paired_dispatch(replay)
        replay['worlds']['afterlight']['decision']['request_plan']['J1'] = 9
        with self.assertRaisesRegex(ValueError, 'formula'): audit_paired_dispatch(replay)

    def test_missing_extra_and_shifted_request_entries_rejected(self):
        for plan in ({'J1': 10}, {'J1': 10, 'J2': 30, 'extra': 30}, {'J1': 10, 'J2': 31}):
            replay = paired_fixture(); replay['worlds']['afterlight']['decision']['request_plan'] = plan
            with self.assertRaisesRegex(ValueError, 'formula'): audit_paired_dispatch(replay)

    def test_ordinary_has_no_priority_and_immediate_uses_dispatch(self):
        for policy, plan in (('ordinary', {'J1': 10}), ('immediate', {'J1': 12, 'J2': 40})):
            replay = paired_fixture(policy); replay['worlds']['afterlight']['decision']['request_plan'] = plan
            with self.assertRaisesRegex(ValueError, 'formula'): audit_paired_dispatch(replay)

    def test_sensor_lag_is_nonnegative_finite_and_causal_in_both_worlds(self):
        for name in ('baseline', 'afterlight'):
            for field, value in (('sensor_lag_s', -1), ('sensor_lag_s', float('nan')),
                                 ('sensor_lag_s', True), ('observed_at_s', 9.5),
                                 ('observed_at_s', -1), ('observed_at_s', float('inf')),
                                 ('dispatch_s', 11)):
                replay = paired_fixture(); replay['worlds'][name]['decision']['observation'][field] = value
                with self.subTest(world=name, field=field, value=value), self.assertRaises(ValueError):
                    audit_paired_dispatch(replay)

    def test_existing_zero_lag_contract_is_preserved(self):
        replay = paired_fixture()
        for world in replay['worlds'].values():
            world['decision']['observation'].update(sensor_lag_s=0, observed_at_s=10)
        audit_paired_dispatch(replay)

    def test_canonical_feature_schema_rejects_future_extra_and_invalid_values(self):
        for key, value in (('future_arrivals', 4), ('downstream_occupancy', 1.1),
                           ('route_junction_count', 1.5), ('route_junction_count', True)):
            replay = paired_fixture()
            replay['worlds']['afterlight']['decision']['observation']['values'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                audit_paired_dispatch(replay)
        replay = paired_fixture()
        del replay['worlds']['afterlight']['decision']['observation']['values']['phase_elapsed_s']
        with self.assertRaises(ValueError): audit_paired_dispatch(replay)

    def test_nonfinite_features_and_past_absolute_etas_rejected(self):
        for value in (float('inf'), float('nan'), True, -1):
            replay = paired_fixture()
            replay['worlds']['afterlight']['decision']['observation']['values']['queue_sum_veh'] = value
            with self.assertRaises(ValueError): audit_paired_dispatch(replay)
        replay = paired_fixture(); replay['worlds']['afterlight']['decision']['absolute_etas']['J1'] = 9
        with self.assertRaisesRegex(ValueError, 'at or after dispatch'): audit_paired_dispatch(replay)

    def test_world_selected_lead_and_policy_identities_agree(self):
        for lead in (True, 7, None):
            replay = paired_fixture(); replay['worlds']['afterlight']['decision']['selected_lead_s'] = lead
            with self.assertRaises(ValueError): audit_paired_dispatch(replay)
        replay = paired_fixture(); replay['worlds']['afterlight']['lead_s'] = 20
        with self.assertRaises(ValueError): audit_paired_dispatch(replay)
        replay = paired_fixture(); replay['worlds']['afterlight']['decision']['policy'] = 'ordinary'
        with self.assertRaises(ValueError): audit_paired_dispatch(replay)

    def test_decision_time_and_unique_event_are_bound(self):
        replay = paired_fixture(); replay['worlds']['afterlight']['decision']['t'] = 11
        with self.assertRaisesRegex(ValueError, 'frozen at dispatch'): audit_paired_dispatch(replay)
        for duplicate in (False, True):
            replay = paired_fixture(); world = replay['worlds']['afterlight']
            if duplicate: world['events'].append(deepcopy(world['decision']))
            else: world['events'] = world['events'][:1]
            with self.assertRaisesRegex(ValueError, 'unique frozen decision'): audit_paired_dispatch(replay)

    def test_prediction_version_is_not_recomputed_or_required_to_match(self):
        replay = paired_fixture('analytical')
        replay['worlds']['afterlight']['decision']['candidate_prediction'] = {'version': 'another frozen predictor'}
        audit_paired_dispatch(replay)

    def test_future_policy_label_has_explicit_limited_timing_coverage(self):
        replay = paired_fixture()
        world = replay['worlds']['afterlight']; world['policy'] = world['decision']['policy'] = 'future-selector'
        result = audit_paired_dispatch(replay)
        self.assertEqual(result['frozen_request_timing']['afterlight'], 'not_checked_for_policy')

    def test_zero_controlled_junction_route_is_supported(self):
        replay = paired_fixture()
        for world in replay['worlds'].values():
            world['decision']['absolute_etas'] = {}
            world['decision']['request_plan'] = {}
        audit_paired_dispatch(replay)


if __name__ == '__main__': unittest.main()
