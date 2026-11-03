"""Bounded optional artifact capture tests, no traffic/model execution."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evaluation.collector import IllustrativeCapture
from evaluation.protocol import digest
from evaluation.study_manifest import validate_illustrative_capture, POLICIES


class CaptureContractTests(unittest.TestCase):
    def test_empty_and_bounded_test_only_contract(self):
        cases=[{'case_id':'a','split':'test'},{'case_id':'b','split':'train'}]
        validate_illustrative_capture({'case_ids':[],'max_world_bytes':0,'max_total_bytes':0},cases)
        validate_illustrative_capture({'case_ids':['a'],'max_world_bytes':100,'max_total_bytes':600},cases)
        for contract in ({'case_ids':['b'],'max_world_bytes':100,'max_total_bytes':600},
                         {'case_ids':['a'],'max_world_bytes':8388609,'max_total_bytes':10000000},
                         {'case_ids':['a'],'max_world_bytes':100,'max_total_bytes':99},
                         {'case_ids':[],'max_world_bytes':1,'max_total_bytes':1},
                         {'case_ids':['a'],'max_world_bytes':100}):
            with self.subTest(contract=contract),self.assertRaises(ValueError):validate_illustrative_capture(contract,cases)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.contract={'case_ids':['case'],'max_world_bytes':10000,'max_total_bytes':60000}
        self.study={'sha256':'study','study':{'spec':{'illustrative_capture':self.contract},'protocol':{},'source':{'source_commit':'unit'}}}
        self.episodes=[{'episode_id':'episode','case_id':'case','demand_sha256':'demand','network_sha256':'network'}]
        self.planned=[{'episode_id':'episode','case_id':'case','policy':policy,'lead_s':lead,
            'directory':f'worlds/case/{policy}'+(f'-{lead}' if lead is not None else '')} for policy,lead in POLICIES]
        for item in self.planned:(self.root/item['directory']).mkdir(parents=True)
        self.capture=IllustrativeCapture(self.root,self.study,'test',self.episodes,self.planned)
        self.world={'world_id':'ordinary','policy':'ordinary','lead_s':None,'decision':{'policy':'ordinary'},
                    'frames':[{'t':0,'vehicles':[{'id':'ambulance','x':3}],'signals':[]}]}

    def test_full_world_bytes_preserve_original_policy_decision_and_poses(self):
        original=deepcopy(self.world)
        entry=self.capture.capture(self.planned[0],self.world,audited=True)
        self.assertEqual(entry['state'],'retained')
        self.assertEqual(json.loads((self.root/entry['file']).read_text()),original)
        self.assertEqual(self.world,original)
        self.assertEqual(self.capture.traces['charged_bytes'],entry['bytes'])
        self.assertEqual(self.capture.traces['retained_bytes'],entry['bytes'])
        self.assertEqual(len(self.capture.traces['entries']),6)
        self.assertEqual(self.capture.capture(self.planned[1],self.world,audited=True),{'state':'not_requested'})

    def test_world_budget_failure_writes_nothing_and_does_not_raise(self):
        self.contract['max_world_bytes']=1
        entry=self.capture.capture(self.planned[0],self.world,audited=True)
        self.assertEqual(entry['state'],'budget_exceeded');self.assertIsNone(entry['file'])
        self.assertEqual(self.capture.traces['charged_bytes'],0)
        self.assertFalse((self.root/self.planned[0]['directory']/'rich-world.json').exists())

    def test_total_budget_failure_retains_prior_trace_without_rerun(self):
        first=self.capture.capture(self.planned[0],self.world,audited=True)
        self.contract['max_total_bytes']=first['bytes']
        world={**self.world,'world_id':'fixed-0','policy':'fixed','lead_s':0}
        second=self.capture.capture(self.planned[2],world,audited=True)
        self.assertEqual(second['state'],'budget_exceeded')
        self.assertTrue((self.root/first['file']).is_file())
        self.assertEqual(self.capture.traces['retained_bytes'],first['bytes'])

    def test_write_failure_isolated_and_charged_conservatively(self):
        with patch.object(Path,'open',side_effect=OSError('synthetic write failure')):
            entry=self.capture.capture(self.planned[0],self.world,audited=True)
        self.assertEqual(entry['state'],'capture_failed')
        self.assertEqual(self.capture.traces['charged_bytes'],entry['bytes'])
        self.assertEqual(self.capture.traces['retained_bytes'],0)
        self.assertIsNone(entry['sha256'])

    def test_serialization_failure_is_not_a_scientific_failure(self):
        self.world['bad']=float('nan')
        entry=self.capture.capture(self.planned[0],self.world,audited=True)
        self.assertEqual(entry['state'],'capture_failed')
        self.assertEqual(self.capture.traces['charged_bytes'],0)

    def test_complete_manifest_binds_six_world_inventory(self):
        for item in self.planned:
            world={**self.world,'world_id':Path(item['directory']).name,'policy':item['policy'],'lead_s':item['lead_s']}
            self.capture.capture(item,world,audited=True)
        summary=self.capture.checkpoint()
        self.assertEqual(summary['status'],'complete')
        envelope=json.loads((self.root/'traces.json').read_text())
        self.assertEqual(envelope['sha256'],digest(envelope['traces']))
        self.assertEqual(len(envelope['traces']['entries']),6)
        self.assertTrue(all(entry['state']=='retained' for entry in envelope['traces']['entries']))

    def test_manifest_write_failure_is_explicit_and_isolated(self):
        with patch('evaluation.collector._checkpoint',side_effect=OSError('synthetic manifest failure')):
            summary=self.capture.checkpoint()
        self.assertEqual(summary['status'],'manifest_write_failed')
        self.assertIsNone(summary['manifest_sha256'])

    def test_wrong_underlying_policy_cannot_be_retained_as_selected_candidate(self):
        entry=self.capture.capture(self.planned[2],self.world,audited=True)
        self.assertEqual(entry['state'],'capture_failed')
        self.assertIn('identity/policy',entry['reason'])
        self.assertEqual(self.capture.traces['charged_bytes'],0)
