"""Pure timing aggregation contract; no actual benchmark or model execution."""
import unittest
from scripts.benchmark_frozen_selector import timing_summary


class TimingSummaryTests(unittest.TestCase):
    def test_nearest_rank_p95_keeps_outlier_and_uses_call_population(self):
        result=timing_summary([1_000_000]*19+[100_000_000])
        self.assertEqual(result['samples'],20)
        self.assertEqual(result['median_ms'],1)
        self.assertEqual(result['p95_ms'],1)
        self.assertEqual(result['max_ms'],100)
        self.assertAlmostEqual(result['mean_ms'],5.95)

    def test_invalid_or_empty_samples_cannot_be_reported(self):
        for value in ([],[True],[-1],[1.5],[float('nan')]):
            with self.subTest(value=value),self.assertRaises(ValueError):timing_summary(value)


if __name__=='__main__':unittest.main()
