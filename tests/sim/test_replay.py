"""Synthetic validation fixtures only; never exported as traffic evidence."""
import copy
import unittest
from export.replay import validate_replay


def specimen():
    return {'schema':'afterlight.replay.v1','mode':'recorded','duration_s':1,'step_s':1,
            'coordinates':{'position_reference':'front_bumper'},'scenario':{'network_kind':'fixture'},
            'provenance':dict(source_commit='fixture',network_sha256='fixture',demand_sha256='fixture',sumo_version='fixture'),
            'worlds':{w:{'world_id':w,'status':'completed','policy':'ordinary' if w=='baseline' else 'fixed',
                        'frames':[{'t':0,'vehicles':[]},{'t':1,'vehicles':[]}]} for w in ('baseline','afterlight')}}


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


if __name__=='__main__': unittest.main()
