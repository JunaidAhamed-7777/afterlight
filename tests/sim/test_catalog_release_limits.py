"""Synthetic publication-contract fixtures, never traffic evidence.

Run only on Omen after the isolated patch is authorized/integrated. Auditor mocks
exercise size/transaction boundaries, not SUMO correctness. Temporary fixtures
are not copied into the project's public recording library.
"""
from __future__ import annotations
import hashlib
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from export.catalog import MAX_PUBLIC_FILE_BYTES, MAX_DECODED_REPLAY_BYTES, _public_json_bytes, register
from sim.network import ROOT, sha256


class ReleaseBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.run=self.root/'run';self.run.mkdir()
        self.destination=self.root/'public'

    def fixture(self):
        replay={'schema':'afterlight.replay.v1','mode':'recorded','duration_s':1,'step_s':1,
                'coordinates':{'position_reference':'front_bumper','source':'canonical XY meters','render':'[x,z,-y]'},
                'scenario':{'id':'synthetic-budget-fixture','network_kind':'city','seed':7,'dispatch_s':0,
                            'pickup_id':'P001','hospital_id':'HOSP_EAST'},
                'provenance':{'source_commit':'1'*40,'source_dirty':False,'network_sha256':'2'*64,
                              'demand_sha256':'3'*64,'sumo_version':'synthetic unit fixture, never measured',
                              'canonical_map_sha256':sha256(ROOT/'assets/map/city_manifest.json')},
                'worlds':{name:{'world_id':name,'policy':'ordinary' if name=='baseline' else 'fixed',
                               'lead_s':None if name=='baseline' else 10,'status':'completed',
                               'metrics':{},'events':[],
                               'frames':[{'t':0,'vehicles':[],'signals':[],'queue_count':0},
                                         {'t':1,'vehicles':[],'signals':[],'queue_count':0}]}
                          for name in ('baseline','afterlight')}}
        payload=json.dumps(replay).encode()
        (self.run/'replay.json').write_bytes(payload)
        (self.run/'outcomes.json').write_text('[]')
        for name in ('baseline','afterlight'):
            (self.run/name).mkdir()
            (self.run/name/'tripinfo.xml').write_text('unit test placeholder; auditor is mocked')
            (self.run/name/'lifecycle.json').write_text('[]')
        return payload,{'replay_sha256':hashlib.sha256(payload).hexdigest()}

    def test_documented_ceiling_is_twenty_mebibytes(self):
        self.assertEqual(MAX_PUBLIC_FILE_BYTES,20*1024*1024)
        self.assertEqual(MAX_DECODED_REPLAY_BYTES,128*1024*1024)

    def test_gzip_registration_preserves_exact_raw_digest_and_values(self):
        payload,audit_result=self.fixture()
        replay=json.loads(payload);replay['synthetic_padding']='x'*100000
        payload=json.dumps(replay).encode();(self.run/'replay.json').write_bytes(payload)
        audit_result['replay_sha256']=hashlib.sha256(payload).hexdigest()
        with patch('export.catalog.MAX_PUBLIC_FILE_BYTES',16384), \
             patch('export.catalog.audit',return_value=audit_result),patch('export.catalog.audit_outcomes'):
            result=register(self.run,self.destination,compress=True,title='Test-only gzip fixture')
        entry=result['entry'];encoded=(self.destination/entry['url']).read_bytes()
        self.assertTrue(entry['url'].endswith('.json.gz'))
        self.assertLess(len(encoded),16384)
        self.assertGreater(len(payload),16384)
        self.assertEqual(gzip.decompress(encoded),payload)
        self.assertEqual(entry['sha256'],hashlib.sha256(payload).hexdigest())
        self.assertEqual(entry['transfer_sha256'],hashlib.sha256(encoded).hexdigest())
        self.assertEqual((entry['bytes'],entry['transfer_bytes']),(len(payload),len(encoded)))
        self.assertEqual((self.run/'replay.json').read_bytes(),payload)

    def test_gzip_decoded_boundary_is_checked_before_audit_or_output(self):
        payload,_=self.fixture()
        with patch('export.catalog.MAX_DECODED_REPLAY_BYTES',len(payload)),patch('export.catalog.audit') as auditor:
            with self.assertRaises(ValueError):register(self.run,self.destination,compress=True)
            auditor.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_coarse_physics_capture_is_refused_for_public_city_presentation(self):
        payload,_=self.fixture();replay=json.loads(payload)
        for world in replay['worlds'].values():world['metrics']['simulation_step_s']=.5
        (self.run/'replay.json').write_text(json.dumps(replay))
        with patch('export.catalog.audit') as auditor:
            with self.assertRaisesRegex(ValueError,'every integration boundary'):
                register(self.run,self.destination,compress=True)
            auditor.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_repacking_keeps_identity_evidence_and_human_title(self):
        payload,audit_result=self.fixture()
        with patch('export.catalog.audit',return_value=audit_result),patch('export.catalog.audit_outcomes'):
            original=register(self.run,self.destination,title='Cross-city response')
            evidence=(self.destination/original['entry']['evidence_url']).read_bytes()
            packed=register(self.run,self.destination,compress=True)
            again=register(self.run,self.destination,compress=True)
        self.assertEqual(packed['entry']['id'],original['entry']['id'])
        self.assertEqual(packed['entry']['title'],'Cross-city response')
        self.assertEqual((self.destination/packed['entry']['evidence_url']).read_bytes(),evidence)
        self.assertEqual((self.destination/original['entry']['url']).read_bytes(),payload)
        self.assertEqual(len(json.loads((self.destination/'catalog.json').read_text())['runs']),1)
        self.assertFalse(again['changed'])

    def test_exact_file_limit_is_rejected_before_mutation(self):
        payload=b'x'*64
        (self.run/'replay.json').write_bytes(payload)
        self.destination.mkdir()
        prior=b'{"schema":"afterlight.catalog.v1","runs":[]}'
        (self.destination/'catalog.json').write_bytes(prior)
        with patch('export.catalog.MAX_PUBLIC_FILE_BYTES',64), patch('export.catalog.audit') as auditor:
            with self.assertRaisesRegex(ValueError,'compact JSON|indexed chunks'):
                register(self.run,self.destination)
            auditor.assert_not_called()
        self.assertEqual((self.run/'replay.json').read_bytes(),payload)
        self.assertEqual((self.destination/'catalog.json').read_bytes(),prior)
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()),['catalog.json'])

    def test_evidence_limit_is_checked_before_destination_creation(self):
        payload,audit_result=self.fixture()
        budget=len(payload)+1000
        (self.run/'outcomes.json').write_text(json.dumps({'synthetic_padding':'x'*(budget*2)}))
        before={str(p.relative_to(self.run)):p.read_bytes() for p in self.run.rglob('*') if p.is_file()}
        with patch('export.catalog.MAX_PUBLIC_FILE_BYTES',budget), \
             patch('export.catalog.audit',return_value=audit_result) as auditor, \
             patch('export.catalog.audit_outcomes'):
            with self.assertRaisesRegex(ValueError,'compact JSON|indexed chunks'):
                register(self.run,self.destination)
            auditor.assert_called_once_with(self.run,write_result=False)
        self.assertFalse(self.destination.exists())
        after={str(p.relative_to(self.run)):p.read_bytes() for p in self.run.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_serialized_json_boundary_is_strict_and_lossless(self):
        value={'message':'original scientific values','numbers':[1,2,3]}
        payload=_public_json_bytes(value)
        with patch('export.catalog.MAX_PUBLIC_FILE_BYTES',len(payload)):
            with self.assertRaises(ValueError):_public_json_bytes(value)
        with patch('export.catalog.MAX_PUBLIC_FILE_BYTES',len(payload)+1):
            self.assertEqual(_public_json_bytes(value),payload)
        self.assertEqual(json.loads(payload),value)

    def test_catalog_policy_is_canonical_not_display_label(self):
        _,audit_result=self.fixture()
        with patch('export.catalog.audit',return_value=audit_result),patch('export.catalog.audit_outcomes'):
            result=register(self.run,self.destination)
        self.assertEqual(result['entry']['policy'],'fixed')
        self.assertEqual(result['entry']['lead_s'],10)
        self.assertEqual(result['entry']['policy_label'],'fixed · 10 s lead')


if __name__=='__main__':unittest.main()
