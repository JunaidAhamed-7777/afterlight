"""Synthetic pre-test analysis regression. No collection, fitting or simulation."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib.util
from pathlib import Path
import py_compile
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import afterlight_analysis_binding_v1 as binding
import afterlight_analysis_amendment_v1 as analysis
import run_analysis_amendment as entry
from evaluation.study_manifest import validate_pilot_world_binding
from models.analytical import AnalyticalConfig, ESTIMATOR_VERSION, estimate_candidates
from policies.scheduler import timing_for_network


class ExactFrozenEstimatorTests(unittest.TestCase):
    def setUp(self):
        observation = {'dispatch_s':20,'sensor_lag_s':1,'observed_at_s':19,'values':{
            'queue_sum_veh':10,'queue_max_veh':10,'downstream_occupancy':0,'route_distance_m':500,
            'route_junction_count':3,'eta_remaining_s':40,'phase_elapsed_s':2}}
        self.estimator = {'version':ESTIMATOR_VERSION,'config':asdict(AnalyticalConfig())}
        self.plan = {'civilian_weight':1,'network':'city','analytical_estimator':self.estimator}
        self.raw = {'policy':'fixed','lead_s':10,'status':'completed','sumo_version':'synthetic fixture',
            'metrics':{'runtime_s':1.0,'controller_timing':asdict(timing_for_network('city'))},
            'decision':{'observation':observation,'request_plan':{'fixture':True}}}
        cost = next(row['analytical_cost_s'] for row in estimate_candidates(observation)['scores'] if row['lead_s']==10)
        self.row = {key:self.raw[key] for key in ('policy','lead_s','status','sumo_version')}
        self.row.update(self.raw['decision'],simulator_runtime_s=1.0,
            controller_timing=self.raw['metrics']['controller_timing'],
            analytical_config_sha256=entry.digest(self.estimator),analytical_cost_s=cost)

    def test_integer_objective_float_frozen_config_reproduces_old_failure_and_passes_exact_binding(self):
        with self.assertRaisesRegex(ValueError,'prediction/config'):
            validate_pilot_world_binding(self.row,self.raw,self.plan)
        binding.validate_frozen_estimator_world_binding(self.row,self.raw,self.plan)
        self.assertIs(type(self.plan['civilian_weight']),int)
        self.assertIs(type(self.estimator['config']['civilian_weight']),float)

    def test_full_explicit_nondefault_config_is_used(self):
        self.estimator['config']['queue_headway_s']=3.5
        scores=estimate_candidates(self.raw['decision']['observation'],AnalyticalConfig(**self.estimator['config']))
        self.row['analytical_config_sha256']=entry.digest(self.estimator)
        self.row['analytical_cost_s']=next(r['analytical_cost_s'] for r in scores['scores'] if r['lead_s']==10)
        binding.validate_frozen_estimator_world_binding(self.row,self.raw,self.plan)

    def test_original_metric_decision_config_and_timing_guards_remain(self):
        for key,value in [('analytical_config_sha256','0'*64),('analytical_cost_s',-100),
                          ('simulator_runtime_s',2),('request_plan',{}),('status','invalid')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                binding.validate_frozen_estimator_world_binding({**self.row,key:value},self.raw,self.plan)
        for change in ('version','missing','timing'):
            raw,plan=deepcopy(self.raw),deepcopy(self.plan)
            if change=='version':plan['analytical_estimator']['version']='wrong'
            elif change=='missing':del plan['analytical_estimator']['config']['queue_headway_s']
            else:raw['metrics']['controller_timing']['all_red_s']=99
            with self.subTest(change=change),self.assertRaises(ValueError):
                binding.validate_frozen_estimator_world_binding(self.row,raw,plan)

    def test_descriptor_numeric_identity_is_canonical_not_python_equality(self):
        study={'sha256':'study','study':{'source':{},'protocol':{'analytical_estimator':self.estimator}}}
        amended=deepcopy(self.estimator);amended['config']['civilian_weight']=1
        self.assertEqual(amended,self.estimator)
        self.assertNotEqual(entry.digest(amended),entry.digest(self.estimator))
        descriptor={'schema':'afterlight.analysis-amendment.v1','id':'frozen-estimator-config-v1',
            'original_study_sha256':'study','original_protocol_sha256':entry.digest(study['study']['protocol']),
            'original_source':{},'frozen_analytical_estimator':amended,
            'frozen_analytical_estimator_sha256':entry.digest(self.estimator)}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'analysis-amendment.json'
            entry.write_new(path,{'sha256':entry.digest(descriptor),'amendment':descriptor})
            with patch.object(entry,'original_context',return_value=study),self.assertRaisesRegex(ValueError,'exact original'):
                entry.load_amended_analysis(Path(temp),Path(temp),path)

    def test_verified_raw_source_ignores_timestamp_valid_poisoned_bytecode(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'fixture.py'
            path.write_bytes(b'value="poison"\n')
            stamp=path.stat().st_mtime_ns
            py_compile.compile(str(path),doraise=True)
            source=b'value="source"\n'
            self.assertEqual(len(source),path.stat().st_size)
            path.write_bytes(source)
            import os
            os.utime(path,ns=(stamp,stamp))
            name='afterlight_amendment_synthetic_source_test'
            self.addCleanup(sys.modules.pop,name,None)
            module=entry._load_verified_source(name,path,hashlib.sha256(source).hexdigest())
            self.assertEqual(module.value,'source')
            self.assertEqual(module.__file__,str(path))
            with self.assertRaisesRegex(ValueError,'changed before compilation'):
                entry._load_verified_source(name,path,'0'*64)

    def test_wrong_selection_amendment_rejects_before_released_test_evidence(self):
        study={'sha256':'study','study':{}}
        for function,args in [(analysis.report_study,(ROOT/'study',ROOT/'collection',ROOT/'output')),
                              (analysis.verify_report_artifacts,(ROOT/'study',ROOT/'collection',ROOT/'report'))]:
            with self.subTest(function=function.__name__),patch.object(analysis,'load_study',return_value=study),\
                 patch.object(analysis,'assert_study_runtime'),\
                 patch.object(analysis,'_released_test_context',return_value={'selection_directory':ROOT}),\
                 patch.object(analysis,'_require_selection_amendment',side_effect=ValueError('wrong amendment')),\
                 patch.object(analysis,'verify_released_test_collection') as evidence:
                with self.assertRaisesRegex(ValueError,'wrong amendment'):
                    function(*args,analysis_amendment={})
                evidence.assert_not_called()

    def test_freeze_protects_study_before_writes_without_blocking_top_level_failure_files(self):
        with tempfile.TemporaryDirectory() as temp:
            checkout=Path(temp);runtime=checkout/'local-runtime';runtime.mkdir()
            study=runtime/'study';study.mkdir()
            journal=runtime/'failed.json';log=runtime/'failed.log'
            entry.write_new(journal,{'state':'watcher_stopped_no_test_release','return_code':1,
                'command':['select','--output','local-runtime/missing-original-selection']})
            log.write_bytes(b'validate_pilot_world_binding')
            with patch.object(entry,'original_context',return_value={}),\
                 patch.object(Path,'mkdir',side_effect=RuntimeError('reached fresh mkdir')) as mkdir:
                with self.assertRaises(ValueError):
                    entry.freeze_amendment(checkout,study,journal,log,study/'inputs'/'bundle')
                mkdir.assert_not_called()
                with self.assertRaisesRegex(RuntimeError,'reached fresh mkdir'):
                    entry.freeze_amendment(checkout,study,journal,log,runtime/'fresh-bundle')

    def test_command_rejects_internally_resealed_amendment_at_final_check(self):
        with tempfile.TemporaryDirectory() as temp:
            checkout=Path(temp)
            argv=['run_analysis_amendment.py','select','--checkout',str(checkout),
                  '--study','local-runtime/study','--amendment','local-runtime/bundle/analysis-amendment.json',
                  '--train','local-runtime/train','--validation','local-runtime/validation',
                  '--output','local-runtime/fresh-selection']
            module=SimpleNamespace(select_study=Mock(return_value={'sha256':'synthetic'}))
            with patch.object(sys,'argv',argv),patch.object(entry,'load_amended_analysis',side_effect=[
                    (module,{'sha256':'initial'},{'sha256':'initial'}),
                    (module,{'sha256':'resealed'},{'sha256':'resealed'})]):
                with self.assertRaisesRegex(ValueError,'identity changed during'):
                    entry.main()
                module.select_study.assert_called_once()


if __name__=='__main__':unittest.main()
