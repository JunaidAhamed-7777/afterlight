import unittest
from policies.scheduler import Scheduler, Timing
from policies.timing import request_plan, distinct_schedules


class SchedulerTests(unittest.TestCase):
    def test_zero_lead_is_not_immediate(self):
        self.assertEqual(request_plan(30, {'J': 60}, lead_s=0), {'J': 60})
        self.assertEqual(request_plan(30, {'J': 60}, immediate=True), {'J': 30})
        self.assertEqual(request_plan(30, {'J': 40}, lead_s=30), {'J': 30})

    def test_transition_honors_minimum_yellow_all_red(self):
        s = Scheduler('J', ('GGrr', 'rrGG'))
        s.plan(0, 1)
        self.assertEqual(s.advance(7), 'GGrr')
        self.assertEqual(s.advance(8), 'yyrr')
        self.assertEqual(s.advance(10), 'yyrr')
        self.assertEqual(s.advance(11), 'rrrr')
        self.assertEqual(s.advance(11.5), 'rrrr')
        self.assertEqual(s.advance(12), 'rrGG')
        self.assertEqual(s.advance(12.5), 'rrGG')
        self.assertEqual(s.request.onset_s, 12)

    def test_priority_hold_is_finite(self):
        s = Scheduler('J', ('GGrr', 'rrGG'))
        s.plan(0, 0)
        for i in range(100):
            s.advance(i)
        self.assertTrue(s.request.released)
        self.assertIn('max_hold', [e.get('reason') for e in s.events])
        self.assertTrue(any(e['kind'] == 'green' and e['phase'] == 1 for e in s.events))

    def test_passage_releases_and_does_not_skip_min_green(self):
        s = Scheduler('J', ('GGrr', 'rrGG'))
        s.plan(0, 0)
        s.advance(0)
        self.assertEqual(s.advance(2, passed=True), 'GGrr')
        self.assertEqual(s.advance(8), 'yyrr')

    def test_passage_cancels_not_yet_due_request(self):
        s = Scheduler('J', ('GGrr', 'rrGG'))
        s.plan(60, 1)
        s.advance(10, passed=True)
        self.assertTrue(s.request.released)
        self.assertFalse(s.recovering)
        s.advance(60)
        self.assertFalse(any(e['kind'] == 'request' for e in s.events))

    def test_ordinary_has_no_recovery(self):
        s = Scheduler('J', ('GGrr', 'rrGG'))
        for t in range(100):
            s.advance(t)
        self.assertFalse(any('recovery' in e['kind'] for e in s.events))

    def test_rejects_backwards_time_and_bad_state(self):
        s = Scheduler('J', ('GGrr', 'rrGG'))
        s.advance(2)
        with self.assertRaises(ValueError): s.advance(1)
        with self.assertRaises(ValueError): Scheduler('J', ('yyyy',))
        with self.assertRaises(ValueError): Timing(yellow_s=0)

    def test_deduplicates_clipped_schedules(self):
        self.assertEqual(len(distinct_schedules(0, {'J': 0})), 1)


if __name__ == '__main__':
    unittest.main()
