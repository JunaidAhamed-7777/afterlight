"""Synthetic retained files: full drain never excuses a collision-invalid status."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from sim.audit import audit


def hash_file(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class AuditedWorldStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'network').mkdir();(self.root/'demand').mkdir()
        net=self.root/'network/network.net.xml';net.write_text('<net/>')
        demand={'dispatch_s':5,'vehicles':[
            {'id':'ambulance','type':'ambulance','depart_s':5,'reference_s':10},
            {'id':'civilian','type':'car','depart_s':0,'reference_s':10}]}
        self.write('demand/demand.json',demand);(self.root/'demand/demand.rou.xml').write_text('<routes/>')
        provenance={'source_commit':'a'*40,'network_sha256':hashlib.sha256(ET.canonicalize(from_file=net,strip_text=True,with_comments=False).encode()).hexdigest(),
            'network_file_sha256':hash_file(net),'demand_sha256':hash_file(self.root/'demand/demand.rou.xml'),
            'demand_manifest_sha256':hash_file(self.root/'demand/demand.json'),'demand_group_id':'b'*64,'sumo_version':'SUMO-synthetic-unit'}
        observation={'dispatch_s':5,'sensor_lag_s':1,'observed_at_s':4,'values':{
            'queue_sum_veh':0,'queue_max_veh':0,'downstream_occupancy':0,'route_distance_m':100,
            'route_junction_count':0,'eta_remaining_s':15,'phase_elapsed_s':4}}
        self.replay={'schema':'afterlight.replay.v1','mode':'recorded','duration_s':20,'step_s':10,
            'scenario':{'id':'unit-status','episode_id':'unit-episode','network_kind':'fixture','seed':7,'dispatch_s':5,
                        'pickup_id':'UNIT_PICKUP','hospital_id':'UNIT_HOSPITAL'},
            'coordinates':{'source':'canonical XY meters','position_reference':'front_bumper','render':'[x,z,-y]'},
            'provenance':provenance,'worlds':{}}
        for name,policy in [('baseline','ordinary'),('afterlight','fixed')]:
            invalid=name=='baseline';status='invalid' if invalid else 'completed';lead=None if policy=='ordinary' else 10
            decision={'t':5,'kind':'dispatch','policy':policy,'selected_lead_s':lead,'observation':deepcopy(observation),'absolute_etas':{},'request_plan':{}}
            metrics={'status':status,'validity_reasons':['collision'] if invalid else [],
                'accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0},
                'ambulance_journey_s':15,'civilian_mean_excess_s':None if invalid else 8,'runtime_s':1,'simulation_step_s':.5}
            events=[decision]+([{'t':12,'kind':'collision','vehicles':['ambulance','civilian']}] if invalid else [])
            world={'world_id':name,'policy':policy,'lead_s':lead,'status':status,'decision':decision,'metrics':metrics,'events':events,
                'frames':[{'t':t,'vehicles':[],'signals':[],'queue_count':0} for t in (0,10,20)]}
            self.replay['worlds'][name]=world
            self.write(name+'/lifecycle.json',[
                {'id':'ambulance','type':'ambulance','scheduled_depart_s':5,'reference_s':10,'actual_depart_s':5,'arrival_s':20},
                {'id':'civilian','type':'car','scheduled_depart_s':0,'reference_s':10,'actual_depart_s':2,'arrival_s':18}])
            (self.root/name/'tripinfo.xml').write_text('<tripinfos><tripinfo id="ambulance" depart="5" arrival="20"/><tripinfo id="civilian" depart="2" arrival="18"/></tripinfos>')
        self.write('outcomes.json',[{'world_id':name,'episode_id':'unit-episode',**provenance,'policy':w['policy'],'lead_s':w['lead_s'],
            'observation':w['decision']['observation'],'request_plan':{},**w['metrics']} for name,w in self.replay['worlds'].items()])
        self.save()

    def write(self,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

    def save(self):self.write('replay.json',self.replay)

    def audit(self):
        # Parsing generated SUMO lane geometry is outside this status regression;
        # actual replay validation/lifecycle/dispatch/scalar audits remain active.
        with patch('sim.audit.read_network',return_value={'signals':{}}):
            return audit(self.root,write_result=False)

    def test_consistent_fully_drained_collision_invalid_world_stays_invalid(self):
        result=self.audit()
        self.assertEqual(result['checks'][0]['status'],'invalid')
        self.assertFalse((self.root/'audit.json').exists())

    def test_outer_only_promotion_cannot_hide_invalid_raw_metrics(self):
        self.replay['worlds']['baseline']['status']='completed';self.save()
        with self.assertRaisesRegex(ValueError,'outer world status'):self.audit()
        self.assertEqual(self.replay['worlds']['baseline']['metrics']['validity_reasons'],['collision'])

    def test_outer_only_demotion_of_completed_fixed_candidate_rejected(self):
        self.replay['worlds']['afterlight']['status']='invalid';self.save()
        with self.assertRaisesRegex(ValueError,'outer world status'):self.audit()

    def test_matching_noninvalid_status_cannot_hide_validity_reasons(self):
        for status in ('completed','censored'):
            world=self.replay['worlds']['baseline'];world['status']=status;world['metrics']['status']=status
            self.save()
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'validity reasons'):self.audit()

    def test_completed_collision_or_teleport_event_cannot_be_cleared_from_reasons(self):
        for kind in ('collision','teleport'):
            world=self.replay['worlds']['baseline'];world['status']='completed';world['metrics']['status']='completed'
            world['metrics']['validity_reasons']=[];world['events'][-1]['kind']=kind;self.save()
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'collision or teleport'):self.audit()

    def test_legacy_structural_metrics_without_status_remain_accepted(self):
        from export.validation_base import validate_base_replay
        for world in self.replay['worlds'].values():del world['metrics']['status']
        validate_base_replay(self.replay)
        # Full real-evidence audit still requires a metric status.
        self.save()
        with self.assertRaisesRegex(ValueError,'outer world status'):self.audit()

    def test_ordinary_completed_outer_mismatch_rejected(self):
        world=self.replay['worlds']['baseline'];world['status']='invalid';world['metrics']['status']='completed'
        self.save()
        with self.assertRaisesRegex(ValueError,'outer world status'):self.audit()


if __name__=='__main__':unittest.main()
