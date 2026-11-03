"""Binary-float boundary fixtures; execute only on designated Omen host."""
import math
import unittest
from policies.scheduler import Scheduler, TIME_EPSILON_S, deadline_reached


class SchedulerPrecisionTests(unittest.TestCase):
    def test_duration_tie_tolerance_is_absolute_and_sub_audit(self):
        self.assertLess(TIME_EPSILON_S, 1e-8)
        self.assertTrue(deadline_reached(math.nextafter(35.1, -math.inf), .1, 35))
        self.assertFalse(deadline_reached(35.1-1e-6, .1, 35))
        self.assertFalse(deadline_reached(100000-1e-6, 0, 100000))

    def test_min_green_yellow_and_all_red_do_not_wait_extra_tick(self):
        s = Scheduler('J', ('Gr', 'rG'))
        s.plan(0, 1)
        self.assertEqual(s.advance(8-1e-6), 'Gr')
        self.assertEqual(s.advance(math.nextafter(8, -math.inf)), 'yr')
        self.assertEqual(s.advance(11-1e-6), 'yr')
        self.assertEqual(s.advance(math.nextafter(11, -math.inf)), 'rr')
        self.assertEqual(s.advance(12-1e-6), 'rr')
        self.assertEqual(s.advance(math.nextafter(12, -math.inf)), 'rG')

    def test_max_hold_preserves_actual_timestamp_at_float_boundary(self):
        s = Scheduler('J', ('Gr', 'rG'))
        s.plan(.1, 0)
        s.advance(.1)
        s.advance(35.1-1e-6)
        self.assertFalse(s.request.released)
        now = math.nextafter(35.1, -math.inf)
        s.advance(now)
        event = next(e for e in s.events if e['kind'] == 'release')
        self.assertEqual(event['reason'], 'max_hold')
        self.assertEqual(event['t'], now)

    def test_request_activation_and_timeout_roundoff_only(self):
        s = Scheduler('J', ('Gr', 'rG'))
        s.plan(.1, 1)
        s.advance(.1-1e-6)
        self.assertFalse(any(e['kind'] == 'request' for e in s.events))
        s.advance(math.nextafter(.1, -math.inf))
        self.assertTrue(any(e['kind'] == 'request' for e in s.events))
        s.advance(math.nextafter(90.1, -math.inf))
        self.assertTrue(s.request.released)
        self.assertEqual(next(e['reason'] for e in s.events if e['kind'] == 'release'), 'request_timeout')

    def test_ordinary_cycle_boundary_uses_same_tolerance(self):
        s = Scheduler('J', ('Gr', 'rG'))
        self.assertEqual(s.advance(25-1e-6), 'Gr')
        self.assertEqual(s.advance(math.nextafter(25, -math.inf)), 'yr')


if __name__ == '__main__':
    unittest.main()
