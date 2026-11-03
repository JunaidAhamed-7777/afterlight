"""Synthetic validation fixtures only; never exported as traffic evidence."""
import copy
import unittest
from export.replay import validate_replay


def specimen():
    return {'schema':'afterlight.replay.v1','mode':'recorded','duration_s':1,'step_s':1,
            'coordinates':{'position_reference':'front_bumper','source':'canonical XY meters','render':'[x,z,-y]'},
            'scenario':{'network_kind':'fixture','id':'unit-only','seed':7,'dispatch_s':0,'pickup_id':'FIXTURE_PICKUP','hospital_id':'FIXTURE_HOSPITAL'},
            'provenance':dict(source_commit='fixture',network_sha256='a'*64,demand_sha256='b'*64,sumo_version='fixture'),
            'worlds':{w:{'world_id':w,'status':'completed','policy':'ordinary' if w=='baseline' else 'fixed',
                        'metrics':{},'events':[],'frames':[{'t':0,'vehicles':[],'signals':[],'queue_count':0},{'t':1,'vehicles':[],'signals':[],'queue_count':0}]} for w in ('baseline','afterlight')}}


class ReplayTests(unittest.TestCase):
    def test_accepts_aligned_clock_fixture(self): validate_replay(specimen())
    def test_rejects_empty_trace(self):
        r=specimen()
        for w in r['worlds'].values(): w['frames']=[]
        with self.assertRaises(ValueError): validate_replay(r)
    def test_rejects_rescaled_baseline_clock(self):
        r=specimen(); r['worlds']['baseline']['frames'][1]['t']=.5
        with self.assertRaises(ValueError): validate_replay(r)
    def test_rejects_missing_provenance(self):
        r=specimen(); r['provenance'].pop('demand_sha256')
        with self.assertRaises(ValueError): validate_replay(r)
    def test_rejects_ghost_as_physical_vehicle(self):
        r=specimen(); r['worlds']['afterlight']['frames'][0]['vehicles']=[{'id':'ghost'}]
        with self.assertRaises(ValueError): validate_replay(r)
    def test_rejects_negative_time(self):
        r=specimen()
        for w in r['worlds'].values(): w['frames'][0]['t']=-.5
        with self.assertRaises(ValueError): validate_replay(r)

    def test_rejects_boolean_times_and_pose_numbers(self):
        for key in ('duration_s','step_s'):
            r=specimen();r[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):validate_replay(r)
        for key in ('x','y','z','angle_deg','speed_mps','length_m','width_m'):
            r=specimen();vehicle=dict(id='ambulance',type='ambulance',x=0,y=0,z=0,angle_deg=0,speed_mps=0,length_m=5,width_m=2)
            vehicle[key]=True;r['worlds']['afterlight']['frames'][0]['vehicles']=[vehicle]
            with self.subTest(key=key),self.assertRaises(ValueError):validate_replay(r)
        for key in ('t','queue_count'):
            r=specimen();r['worlds']['afterlight']['frames'][0][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):validate_replay(r)

    def test_rejects_missing_world_and_frame_contract_fields(self):
        for key in ('metrics','events','policy'):
            r=specimen();del r['worlds']['afterlight'][key]
            with self.subTest(key=key),self.assertRaises(ValueError):validate_replay(r)
        for key in ('signals','queue_count','vehicles'):
            r=specimen();del r['worlds']['afterlight']['frames'][0][key]
            with self.subTest(key=key),self.assertRaises(ValueError):validate_replay(r)
        for value in ([],True,'complete',None):
            r=specimen();r['worlds']['afterlight']['metrics']=value
            with self.subTest(metrics=value),self.assertRaises(ValueError):validate_replay(r)

    def test_rejects_noncanonical_physical_ambulances(self):
        for identifier,kind in (('other','ambulance'),('ambulance','car'),('civilian','unknown'),('civilian',None)):
            r=specimen();r['worlds']['afterlight']['frames'][0]['vehicles']=[dict(id=identifier,type=kind,x=0,y=0,z=0,angle_deg=0,speed_mps=0,length_m=5)]
            with self.subTest(identity=(identifier,kind)),self.assertRaises(ValueError):validate_replay(r)

    def test_rejects_invalid_events_hashes_and_coordinates(self):
        mutations=[lambda r:r['provenance'].update(network_sha256='fixture'),
                   lambda r:r['coordinates'].update(render='wrong'),
                   lambda r:r['scenario'].update(seed=True),
                   lambda r:r['worlds']['afterlight'].update(events=[{'kind':'dispatch','t':True}]),
                   lambda r:r['worlds']['afterlight'].update(events=[{'kind':'dispatch','t':2}]),
                   lambda r:r['worlds']['afterlight'].update(events=[{'kind':'request_planned','t':1,'request_at_s':0}])]
        for index,mutate in enumerate(mutations):
            r=specimen();mutate(r)
            with self.subTest(mutation=index),self.assertRaises(ValueError):validate_replay(r)

    def test_optional_geometry_and_decision_preserve_recorded_v1(self):
        r=specimen();r['worlds']['afterlight']['status']='censored'
        r['worlds']['afterlight']['metrics']={'ambulance_journey_s':None}
        r['worlds']['afterlight']['decision']={'t':0,'request_plan':{'J':100}}
        r['worlds']['afterlight']['events']=[{'kind':'request_planned','t':0,'request_at_s':100}]
        validate_replay(r)
        r['worlds']['afterlight']['decision']=[]
        with self.assertRaises(ValueError):validate_replay(r)

    def test_signal_geometry_binding_allows_shared_link_indices(self):
        r=specimen()
        link=dict(index=0,from_edge='a',to_edge='b',from_lane='a_0',to_lane='b_0',stop_line=[0,0],incoming_shape=[[-1,0],[0,0]],outgoing_shape=[[0,0],[1,0]])
        r['network_geometry']={'signals':[{'id':'J','position':[0,0],'links':[link,dict(link,to_lane='b_1')]}]}
        for world in r['worlds'].values():
            for frame in world['frames']:frame['signals']=[{'id':'J','state':'G'}]
        validate_replay(r)
        bad=copy.deepcopy(r);bad['network_geometry']['signals'][0]['links'][0]['index']=5
        with self.assertRaises(ValueError):validate_replay(bad)
        for signals in ([],[{'id':'other','state':'G'}],[{'id':'J','state':'GG'}],[{'id':'J','state':'?' }],[{'id':'J','state':'G'},{'id':'J','state':'G'}]):
            bad=copy.deepcopy(r);bad['worlds']['afterlight']['frames'][1]['signals']=signals
            with self.subTest(signals=signals),self.assertRaises(ValueError):validate_replay(bad)


if __name__=='__main__': unittest.main()
