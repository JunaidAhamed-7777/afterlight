"""Synthetic offline export tests; no simulator, training or test-data access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.protocol import digest
from export.selected_replay import verify_case_traces, assemble_replay
from export.replay import validate_replay, validate_selection_evidence

HASH='a'*64
SOURCE={'source_commit':'b'*40,'source_dirty':False,'source_code_sha256':HASH,'source_files':{}}


def world(policy,lead):
    return {'world_id':policy+(f'-{lead}' if lead is not None else ''),'policy':policy,'lead_s':lead,
        'status':'completed','sumo_version':'SUMO-unit-only',
        'decision':{'t':1,'kind':'dispatch','policy':policy,'selected_lead_s':lead,'observation':{'dispatch_s':1,'sensor_lag_s':1,'observed_at_s':0,'values':{}},'request_plan':{}},
        'metrics':{'status':'completed','runtime_s':.01},'events':[],
        'frames':[{'t':t,'vehicles':[],'signals':[],'queue_count':0} for t in (0,1,2)]}


def inputs():
    episode={'episode_id':'episode-unit','case_id':'case-unit','split':'test','seed':101,'regime':'sparse','dispatch_s':1,
        'pickup_id':'P001','hospital_id':'HOSP_EAST','demand_sha256':HASH,'demand_manifest_sha256':HASH,'demand_group_id':HASH,'network_sha256':HASH}
    contract={'case_ids':['case-unit'],'max_world_bytes':1024*1024,'max_total_bytes':8*1024*1024}
    study={'source':SOURCE,'protocol':{'unit':'synthetic'},'spec':{'network_kind':'city','illustrative_capture':contract,
        'timing':{'horizon_s':1,'drain_s':1,'sample_s':1}},'episodes':[episode],
        'network':{'manifest':{'network_sha256':HASH,'network_file_sha256':HASH,'network_hash_definition':'unit','canonical_map_sha256':HASH}},
        'dependencies':{},'pilot_evidence':{'sumo_version':'SUMO-unit-only'}}
    return {'sha256':digest(study),'study':study},episode


def selection(episode,lead=10,kind='residual_tree'):
    evidence={key:HASH for key in ('selector_sha256','study_sha256','protocol_sha256','release_sha256','report_sha256',
        'selection_sha256','trace_manifest_sha256','collection_manifest_sha256','comparison_artifact_sha256')}
    evidence.update(schema='afterlight.selection-evidence.v1',selector_kind=kind,model_sha256=HASH if kind=='residual_tree' else None,
        model_file_sha256=HASH if kind=='residual_tree' else None,case_id=episode['case_id'],episode_id=episode['episode_id'],selected_lead_s=lead,
        source_world_aliases={alias:{'original_world_id':name,'trace_sha256':HASH,'trace_file':f"worlds/{episode['case_id']}/{name}/rich-world.json"}
            for alias,name in [('baseline','ordinary'),('afterlight',f'fixed-{lead}')]},
        interpretation='Model-selected recorded fixed policy, not evidence of gain')
    return evidence


class ReplayAssemblyTests(unittest.TestCase):
    def make(self,kind='residual_tree'):
        study,episode=inputs();pair={'baseline':{'world':world('ordinary',None)},'afterlight':{'world':world('fixed',10)}}
        original=deepcopy(pair)
        replay=assemble_replay(study,episode,pair,{'signals':{}},{'vehicles':[{'id':'ambulance','route':['a','b']}]},selection(episode,kind=kind))
        self.assertEqual(pair,original)
        return replay,pair

    def test_exact_physics_unchanged_only_display_world_alias_differs(self):
        replay,pair=self.make()
        for alias,item in pair.items():
            projected=deepcopy(replay['worlds'][alias]);projected['world_id']=item['world']['world_id']
            self.assertEqual(projected,item['world'])
        self.assertEqual(replay['worlds']['afterlight']['policy'],'fixed')
        self.assertEqual(replay['selection_evidence']['selector_kind'],'residual_tree')

    def test_invalid_and_censored_outcomes_are_not_replaced_or_promoted(self):
        for state in ('invalid','censored'):
            study,episode=inputs();selected=world('fixed',10);selected['status']=state;selected['metrics']['status']=state
            replay=assemble_replay(study,episode,{'baseline':{'world':world('ordinary',None)},'afterlight':{'world':selected}},
                {'signals':{}},{'vehicles':[{'id':'ambulance','route':['a']}]},selection(episode))
            self.assertEqual(replay['worlds']['afterlight']['status'],state)

    def test_explicit_analytical_selection_has_no_model(self):
        replay,_=self.make('analytical');validate_replay(replay)
        self.assertIsNone(replay['provenance']['model_sha256'])

    def test_policy_lead_model_and_episode_mismatch_reject(self):
        for field in ('policy','lead','model','episode','missing-episode'):
            replay,_=self.make()
            if field=='policy':replay['worlds']['afterlight']['policy']='learned'
            elif field=='lead':replay['selection_evidence']['selected_lead_s']=20
            elif field=='model':replay['provenance']['model_sha256']=None
            elif field=='episode':replay['selection_evidence']['episode_id']='other'
            else:
                del replay['selection_evidence']['episode_id'];del replay['scenario']['episode_id']
            with self.subTest(field=field),self.assertRaises(ValueError):validate_selection_evidence(replay)

    def test_trace_reference_never_external_fetch_or_path_escape(self):
        for path in ('https://example.invalid/trace','../trace','worlds/case-unit/fixed-20/rich-world.json','C:\\trace.json'):
            replay,_=self.make();replay['selection_evidence']['source_world_aliases']['afterlight']['trace_file']=path
            with self.subTest(path=path),self.assertRaises(ValueError):validate_selection_evidence(replay)

    def test_bool_alias_leads_reject_and_integral_float_uses_canonical_path(self):
        replay,_=self.make()
        replay['selection_evidence']['selected_lead_s']=10.0
        validate_selection_evidence(replay)
        for field in ('world','decision'):
            replay,_=self.make();replay['selection_evidence']['selected_lead_s']=0
            replay['worlds']['afterlight']['lead_s']=0;replay['worlds']['afterlight']['decision']['selected_lead_s']=0
            replay['selection_evidence']['source_world_aliases']['afterlight']['trace_file']='worlds/case-unit/fixed-0/rich-world.json'
            if field=='world':replay['worlds']['afterlight']['lead_s']=False
            else:replay['worlds']['afterlight']['decision']['selected_lead_s']=False
            with self.subTest(field=field),self.assertRaises(ValueError):validate_selection_evidence(replay)

    def test_missing_selection_evidence_keeps_original_replay_compatible(self):
        replay,_=self.make();del replay['selection_evidence'];validate_replay(replay)


class TraceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.study,self.episode=inputs();self.entries=[];self.rows=[]
        for policy,lead in [('ordinary',None),*(('fixed',lead) for lead in (0,5,10,20,30))]:
            value=world(policy,lead);directory='worlds/case-unit/'+value['world_id'];relative=directory+'/rich-world.json'
            raw=self.write(relative,value)
            outcome_bytes=self.write(directory+'/outcome.json',{k:v for k,v in value.items() if k!='frames'})
            signal={k:value[k] for k in ('policy','status','events','decision','metrics')}
            signal['frames']=[{'t':f['t'],'signals':f['signals']} for f in value['frames']]
            signal_bytes=self.write(directory+'/signal-audit-input.json',signal)
            entry={'episode_id':self.episode['episode_id'],'case_id':'case-unit','policy':policy,'lead_s':lead,
                'demand_sha256':HASH,'network_sha256':HASH,'state':'retained','file':relative,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'reason':None}
            self.entries.append(entry);self.rows.append({'episode_id':self.episode['episode_id'],'policy':policy,'lead_s':lead,
                'raw_world_directory':directory,'illustrative_trace':deepcopy(entry),'raw_files_sha256':{'outcome.json':hashlib.sha256(outcome_bytes).hexdigest(),'signal-audit-input.json':hashlib.sha256(signal_bytes).hexdigest()}})
        self.refresh()

    def write(self,relative,value):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(value,separators=(',',':')).encode();path.write_bytes(raw);return raw

    def refresh(self):
        total=sum(e['bytes'] for e in self.entries)
        traces={'schema':'afterlight.illustrative-traces.v1','study_sha256':self.study['sha256'],
            'protocol_sha256':digest(self.study['study']['protocol']),'source':SOURCE,'split':'test',
            'contract':self.study['study']['spec']['illustrative_capture'],'charged_bytes':total,'retained_bytes':total,'status':'complete','entries':self.entries}
        raw=self.write('traces.json',{'sha256':digest(traces),'traces':traces})
        self.verified={'rows':self.rows,'manifest':{'illustrative_capture':{key:traces[key] for key in ('contract','charged_bytes','retained_bytes','status')}|
            {'manifest_file':'traces.json','manifest_sha256':hashlib.sha256(raw).hexdigest()}}}

    def check(self):return verify_case_traces(self.root,self.study,self.verified,'case-unit')

    def test_all_six_traces_are_bound_to_audited_outcomes_and_signal_frames(self):
        self.assertEqual(len(self.check()['traces']),6)

    def test_missing_unselected_candidate_still_rejects(self):
        self.entries.pop();self.refresh()
        with self.assertRaisesRegex(ValueError,'six illustrative'):self.check()

    def test_modified_trace_bytes_rejected(self):
        path=self.root/self.entries[-1]['file'];path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'byte identity'):self.check()

    def test_outcome_and_signal_divergence_rejected(self):
        directory=self.rows[-1]['raw_world_directory'];self.write(directory+'/outcome.json',{'different':True})
        with self.assertRaisesRegex(ValueError,'outcome hash'):self.check()

    def test_budget_failure_is_not_silently_substituted(self):
        self.entries[-1]['state']='budget_exceeded';self.refresh()
        with self.assertRaisesRegex(ValueError,'unavailable'):self.check()

    def test_unplanned_case_and_redirected_path_rejected(self):
        with self.assertRaisesRegex(ValueError,'predeclared'):verify_case_traces(self.root,self.study,self.verified,'other')
        self.entries[0]['file']='../outside';self.refresh()
        with self.assertRaises(ValueError):self.check()


if __name__=='__main__':unittest.main()
