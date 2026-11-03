"""Individual-vehicle descriptive percentile; synthetic ledger/tripinfo only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from sim.accounting import Accounting
from sim.audit import audit_lifecycle


def ledger(delays):
    scheduled={'ambulance':{'type':'ambulance','depart_s':0,'reference_s':1}}
    for index,delay in enumerate(delays):scheduled[f'c{index}']={'type':'car','depart_s':2,'reference_s':10}
    value=Accounting(scheduled)
    value.inserted={key:5 for key in scheduled};value.completed={'ambulance':999}
    value.completed.update({f'c{index}':12+delay for index,delay in enumerate(delays)})
    return value


class IndividualTailTests(unittest.TestCase):
    def test_nearest_rank_not_interpolation_and_ambulance_excluded(self):
        result=ledger(list(range(1,21))).civilian_excess_tail('completed')
        self.assertEqual(result['civilian_excess_p95_s'],19)
        population=result['civilian_excess_p95_population']
        self.assertEqual(population['scheduled_count'],20);self.assertEqual(population['included_count'],20)
        self.assertTrue(population['ambulance_excluded'])

    def test_single_vehicle_includes_insertion_wait_and_clamps_negative_excess(self):
        value=ledger([8]);value.inserted['c0']=7
        self.assertEqual(value.civilian_excess_tail('completed')['civilian_excess_p95_s'],8)
        value.completed['c0']=11
        self.assertEqual(value.civilian_excess_tail('completed')['civilian_excess_p95_s'],0)

    def test_invalid_censored_and_incomplete_never_use_completed_subset(self):
        for status in ('invalid','censored','infrastructure_error'):
            result=ledger([5,10]).civilian_excess_tail(status)
            self.assertIsNone(result['civilian_excess_p95_s']);self.assertEqual(result['civilian_excess_p95_population']['included_count'],0)
        value=ledger([5,10]);del value.completed['c1']
        self.assertIsNone(value.civilian_excess_tail('completed')['civilian_excess_p95_s'])

    def test_empty_civilian_population_null_without_changing_mean(self):
        value=ledger([])
        self.assertIsNone(value.civilian_excess_tail('completed')['civilian_excess_p95_s'])
        self.assertEqual(value.completed_civilian_mean_excess(),0.0)

    def test_nonfinite_inputs_and_overflow_cannot_hide_behind_zero_clamp(self):
        for malformed in (float('nan'),float('inf'),10**1000):
            value=ledger([5]);value.completed['c0']=malformed
            with self.subTest(value=str(malformed)[:15]),self.assertRaises(ValueError):value.civilian_excess_tail('completed')
        value=ledger([5]);value.completed['c0']=1e308;value.scheduled['c0']['depart_s']=-1e308
        with self.assertRaises(ValueError):value.civilian_excess_tail('completed')

    def test_ties_and_exact_rank_boundary(self):
        self.assertEqual(ledger([4]*100).civilian_excess_tail('completed')['civilian_excess_p95_s'],4)
        self.assertEqual(ledger(list(range(100))).civilian_excess_tail('completed')['civilian_excess_p95_s'],94)


class TailRawAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'tripinfo.xml';self.value=ledger([5,10])
        self.path.write_text('<tripinfos><tripinfo id="ambulance" depart="5" arrival="999"/>'
            '<tripinfo id="c0" depart="5" arrival="17"/><tripinfo id="c1" depart="5" arrival="22"/></tripinfos>')
        self.demand={'dispatch_s':0,'vehicles':[dict(value,id=key) for key,value in self.value.scheduled.items()]}
        self.metrics={'status':'completed','validity_reasons':[],'accounting':self.value.counts(),
            'ambulance_journey_s':999,'civilian_mean_excess_s':7.5,**self.value.civilian_excess_tail('completed')}

    def audit(self):audit_lifecycle(self.demand,self.value.rows(),self.path,self.metrics)

    def test_exact_tripinfo_tail_and_legacy_absence_supported(self):
        self.audit()
        del self.metrics['civilian_excess_p95_s'];del self.metrics['civilian_excess_p95_population'];self.audit()

    def test_changed_value_population_or_partial_fields_rejected(self):
        original=deepcopy(self.metrics)
        for mutation in ('value','population','missing','bool-count'):
            self.metrics=deepcopy(original)
            if mutation=='value':self.metrics['civilian_excess_p95_s']=9
            elif mutation=='population':self.metrics['civilian_excess_p95_population']['included_count']=1
            elif mutation=='missing':del self.metrics['civilian_excess_p95_population']
            else:self.metrics['civilian_excess_p95_population']['included_count']=True
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'tail/population'):self.audit()

    def test_invalid_fully_drained_tail_remains_null(self):
        self.metrics.update(status='invalid',validity_reasons=['collision'],civilian_mean_excess_s=None,
            **self.value.civilian_excess_tail('invalid'))
        self.audit();self.metrics['civilian_excess_p95_s']=10
        with self.assertRaisesRegex(ValueError,'tail/population'):self.audit()


if __name__=='__main__':unittest.main()
