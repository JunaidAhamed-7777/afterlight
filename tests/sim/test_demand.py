import unittest
from sim.demand import project_to_lane


class DemandTests(unittest.TestCase):
    def test_projects_actual_clipped_lane_not_fraction(self):
        # Canonical road [0,100], clipped SUMO lane [10,90]; curb x25
        # must produce lane arclength15, not canonical fraction .25*80=20.
        position, error = project_to_lane([25, 5, 0], [[10,0],[90,0]])
        self.assertEqual(position, 15)
        self.assertEqual(error, 5)

    def test_multisegment_projection(self):
        self.assertEqual(project_to_lane([10,5], [[0,0],[10,0],[10,10]]), (15,0))


if __name__=='__main__': unittest.main()
