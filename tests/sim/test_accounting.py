import unittest
from sim.accounting import Accounting


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Accounting({'ambulance': {'type':'ambulance','depart_s':5,'reference_s':10},
            'c1': {'type':'car','depart_s':0,'reference_s':10},
            'c2': {'type':'car','depart_s':1,'reference_s':10}})

    def test_uninserted_and_running_are_not_hidden(self):
        self.ledger.depart(['c1'], 3)
        self.assertEqual(self.ledger.counts(), {'scheduled':2,'inserted':1,'completed':0,'running':1,'not_inserted':1})
        self.assertIsNone(self.ledger.completed_civilian_mean_excess())

    def test_delay_includes_insertion_wait(self):
        self.ledger.depart(['c1','c2'], 5)
        self.ledger.arrive(['c1','c2'], 20)
        self.assertEqual(self.ledger.completed_civilian_mean_excess(), 9.5)

    def test_rejects_ghost_physical_vehicle(self):
        with self.assertRaises(ValueError): self.ledger.depart(['ghost'], 1)

    def test_duplicate_arrival_rejected(self):
        self.ledger.depart(['c1'], 1)
        self.ledger.arrive(['c1'], 12)
        with self.assertRaises(ValueError): self.ledger.arrive(['c1'], 13)


if __name__ == '__main__': unittest.main()
