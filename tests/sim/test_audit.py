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



class ScalarEvidenceTests(unittest.TestCase):
    def test_stale_companion_metrics_are_rejected(self):
        from sim.audit import audit_outcomes
        provenance={'demand_group_id':'g','demand_sha256':'d','network_sha256':'n','source_commit':'c'}
        worlds={name:{'policy':'ordinary' if name=='baseline' else 'fixed','lead_s':None if name=='baseline' else 10,
            'decision':{'observation':{},'request_plan':{}},'metrics':{'status':'completed','ambulance_journey_s':20}}
            for name in ('baseline','afterlight')}
        replay={'scenario':{'episode_id':'e'},'provenance':provenance,'worlds':worlds}
        rows=[{'episode_id':'e',**provenance,'policy':world['policy'],'lead_s':world['lead_s'],
               'observation':{},'request_plan':{},**world['metrics']} for world in worlds.values()]
        audit_outcomes(replay,rows)
        rows[1]['ambulance_journey_s']=10
        with self.assertRaises(ValueError): audit_outcomes(replay,rows)



class NegativeControlTests(unittest.TestCase):
    def test_runtime_can_differ_but_physics_cannot(self):
        from sim.audit import audit_ordinary_negative_control
        world={'policy':'ordinary','frames':[{'t':0}],'events':[], 'decision':{},'status':'completed',
               'metrics':{'runtime_s':1,'ambulance_journey_s':20}}
        replay={'worlds':{'baseline':copy.deepcopy(world),'afterlight':copy.deepcopy(world)}}
        replay['worlds']['afterlight']['metrics']['runtime_s']=2
        self.assertTrue(audit_ordinary_negative_control(replay))
        replay['worlds']['afterlight']['frames'][0]['t']=1
        with self.assertRaises(ValueError):audit_ordinary_negative_control(replay)


if __name__=='__main__': unittest.main()
