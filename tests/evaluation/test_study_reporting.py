"""Pure/mocked selection guards. These fixtures are not experimental evidence."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.protocol import digest
from evaluation.study_manifest import POLICIES, file_hash
from evaluation.study_reporting import RAW_FILES, verify_collection, select_study, ml_runtime
from models.analytical import AnalyticalConfig


class ReportingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.study_dir=self.root/'local-runtime/study';self.study_dir.mkdir(parents=True)
        self.collection=self.root/'local-runtime/train';self.collection.mkdir()
        self.source={'source_commit':'unit','source_code_sha256':'unit-code','source_dirty':False}
        self.estimator={'version':'unit','config':asdict(AnalyticalConfig())}
        episode={'episode_id':'episode','case_id':'case','demand_group_id':'group','split':'train','regime':'sparse','seed':1,
            'dispatch_s':2,'pickup_id':'pickup','hospital_id':'hospital','route_family':'route',
            'demand_sha256':'demand','network_sha256':'network','demand_directory':'inputs/demand/case'}
        self.study={'source':self.source,'dependencies':{},'pilot_evidence':{'sumo_version':'unit'},'episodes':[episode],
            'network':{'directory':'inputs/network'},'budget':{'split_start_budgets_s':{'train':100}},
            'spec':{'civilian_weight':1,'timing':{'step_s':.5},'model_specification':{'max_depth':3,'min_samples_leaf':5}},
            'protocol':{'schema':'afterlight.protocol.v1','group_assignments':{'group':'train'},'horizon_s':10,'drain_end_s':20,
                'recovery_window_s':[2,20],'queue_scope':'unit','feature_schema':[],
                'analytical_estimator':self.estimator}}
        self.envelope={'sha256':digest(self.study),'study':self.study}
        demand=self.study_dir/episode['demand_directory'];demand.mkdir(parents=True)
        (demand/'demand.json').write_text('{}')
        self.rows=[];planned=[]
        for policy,lead in POLICIES:
            relative=f'worlds/case/{policy}'+(f'-{lead}' if lead is not None else '')
            directory=self.collection/relative;directory.mkdir(parents=True)
            metrics={'status':'completed','validity_reasons':[],'runtime_s':.1,
                'ambulance_journey_s':3,'civilian_mean_excess_s':1,'horizon_s':10,'drain_end_s':20,
                'accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0},
                'queue_samples':[{'t':0,'queue_count':0},{'t':20,'queue_count':0}]}
            raw={'policy':policy,'lead_s':lead,'status':'completed','sumo_version':'unit','metrics':metrics,
                'decision':{'observation':{},'request_plan':[]},'events':[]}
            signal={k:raw[k] for k in ('policy','status','metrics','decision','events')};signal['frames']=[]
            for name,value in [('outcome.json',raw),('signal-audit-input.json',signal),('lifecycle.json',[]),('command.json',[])]:
                (directory/name).write_text(json.dumps(value))
            (directory/'tripinfo.xml').write_text('<tripinfos/>')
            hashes={name:file_hash(directory/name) for name in RAW_FILES}
            self.rows.append({**episode,**metrics,'policy':policy,'lead_s':lead,'source_commit':'unit','source_code_sha256':'unit-code',
                'study_sha256':self.envelope['sha256'],'protocol_sha256':digest(self.study['protocol']),'dependencies':{},
                'sumo_version':'unit','audit_status':'passed','priority_deadline_audit':'passed','raw_world_directory':relative,
                'raw_files_sha256':hashes,'signal_audit_input_sha256':hashes['signal-audit-input.json'],
                'runtime_s':.2,'simulator_runtime_s':.1,'observation':{},'request_plan':[],
                'analytical_config_sha256':digest(self.estimator),'analytical_cost_s':1 if lead is not None else None,
                'recovery_window_s':[2,20],'recovery_excess_queue_area_vehicle_s':0,'queue_scope':'unit'})
            planned.append({'episode_id':'episode','case_id':'case','policy':policy,'lead_s':lead,
                'state':'audited','runner_invoked':True,'directory':relative})
        self.manifest={'schema':'afterlight.collection.v1','status':'completed','split':'train',
            'study_sha256':self.envelope['sha256'],'protocol_sha256':digest(self.study['protocol']),
            'source':self.source,'dependencies':{},'sumo_version':'unit','world_inventory':planned,
            'recorded_worlds':7,'runner_invocations':7,'unattempted_worlds':0,'runtime_total_s':2,
            'split_start_budget_s':100,'wall_budget_overrun_s':0}
        self.save()
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('evaluation.study_reporting.load_study',return_value=self.envelope))
        stack.enter_context(patch('sim.network.read_network',return_value={}))
        stack.enter_context(patch('sim.audit.audit_lifecycle'))
        stack.enter_context(patch('sim.audit.audit_world_signals'))
        stack.enter_context(patch('evaluation.study_reporting.assert_episode_coverage'))
        stack.enter_context(patch('evaluation.study_reporting.validate_prediction_inputs'))
        stack.enter_context(patch('models.residual.validate_candidate_rows'))
        stack.enter_context(patch('evaluation.study_manifest.estimate_candidates',return_value={**self.estimator,
            'scores':[{'lead_s':lead,'analytical_cost_s':1} for lead in (0,5,10,20,30)]}))

    def save(self):
        for name,value in [('collection.json',self.manifest),('outcomes.json',self.rows),
                           ('candidate-outcomes.json',[r for r in self.rows if r['policy']=='fixed'])]:
            (self.collection/name).write_text(json.dumps(value))

    def test_complete_collection_preserves_all_worlds(self):
        result=verify_collection(self.study_dir,self.collection,'train')
        self.assertEqual(len(result['rows']),7);self.assertEqual(len(result['candidate_rows']),5)
        self.assertEqual(len(result['files_sha256']),38)

    def test_wrong_split_never_opens_outcomes(self):
        self.manifest['split']='test';self.save()
        (self.collection/'outcomes.json').unlink();(self.collection/'candidate-outcomes.json').unlink()
        with self.assertRaisesRegex(ValueError,'outcomes not opened'):verify_collection(self.study_dir,self.collection,'train')
        with self.assertRaisesRegex(ValueError,'test remains unreleased'):verify_collection(self.study_dir,self.collection,'test')

    def test_raw_byte_mutation_is_rejected(self):
        (self.collection/self.rows[0]['raw_world_directory']/'command.json').write_text('["changed"]')
        with self.assertRaisesRegex(ValueError,'evidence changed'):verify_collection(self.study_dir,self.collection,'train')

    def test_partial_or_duplicate_inventory_is_rejected(self):
        self.manifest['world_inventory'][0]['state']='unattempted';self.save()
        with self.assertRaisesRegex(ValueError,'unattempted'):verify_collection(self.study_dir,self.collection,'train')

    def test_stale_scalar_queue_or_recovery_is_rejected(self):
        self.rows[0]['queue_samples'][0]['queue_count']=4;self.save()
        with self.assertRaisesRegex(ValueError,'metric mismatch'):verify_collection(self.study_dir,self.collection,'train')

    def test_changed_recovery_cannot_survive_raw_audits(self):
        self.rows[0]['recovery_excess_queue_area_vehicle_s']=5;self.save()
        with self.assertRaisesRegex(ValueError,'recovery metric'):verify_collection(self.study_dir,self.collection,'train')

    def test_missing_original_evidence_hashes_rejected(self):
        self.rows[0]['raw_files_sha256'].pop('tripinfo.xml');self.save()
        with self.assertRaisesRegex(ValueError,'original raw'):verify_collection(self.study_dir,self.collection,'train')


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.out=self.root/'local-runtime/selection'
        self.study={'source':{'source_commit':'unit'},'dependencies':{},'spec':{'civilian_weight':1,
            'model_specification':{'max_depth':3,'min_samples_leaf':5}},
            'protocol':{'schema':'afterlight.protocol.v1','feature_schema':[]}}
        self.envelope={'sha256':'unit','study':self.study}
        self.verified={'files_sha256':{},'candidate_rows':[{'unit':True}]*5}
        for split in ('train','validation'):
            directory=self.root/split;directory.mkdir()
            path=directory/'candidate-outcomes.json';path.write_text(json.dumps(self.verified['candidate_rows']))
            self.verified['files_sha256']['candidate-outcomes.json']=file_hash(path)
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.network.ROOT',self.root))
        stack.enter_context(patch('evaluation.study_reporting.load_study',return_value=self.envelope))
        stack.enter_context(patch('evaluation.study_reporting.assert_study_runtime'))
        stack.enter_context(patch('evaluation.study_reporting.verify_collection',return_value=self.verified))
        stack.enter_context(patch('evaluation.study_reporting.objective',return_value=1))
        stack.enter_context(patch('models.residual.select_fixed_lead',return_value={'conclusive':True,'lead_s':5}))
        stack.enter_context(patch('evaluation.study_reporting.fixed_lead_artifact',return_value={'unit':'fixed'}))
        stack.enter_context(patch('evaluation.study_reporting.freeze_selectors'))
        self.ml=stack.enter_context(patch('evaluation.study_reporting.ml_runtime'))
        self.fit=stack.enter_context(patch('models.residual.fit_residual'))

    def select(self,fit=False):
        return select_study(self.root/'study',self.root/'train',self.root/'validation',self.out,fit_model=fit)

    def test_baseline_only_does_not_import_optional_ml(self):
        result=self.select()
        self.assertEqual(result['selection']['status'],'baseline_only')
        self.assertFalse(result['selection']['test_release_authorized'])
        self.ml.assert_not_called();self.fit.assert_not_called()

    def test_insufficient_labels_is_explicit_not_fabricated_model(self):
        result=self.select(True)
        self.assertIn('insufficient finite',result['selection']['reason'])
        self.assertEqual(result['selection']['finite_training_labels'],5)
        self.assertFalse((self.out/'model.json').exists());self.ml.assert_not_called();self.fit.assert_not_called()

    def test_inconclusive_fixed_comparator_does_not_fit(self):
        with patch('models.residual.select_fixed_lead',return_value={'conclusive':False}):result=self.select(True)
        self.assertEqual(result['selection']['status'],'inconclusive');self.fit.assert_not_called()

    def test_existing_selection_not_overwritten(self):
        self.select();before=(self.out/'selection.json').read_bytes()
        with self.assertRaises(FileExistsError):self.select()
        self.assertEqual((self.out/'selection.json').read_bytes(),before)

    def test_ml_runtime_drift_keeps_failure_without_model(self):
        self.study['spec']['model_specification']['min_samples_leaf']=2
        self.ml.side_effect=[{'packages':{'scikit-learn':'1.7.2'}},{'packages':{'scikit-learn':'changed'}}]
        self.fit.return_value={'model':{'sklearn_version':'1.7.2'}}
        with self.assertRaisesRegex(ValueError,'runtime changed'):self.select(True)
        self.assertTrue((self.out/'selection-failure.json').exists())
        self.assertFalse((self.out/'model.json').exists())

    def test_wrong_optional_sklearn_version_rejected(self):
        with patch('evaluation.study_reporting.metadata.version',return_value='wrong'),self.assertRaisesRegex(ValueError,'1.7.2'):
            ml_runtime()

class SelectionArtifactTests(unittest.TestCase):
    def setUp(self):
        from evaluation.selectors import analytical_artifact, fixed_lead_artifact
        from models.analytical import ESTIMATOR_VERSION, estimate_candidates
        from models.residual import DEFAULT_FEATURES, select_fixed_lead
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.protocol={'schema':'afterlight.protocol.v1','group_assignments':{'train':'train','validation':'validation'},
            'source_commit':'unit','civilian_weight':1,'horizon_s':100,'drain_end_s':200,
            'feature_schema':[{'name':name,'unit':'unit','source':'unit','sensor_lag_s':1} for name in DEFAULT_FEATURES],
            'analytical_estimator':{'version':ESTIMATOR_VERSION,'config':asdict(AnalyticalConfig())},
            'episode_inventory':[{'episode_id':split,'demand_group_id':split,'split':split,
                'demand_sha256':'demand-'+split,'network_sha256':'network','dispatch_s':20} for split in ('train','validation')],
            'model_specification':{'max_depth':3,'min_samples_leaf':5}}
        frozen={'sha256':digest(self.protocol),'protocol':self.protocol}
        self.study={'protocol':self.protocol,'source':{'source_commit':'unit'},'dependencies':{},
            'spec':{'model_specification':self.protocol['model_specification'],'civilian_weight':1},
            'episodes':[{'split':split,'case_id':split} for split in ('train','validation')]}
        observation={'dispatch_s':20,'sensor_lag_s':1,'observed_at_s':19,'values':{
            'queue_sum_veh':10,'queue_max_veh':10,'downstream_occupancy':0,'route_distance_m':500,
            'route_junction_count':3,'eta_remaining_s':40,'phase_elapsed_s':2}}
        costs={row['lead_s']:row['analytical_cost_s'] for row in estimate_candidates(observation)['scores']}
        validation=[{'episode_id':'validation','demand_group_id':'validation','split':'validation','policy':'fixed','lead_s':lead,
            'demand_sha256':'demand-validation','network_sha256':'network','source_commit':'unit','horizon_s':100,'drain_end_s':200,
            'status':'completed','validity_reasons':[],'ambulance_journey_s':20+(lead-5)**2,'civilian_mean_excess_s':0,
            'accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0},
            'observation':observation,'analytical_cost_s':costs[lead],
            'analytical_config_sha256':digest(self.protocol['analytical_estimator'])} for lead in (0,5,10,20,30)]
        analytical=analytical_artifact(frozen)
        fixed_result=select_fixed_lead(validation,1)
        fixed=fixed_lead_artifact(validation,frozen)
        pair={'schema':'afterlight.selector-freeze.v1','protocol_sha256':frozen['sha256'],'selected':analytical,'comparator':fixed}
        for name,value in [('analytical-selector.json',analytical),('fixed-selector.json',fixed),
                           ('validation-candidates.json',validation),
                           ('analytical-vs-fixed.json',{'sha256':digest(pair),'selectors':pair})]:
            (self.root/name).write_text(json.dumps(value))
        collections={}
        for split in ('train','validation'):
            names={'collection.json','outcomes.json','candidate-outcomes.json'}
            for policy,lead in POLICIES:
                directory=f'worlds/{split}/{policy}'+(f'-{lead}' if lead is not None else '')
                names.update(directory+'/'+name for name in RAW_FILES)
            collections[split]={name:'a'*64 for name in names}
        collections['validation']['candidate-outcomes.json']=file_hash(self.root/'validation-candidates.json')
        self.selection={'schema':'afterlight.study-selection.v2','study_sha256':'study','protocol_sha256':frozen['sha256'],
            'source':self.study['source'],'simulation_dependencies':{},'model_specification':self.protocol['model_specification'],
            'test_outcomes_accessed':False,'test_release_authorized':False,'status':'baseline_only',
            'collections':collections,'candidate_data_sha256':{'train':digest([]),'validation':digest(validation)},
            'finite_training_labels':5,'infeasible_training_rows':0,'validation_fixed_selection':fixed_result,
            'artifacts_sha256':{p.name:file_hash(p) for p in self.root.iterdir()}}
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('evaluation.study_reporting.load_study',return_value={'sha256':'study','study':self.study}))
        stack.enter_context(patch('evaluation.study_reporting.assert_study_runtime'))
        self.save()

    def save(self):
        (self.root/'selection.json').write_text(json.dumps({'sha256':digest(self.selection),'selection':self.selection}))

    def verify(self):
        from evaluation.study_reporting import verify_selection_artifacts
        return verify_selection_artifacts(self.root/'study',self.root)

    def test_baseline_artifacts_exactly_bound(self):
        self.assertEqual(self.verify()['selection']['status'],'baseline_only')

    def test_rehashed_inconsistent_fixed_comparator_rejected(self):
        self.selection['validation_fixed_selection']['lead_s']=30;self.save()
        with self.assertRaisesRegex(ValueError,'validation-only argmin'):self.verify()

    def test_rehashed_incomplete_collection_inventory_rejected(self):
        self.selection['collections']['train'].pop('outcomes.json');self.save()
        with self.assertRaisesRegex(ValueError,'full declared worlds'):self.verify()

    def test_extra_or_changed_artifacts_rejected(self):
        (self.root/'unexpected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'unexpected artifacts'):self.verify()

    def test_consistently_rehashed_weaker_fixed_baseline_rejected(self):
        self.selection['validation_fixed_selection']['lead_s']=30
        fixed=json.loads((self.root/'fixed-selector.json').read_text())
        fixed['selector']['lead_s']=30
        fixed['selector']['validation_selection']['lead_s']=30
        fixed['sha256']=digest(fixed['selector'])
        (self.root/'fixed-selector.json').write_text(json.dumps(fixed))
        pair=json.loads((self.root/'analytical-vs-fixed.json').read_text())
        pair['selectors']['comparator']=fixed;pair['sha256']=digest(pair['selectors'])
        (self.root/'analytical-vs-fixed.json').write_text(json.dumps(pair))
        for name in self.selection['artifacts_sha256']:
            self.selection['artifacts_sha256'][name]=file_hash(self.root/name)
        self.save()
        with self.assertRaisesRegex(ValueError,'validation-only argmin'):self.verify()

    def test_same_rows_different_bytes_cannot_replace_original_validation_snapshot(self):
        path=self.root/'validation-candidates.json'
        path.write_text(json.dumps(json.loads(path.read_text()),indent=2))
        self.selection['artifacts_sha256'][path.name]=file_hash(path);self.save()
        with self.assertRaisesRegex(ValueError,'original verified collection bytes'):self.verify()

    def test_legacy_selection_without_retained_evidence_rejected_explicitly(self):
        self.selection['schema']='afterlight.study-selection.v1';self.save()
        with self.assertRaisesRegex(ValueError,'schema v2'):self.verify()


class ArtifactPathTests(unittest.TestCase):
    def test_containment_checked_before_outcomes_read(self):
        from evaluation.study_reporting import _contained
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(Path,'is_symlink',return_value=True),self.assertRaisesRegex(ValueError,'symbolic links'):
                _contained(root,'outcomes.json')
            with self.assertRaises(ValueError):_contained(root,'../test/outcomes.json')
