"""Synthetic raw-evidence consistency tests, not traffic performance examples."""
import copy
from pathlib import Path
import tempfile
import unittest
from sim.audit import audit_lifecycle


class AuditLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.tripinfo=Path(self.temp.name)/'tripinfo.xml'
        self.tripinfo.write_text('<tripinfos><tripinfo id="ambulance" depart="5" arrival="20"/>'
                                '<tripinfo id="c1" depart="2" arrival="18"/></tripinfos>')
        self.demand={'dispatch_s':5,'vehicles':[
            {'id':'ambulance','type':'ambulance','depart_s':5,'reference_s':10},
            {'id':'c1','type':'car','depart_s':0,'reference_s':10}]}
        self.rows=[{'id':'ambulance','type':'ambulance','scheduled_depart_s':5,'reference_s':10,'actual_depart_s':5,'arrival_s':20},
                   {'id':'c1','type':'car','scheduled_depart_s':0,'reference_s':10,'actual_depart_s':2,'arrival_s':18}]
        self.metrics={'status':'completed','accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0},
                      'ambulance_journey_s':15,'civilian_mean_excess_s':8}

    def test_exact_raw_agreement(self):
        audit_lifecycle(self.demand,self.rows,self.tripinfo,self.metrics)

    def test_rejects_improved_but_fabricated_journey(self):
        self.metrics['ambulance_journey_s']=10
        with self.assertRaises(ValueError): audit_lifecycle(self.demand,self.rows,self.tripinfo,self.metrics)

    def test_rejects_changed_lifecycle_time(self):
        self.rows[0]['arrival_s']=19
        with self.assertRaises(ValueError): audit_lifecycle(self.demand,self.rows,self.tripinfo,self.metrics)

    def test_rejects_completed_only_population(self):
        self.demand['vehicles'].append({'id':'uninserted','type':'car','depart_s':1,'reference_s':10})
        with self.assertRaises(ValueError): audit_lifecycle(self.demand,self.rows,self.tripinfo,self.metrics)


if __name__=='__main__': unittest.main()
