"""Synthetic controller audit regressions; execute on Omen, not cloud."""
import copy
import unittest

from policies.scheduler import Scheduler, Timing
from sim.audit import audit_signal_release, audit_world_signals


def fixture(*, phase=0, request_at=0, passed_at=None, end=100, greens=('Gr', 'rG'), timing=None):
    timing = timing or Timing()
    scheduler = Scheduler('J', greens, timing=timing)
    scheduler.plan(request_at, phase, planned_at_s=0)
    frames = []
    for tick in range(round(end * 2) + 1):
        now = tick / 2
        state = scheduler.advance(now, passed=passed_at is not None and now >= passed_at)
        frames.append({'t': now, 'signals': [{'id': 'J', 'state': state}]})
    return ({'policy': 'fixed', 'events': copy.deepcopy(scheduler.events), 'frames': frames,
             'decision': {'request_plan': {'J': request_at}}, 'metrics': {'simulation_step_s': .5}},
            {'signals': {'J': {'greens': list(greens)}}}, timing)


class SignalReleaseAuditTests(unittest.TestCase):
    def check(self, arguments):
        world, network, timing = arguments
        audit_signal_release(world, network, timing, .5)

    def test_actual_shared_controller_patterns(self):
        for parameters in ({}, {'phase': 1}, {'passed_at': 2}, {'passed_at': 18},
                           {'request_at': 26, 'phase': 0, 'passed_at': 27},
                           {'request_at': 26, 'phase': 0, 'passed_at': 28.5},
                           {'request_at': 60, 'phase': 1, 'passed_at': 10},
                           {'greens': ('G',)}, {'end': 36}, {'end': 39}):
            with self.subTest(parameters=parameters):
                self.check(fixture(**parameters))

    def test_ordinary_without_priority_has_no_recovery_obligation(self):
        scheduler = Scheduler('J', ('Gr', 'rG'))
        frames = []
        for tick in range(201):
            now = tick / 2
            frames.append({'t': now, 'signals': [{'id': 'J', 'state': scheduler.advance(now)}]})
        world = {'policy': 'ordinary', 'events': scheduler.events, 'frames': frames,
                 'decision': {'request_plan': {}}, 'metrics': {'simulation_step_s': .5}}
        audit_world_signals(world, {'signals': {'J': {'greens': ['Gr', 'rG']}}}, 0)

    def test_full_signal_auditor_calls_release_guard(self):
        world, network, _ = fixture()
        result = audit_world_signals(world, network, 0)
        self.assertEqual(result['release_recovery_audit'], 'passed')

    def test_on_time_release_with_green_held_forever_rejected(self):
        world, network, timing = fixture()
        world['events'] = [e for e in world['events'] if e['kind'] not in ('yellow', 'all_red', 'recovery_requested') and not (e['kind'] == 'green' and e['t'] > 0)]
        for frame in world['frames']:
            frame['signals'][0]['state'] = 'Gr'
        with self.assertRaisesRegex(ValueError, 'never begins bounded recovery'):
            audit_world_signals(world, network, 0)

    def test_priority_label_on_wrong_phase_rejected(self):
        world, network, timing = fixture()
        onset = next(e for e in world['events'] if e['kind'] == 'priority_green')
        onset['phase'] = 1
        with self.assertRaisesRegex(ValueError, 'not the active'):
            self.check((world, network, timing))

    def test_priority_label_during_clearance_rejected(self):
        world, network, timing = fixture(phase=1)
        onset = next(e for e in world['events'] if e['kind'] == 'priority_green')
        world['events'].remove(onset)
        onset['t'] = 10
        world['events'].append(onset)
        world['events'].sort(key=lambda e: e['t'])
        with self.assertRaisesRegex(ValueError, 'not the active'):
            self.check((world, network, timing))

    def test_fake_recovery_event_without_yellow_rejected(self):
        world, network, timing = fixture()
        world['events'] = [e for e in world['events'] if not (e['kind'] == 'yellow' and e['t'] == 35)]
        with self.assertRaisesRegex(ValueError, 'yellow target'):
            self.check((world, network, timing))

    def test_recovery_green_cannot_remain_forever(self):
        world, network, timing = fixture()
        world['events'] = [e for e in world['events'] if e['t'] < 64]
        with self.assertRaisesRegex(ValueError, 'exceeded its bound'):
            self.check((world, network, timing))

    def test_final_ordinary_yellow_cannot_hang_forever(self):
        world, network, timing = fixture()
        world['events'] = [e for e in world['events'] if e['t'] <= 64]
        with self.assertRaisesRegex(ValueError, 'exceeded its bound'):
            self.check((world, network, timing))

    def test_final_ordinary_all_red_cannot_hang_forever(self):
        world, network, timing = fixture()
        world['events'] = [e for e in world['events'] if e['t'] <= 67]
        with self.assertRaisesRegex(ValueError, 'exceeded its bound'):
            self.check((world, network, timing))

    def test_final_ordinary_green_must_be_the_next_phase(self):
        world, network, timing = fixture()
        next(e for e in world['events'] if e['kind'] == 'green' and e['t'] == 68)['phase'] = 1
        with self.assertRaisesRegex(ValueError, 'exceeded its bound'):
            self.check((world, network, timing))

    def test_endpoint_during_return_to_ordinary_clearance_is_valid(self):
        for endpoint in (64, 65, 67, 67.5, 68):
            with self.subTest(endpoint=endpoint):
                self.check(fixture(end=endpoint))
                self.check(fixture(end=endpoint, greens=('G',)))

    def test_delayed_or_early_recovery_rejected(self):
        for delta in (-.5, .5):
            world, network, timing = fixture()
            next(e for e in world['events'] if e['kind'] == 'recovery_requested')['t'] += delta
            with self.assertRaisesRegex(ValueError, 'legal release boundary'):
                self.check((world, network, timing))

    def test_recovery_without_release_rejected(self):
        world, network, timing = fixture()
        world['events'] = [e for e in world['events'] if e['kind'] != 'release']
        with self.assertRaisesRegex(ValueError, 'preceding release'):
            self.check((world, network, timing))

    def test_duplicate_recovery_rejected(self):
        world, network, timing = fixture()
        world['events'].append(copy.deepcopy(next(e for e in world['events'] if e['kind'] == 'recovery_requested')))
        with self.assertRaisesRegex(ValueError, 'multiple recovery'):
            self.check((world, network, timing))

    def test_return_to_wrong_ordinary_phase_rejected(self):
        world, network, timing = fixture()
        next(e for e in world['events'] if e['kind'] == 'yellow' and e['t'] == 64)['target'] = 1
        with self.assertRaisesRegex(ValueError, 'ordinary cycling'):
            self.check((world, network, timing))

    def test_release_during_yellow_timeout_does_not_skip_clearance(self):
        self.check(fixture(phase=1, request_at=7, timing=Timing(request_timeout_s=2)))

    def test_no_step_provenance_does_not_claim_time_bounds(self):
        world, network, timing = fixture()
        world['metrics'].pop('simulation_step_s')
        result = audit_world_signals(world, network, 0)
        self.assertEqual(result['release_recovery_audit'], 'phase_binding_only_missing_integration_step')


if __name__ == '__main__':
    unittest.main()
