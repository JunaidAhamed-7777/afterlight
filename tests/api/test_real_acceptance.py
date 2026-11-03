"""Mock client protocol checks only; never starts a server or SUMO process."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import api_real_acceptance as client

COMMIT='a'*40
IDENTITY={'source':{'source_commit':COMMIT,'source_dirty':False,'source_files':{},'source_code_sha256':'b'*64}}


class RealAcceptanceClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.patch=patch.object(client,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.output=self.root/'local-runtime/api-unit'
        self.identity=lambda root:deepcopy(IDENTITY)
        self.journal=client.prepare(self.output,'http://127.0.0.1:8765',COMMIT,identity_fn=self.identity)
        self.identifier=self.journal['request']['request_id'];self.calls=[]

    def job(self,state='completed'):
        return {'id':self.identifier,'parameters':dict(client.PARAMETERS),'status':state,'created_at':1,'started_at':2,'finished_at':3,'replay_sha256':'c'*64}

    def transport(self,base,method,path,body=None):
        self.calls.append((method,path,body))
        if path=='/api/health':return 200,b'{"generation_available":true}'
        return (202 if method=='POST' else 200),json.dumps(self.job()).encode()

    def terminal(self,*args):return {'replay_sha256':'c'*64,'raw_files_sha256':{},'job_identity':{key:self.job()[key] for key in ('id','created_at','started_at','finished_at','replay_sha256')}}

    def test_prepare_persists_exact_request_before_any_network_and_is_fresh_only(self):
        saved=json.loads((self.output/'request.json').read_text())
        self.assertEqual(saved,self.journal['request']);self.assertEqual(self.journal['state'],'prepared')
        self.assertEqual(self.calls,[])
        with self.assertRaises(FileExistsError):client.prepare(self.output,'http://127.0.0.1:8765',COMMIT,identity_fn=self.identity)

    def test_known_ack_authorizes_exact_idempotency_probe_not_new_id(self):
        with patch.object(client,'verified_terminal',side_effect=self.terminal):
            result=client.execute(self.output,confirm_no_active_runs=True,transport=self.transport,identity_fn=self.identity)
        posts=[entry for entry in self.calls if entry[0]=='POST']
        self.assertEqual(len(posts),2);self.assertEqual(posts[0][2],posts[1][2]);self.assertEqual(result['state'],'terminal_verified')
        with self.assertRaises(ValueError):client.execute(self.output,confirm_no_active_runs=True,transport=self.transport,identity_fn=self.identity)
        self.assertEqual(len([entry for entry in self.calls if entry[0]=='POST']),2)

    def test_lost_first_post_response_never_retries_or_changes_id(self):
        def lost(base,method,path,body=None):
            self.calls.append((method,path,body))
            if method=='POST':raise TimeoutError('synthetic response loss')
            return 200,b'{"generation_available":true}'
        with self.assertRaises(TimeoutError):client.execute(self.output,confirm_no_active_runs=True,transport=lost,identity_fn=self.identity)
        self.assertEqual(len([entry for entry in self.calls if entry[0]=='POST']),1)
        saved=json.loads((self.output/'journal.json').read_text());self.assertEqual(saved['state'],'unresolved')
        self.assertEqual(saved['request']['request_id'],self.identifier)
        before=(self.output/'journal.json').read_bytes()
        result=client.status(self.output,transport=self.transport)
        self.assertEqual(result['state'],'completed');self.assertEqual((self.output/'journal.json').read_bytes(),before)
        self.assertEqual(self.calls[-1][0],'GET')

    def test_keyboard_interrupt_marks_post_uncertain_without_retry(self):
        def interrupted(base,method,path,body=None):
            self.calls.append(method)
            if method=='POST':raise KeyboardInterrupt()
            return 200,b'{"generation_available":true}'
        with self.assertRaises(KeyboardInterrupt):client.execute(self.output,confirm_no_active_runs=True,transport=interrupted,identity_fn=self.identity)
        saved=json.loads((self.output/'journal.json').read_text())
        self.assertEqual(saved['state'],'unresolved');self.assertEqual(saved['error_type'],'KeyboardInterrupt')
        self.assertEqual(saved['requests'][-1]['state'],'uncertain');self.assertEqual(self.calls.count('POST'),1)
        self.assertTrue((self.output/'run-started.json').exists())

    def test_404_status_is_unresolved_and_read_only(self):
        before=(self.output/'journal.json').read_bytes()
        def missing(base,method,path,body=None):
            self.assertEqual(method,'GET');return 404,b'{}'
        self.assertEqual(client.status(self.output,transport=missing)['state'],'unresolved')
        self.assertEqual((self.output/'journal.json').read_bytes(),before)

    def test_client_deadline_does_not_kill_or_resubmit(self):
        def running(base,method,path,body=None):
            self.calls.append((method,path,body))
            if path=='/api/health':return 200,b'{"generation_available":true}'
            return (202 if method=='POST' else 200),json.dumps(self.job('running')).encode()
        ticks=iter([0,2])
        with self.assertRaises(TimeoutError):client.execute(self.output,confirm_no_active_runs=True,monitor_s=1,transport=running,
            identity_fn=self.identity,clock=lambda:next(ticks),sleep=lambda delay:self.fail('Deadline should already expire'))
        self.assertEqual(len([entry for entry in self.calls if entry[0]=='POST']),2)
        self.assertEqual(json.loads((self.output/'journal.json').read_text())['state'],'unresolved')

    def test_existing_exclusive_run_claim_blocks_concurrent_or_crash_retry(self):
        (self.output/'run-started.json').write_text('{"synthetic":"prior claim"}')
        with self.assertRaises(FileExistsError):client.execute(self.output,confirm_no_active_runs=True,transport=self.transport,identity_fn=self.identity)
        self.assertEqual(self.calls,[])
        self.assertEqual(json.loads((self.output/'journal.json').read_text())['state'],'prepared')

    def test_polling_cannot_accept_recreated_job_with_same_id_and_parameters(self):
        def recreated(base,method,path,body=None):
            self.calls.append((method,path,body))
            if path=='/api/health':return 200,b'{"generation_available":true}'
            job=self.job('running' if method=='POST' else 'completed')
            if method=='GET':job['created_at']=99
            return (202 if method=='POST' else 200),json.dumps(job).encode()
        with self.assertRaisesRegex(ValueError,'creation identity changed'):
            client.execute(self.output,confirm_no_active_runs=True,transport=recreated,identity_fn=self.identity,sleep=lambda delay:None)
        self.assertEqual(json.loads((self.output/'journal.json').read_text())['state'],'unresolved')
        self.assertEqual(len([entry for entry in self.calls if entry[0]=='POST']),2)

    def test_operator_and_source_preflight_block_before_network(self):
        with self.assertRaises(ValueError):client.execute(self.output,confirm_no_active_runs=False,transport=self.transport,identity_fn=self.identity)
        with self.assertRaises(ValueError):client.execute(self.output,confirm_no_active_runs=True,transport=self.transport,identity_fn=lambda root:{'changed':True})
        self.assertEqual(self.calls,[])

    def test_request_tampering_and_remote_origins_reject(self):
        for value in ('https://example.invalid','http://127.0.0.1:80','http://localhost:8765/path','http://user@localhost:8765'):
            with self.subTest(value=value),self.assertRaises(ValueError):client.origin(value)
        value=json.loads((self.output/'request.json').read_text());value['seed']=8
        (self.output/'request.json').write_text(json.dumps(value))
        with self.assertRaises(ValueError):client.status(self.output,transport=self.transport)
        self.assertEqual(self.calls,[])

    def test_recovery_requires_prior_verified_terminal_and_manual_confirmation(self):
        with self.assertRaises(ValueError):client.verify_recovery(self.output,confirm_server_restarted_after_terminal=True,transport=self.transport,identity_fn=self.identity)
        with self.assertRaises(ValueError):client.verify_recovery(self.output,confirm_server_restarted_after_terminal=False,transport=self.transport,identity_fn=self.identity)
        self.assertEqual(self.calls,[])

    def test_recovery_gets_known_terminal_before_exact_post_and_never_repeats(self):
        value=deepcopy(self.journal);value.update(state='terminal_verified',terminal_evidence=self.terminal())
        client._atomic(self.output/'journal.json',value)
        with patch.object(client,'raw_inventory',return_value={}),patch.object(client,'verified_terminal',side_effect=self.terminal):
            result=client.verify_recovery(self.output,confirm_server_restarted_after_terminal=True,transport=self.transport,identity_fn=self.identity)
            self.assertEqual([entry[0] for entry in self.calls],['GET','POST'])
            self.assertEqual(result['state'],'recovery_verified')
            with self.assertRaises(ValueError):client.verify_recovery(self.output,confirm_server_restarted_after_terminal=True,transport=self.transport,identity_fn=self.identity)

    def test_recovery_interrupt_is_unresolved_and_exclusive_claim_remains(self):
        value=deepcopy(self.journal);value.update(state='terminal_verified',terminal_evidence=self.terminal())
        client._atomic(self.output/'journal.json',value)
        def interrupted(base,method,path,body=None):
            self.assertEqual(method,'GET');raise KeyboardInterrupt()
        with patch.object(client,'raw_inventory',return_value={}):
            with self.assertRaises(KeyboardInterrupt):client.verify_recovery(self.output,confirm_server_restarted_after_terminal=True,transport=interrupted,identity_fn=self.identity)
        saved=json.loads((self.output/'journal.json').read_text())
        self.assertEqual(saved['state'],'recovery_unresolved');self.assertEqual(saved['requests'][-1]['state'],'uncertain')
        self.assertTrue((self.output/'recovery-started.json').exists())

    def test_recovery_404_never_posts(self):
        value=deepcopy(self.journal);value.update(state='terminal_verified',terminal_evidence=self.terminal())
        client._atomic(self.output/'journal.json',value)
        def missing(base,method,path,body=None):self.calls.append(method);return 404,b'{}'
        with patch.object(client,'raw_inventory',return_value={}):
            with self.assertRaises(ValueError):client.verify_recovery(self.output,confirm_server_restarted_after_terminal=True,transport=missing,identity_fn=self.identity)
        self.assertEqual(self.calls,['GET']);self.assertTrue((self.output/'recovery-started.json').exists())


if __name__=='__main__':unittest.main()
