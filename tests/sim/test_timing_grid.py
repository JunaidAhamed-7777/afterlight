"""Pure controller-grid contract tests; execute only on designated Omen host."""
import unittest
from policies.scheduler import Timing
from sim.run import validate_timing_grid


class TimingGridTests(unittest.TestCase):
    def test_default_and_finer_exact_grids_are_supported(self):
        for step in (.5, .25, .1, 1.0):
            with self.subTest(step=step):
                validate_timing_grid(step)

    def test_grid_that_extends_hold_or_transition_is_rejected(self):
        for step in (2.0, .4, 3.0):
            with self.subTest(step=step), self.assertRaisesRegex(ValueError, 'must divide'):
                validate_timing_grid(step)

    def test_invalid_steps_are_rejected(self):
        for step in (0, -1, float('nan'), float('inf')):
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate_timing_grid(step)

    def test_custom_controller_duration_is_checked(self):
        with self.assertRaisesRegex(ValueError, 'max_hold_s'):
            validate_timing_grid(.5, Timing(max_hold_s=35.25))


if __name__ == '__main__':
    unittest.main()
