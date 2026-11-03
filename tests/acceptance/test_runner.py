"""Mock subprocess acceptance-runner tests. They never execute acceptance steps."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('omen_acceptance',ROOT/'scripts/omen_acceptance.py')
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)
COMMIT='a'*40
IDENTITY={'source':{'source_commit':COMMIT,'source_dirty':False,'source_code_sha256':'fixture','source_files':{}},
          'acceptance_files':{'unit-only':'fixture'},'acceptance_input_sha256':'fixture'}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'web/tests').mkdir(parents=True)
        (self.root/'web/tests/unit.test.ts').write_text('// synthetic unit fixture\n')
        (self.root/'web/tests/test_released_study_guards.py').write_text('# synthetic subprocess fixture; never executed\n')
        self.output=self.root/'local-runtime/acceptance/unit-attempt'
        self.calls=[]

    def identity(self,root):return deepcopy(IDENTITY)

    def spawn(self,codes=None,interrupt=False):
        codes=iter(codes or [0]*10)
        def start(argv,**kwargs):
            self.calls.append((argv,kwargs))
            self.assertIs(kwargs['shell'],False)
            self.assertEqual(kwargs['env']['PYTHONDONTWRITEBYTECODE'],'1')
            self.assertTrue(Path(kwargs['env']['TEMP']).is_relative_to(self.output))
            kwargs['stdout'].write(b'synthetic stdout\n');kwargs['stderr'].write(b'synthetic stderr\n')
            owner=self
            class Child:
                pid=4321
                def wait(self):
                    saved=json.loads((owner.output/'run.json').read_text())
                    self_step=next(step for step in saved['steps'] if step['status']=='running')
                    owner.assertEqual(self_step['child_pid'],self.pid)
                    owner.assertEqual(self_step['argv'],argv)
                    if interrupt:raise KeyboardInterrupt('synthetic interrupted wait')
                    return next(codes)
            return Child()
        return start

    def execute(self,**kwargs):
        return runner.execute(self.root,self.output,COMMIT,confirm_no_active_runs=True,
            identity_fn=kwargs.pop('identity_fn',self.identity),popen_fn=kwargs.pop('popen_fn',self.spawn()),node='node-unit-fixture',**kwargs)

    def test_plan_is_read_only_and_excludes_build_traffic_training_and_browser(self):
        value=runner.plan(self.root,self.output,python='python-unit-fixture',node='node-unit-fixture')
        self.assertFalse(self.output.exists())
        self.assertEqual(len(value['steps']),10)
        guard=next(step for step in value['steps'] if step['id']=='python-study-proof-guards')
        self.assertEqual(guard['argv'],['python-unit-fixture','-B',str(self.root/'web/tests/test_released_study_guards.py')])
        flattened=[arg for step in value['steps'] for arg in step['argv']]
        self.assertNotIn('sim.run',flattened);self.assertNotIn('evaluation.collector',flattened)
        self.assertNotIn('build',flattened);self.assertNotIn('browser_smoke.py',flattened)
        self.assertEqual(value['steps'][-2]['argv'][-1],str(self.output/'networks/fixture'))
        self.assertEqual(value['steps'][-1]['argv'][-1],str(self.output/'networks/city'))

    def test_complete_records_actual_pids_commands_logs_and_exit_codes(self):
        result=self.execute()
        self.assertEqual(result['status'],'completed');self.assertEqual(len(self.calls),10)
        self.assertIsNone(result['active_child_pid'])
        self.assertEqual(runner.status(self.root,self.output)['state'],'completed')
        for step in result['steps']:
            self.assertEqual(step['exit_code'],0);self.assertEqual(step['child_pid'],4321)
            self.assertEqual((self.output/step['stdout']).read_bytes(),b'synthetic stdout\n')
            self.assertEqual((self.output/step['stderr']).read_bytes(),b'synthetic stderr\n')
            self.assertEqual(json.loads((self.output/'steps'/step['id']/'step.json').read_text()),step)

    def test_nonzero_exit_stops_first_failure_without_retry(self):
        with self.assertRaisesRegex(RuntimeError,'exit 3'):self.execute(popen_fn=self.spawn([3]))
        result=runner.status(self.root,self.output)
        self.assertEqual(result['state'],'failed');self.assertEqual(len(self.calls),1)
        self.assertEqual(result['record']['steps'][0]['exit_code'],3)
        self.assertTrue(all(step['status']=='planned' for step in result['record']['steps'][1:]))

    def test_interrupted_wait_remains_unresolved_and_blocks_new_attempt(self):
        with self.assertRaises(KeyboardInterrupt):self.execute(popen_fn=self.spawn(interrupt=True))
        result=runner.status(self.root,self.output)
        self.assertEqual(result['state'],'unresolved')
        self.assertEqual(result['record']['active_child_pid'],4321)
        with self.assertRaisesRegex(ValueError,'Unresolved earlier'):
            runner.execute(self.root,self.output.with_name('new-attempt'),COMMIT,confirm_no_active_runs=True,
                identity_fn=self.identity,popen_fn=lambda *args,**kwargs:self.fail('must not launch'),node='node-unit-fixture')
        self.assertFalse(self.output.with_name('new-attempt').exists())

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir(parents=True);sentinel=self.output/'keep';sentinel.write_text('unchanged')
        with self.assertRaises(FileExistsError):self.execute()
        self.assertEqual(list(self.output.iterdir()),[sentinel]);self.assertEqual(sentinel.read_text(),'unchanged')

    def test_unknown_empty_previous_attempt_blocks_execution(self):
        self.output.with_name('earlier-crash').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'Unresolved earlier'):self.execute()
        self.assertFalse(self.output.exists());self.assertEqual(self.calls,[])

    def test_explicit_operator_preflight_required_before_any_write(self):
        with self.assertRaisesRegex(ValueError,'operator confirmation'):
            runner.execute(self.root,self.output,COMMIT,confirm_no_active_runs=False,identity_fn=self.identity,node='node-unit-fixture')
        self.assertFalse(self.output.exists())

    def test_wrong_commit_and_dirty_source_never_launch(self):
        for change in ({'source_commit':'b'*40},{'source_dirty':True}):
            identity=deepcopy(IDENTITY);identity['source'].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'expected commit'):
                self.execute(identity_fn=lambda root:identity)
            self.assertFalse(self.output.exists())
        self.assertEqual(self.calls,[])

    def test_source_change_during_step_invalidates_even_zero_exit(self):
        calls=0
        def changed(root):
            nonlocal calls
            calls+=1;identity=deepcopy(IDENTITY)
            if calls>=3:identity['acceptance_input_sha256']='changed'
            return identity
        with self.assertRaisesRegex(ValueError,'Source changed during'):self.execute(identity_fn=changed)
        result=runner.status(self.root,self.output)
        self.assertEqual(result['state'],'failed');self.assertEqual(len(self.calls),1)
        self.assertEqual(result['record']['steps'][0]['status'],'invalid_source')
        self.assertEqual(result['record']['steps'][0]['exit_code'],0)

    def test_launch_exception_is_unresolved_not_assumed_process_exit(self):
        def launch(*args,**kwargs):raise OSError('synthetic process launch failure')
        with self.assertRaises(OSError):self.execute(popen_fn=launch)
        self.assertEqual(runner.status(self.root,self.output)['state'],'unresolved')

    def test_status_does_not_infer_liveness_or_spawn(self):
        with patch.object(runner.subprocess,'Popen',side_effect=AssertionError('status cannot start commands')):
            self.assertEqual(runner.status(self.root,self.output)['state'],'unresolved')
        self.assertFalse(self.output.exists())

    def test_malformed_or_nonfinite_status_record_is_unresolved(self):
        self.output.mkdir(parents=True)
        for payload in ('{"schema":"afterlight.acceptance-run.v1","steps":[] ,"status":"failed"}',
                        '{"schema":"afterlight.acceptance-run.v1","extra":1e309}'):
            (self.output/'run.json').write_text(payload)
            self.assertEqual(runner.status(self.root,self.output)['state'],'unresolved')

    def test_output_escape_and_runtime_redirect_rejected(self):
        with self.assertRaises(ValueError):runner.plan(self.root,self.root/'outside',node='node-unit-fixture')
        original=runner._redirected
        with patch.object(runner,'_redirected',side_effect=lambda path:path==self.root/'local-runtime' or original(path)):
            with self.assertRaises(ValueError):runner.plan(self.root,self.output,node='node-unit-fixture')
        self.assertFalse(self.output.exists())


class InputIdentityTests(unittest.TestCase):
    def test_raw_api_bytes_not_cached_git_status_define_committed_identity(self):
        from sim.source_identity import blob_id
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'api').mkdir();path=root/'api/example.py';payload=b'value=1\n';path.write_bytes(payload);path.chmod(0o644)
            files={'api/example.py':payload,
                'preview/manifest.json':json.dumps({'source_files':{},'output_files':{},'runtime_assets':{}}).encode(),
                'web/package.json':b'{"dependencies":{},"devDependencies":{}}',
                'web/package-lock.json':b'{"packages":{}}'}
            for relative,data in files.items():
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(0o644)
            def git(root,*args):
                if args[0]=='ls-tree':return b''.join(f'100644 blob {blob_id(data,"sha1")}\t{name}\0'.encode() for name,data in sorted(files.items()))
                if args[:2]==('ls-files','--stage'):return b''.join(f'100644 {blob_id(data,"sha1")} 0\t{name}\0'.encode() for name,data in sorted(files.items()))
                if args[:2]==('ls-files','--others'):return b''
                if args==('rev-parse','--show-object-format'):return b'sha1\n'
                if args==('rev-parse','--verify','HEAD'):return (COMMIT+'\n').encode()
                raise AssertionError('Unexpected command/stat-cache dependency')
            with patch('sim.source_identity.source_snapshot',return_value=deepcopy(IDENTITY['source'])),patch.object(runner,'_git',side_effect=git):
                identity=runner.capture_identity(root)
                self.assertEqual(identity['acceptance_files']['api/example.py'],hashlib.sha256(payload).hexdigest())
                path.write_bytes(b'value=2\n')
                with self.assertRaisesRegex(ValueError,'differs from HEAD'):runner.capture_identity(root)


class DependencyMetadataTests(unittest.TestCase):
    def test_installed_version_and_metadata_hash_are_recorded_not_code_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);package=root/'web/node_modules/three/package.json'
            package.parent.mkdir(parents=True);payload=b'{"version":"0.180.0"}';package.write_bytes(payload)
            installed=root/'web/node_modules/.package-lock.json';installed.write_bytes(b'{"packages":{}}')
            result=runner._node_metadata(root,{'dependencies':{'three':'0.180.0'}},
                {'packages':{'node_modules/three':{'version':'0.180.0'}}})
            self.assertEqual(result['packages']['three']['version'],'0.180.0')
            self.assertEqual(result['packages']['three']['package_json_sha256'],hashlib.sha256(payload).hexdigest())
            self.assertEqual(result['installed_lock_sha256'],hashlib.sha256(installed.read_bytes()).hexdigest())
            self.assertIn('NOT verified',result['verification_scope'])

    def test_mismatched_installed_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);package=root/'web/node_modules/three/package.json'
            package.parent.mkdir(parents=True);package.write_text('{"version":"0.179.0"}')
            with self.assertRaisesRegex(ValueError,'differs from lock'):
                runner._node_metadata(root,{'dependencies':{'three':'0.180.0'}},
                    {'packages':{'node_modules/three':{'version':'0.180.0'}}})

    def test_manifest_input_escape_rejected_before_git_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'preview').mkdir();(root/'web').mkdir()
            (root/'preview/manifest.json').write_text(json.dumps({'source_files':{'../outside.py':'a'*64},'output_files':{},'runtime_assets':{}}))
            (root/'web/package.json').write_text('{}');(root/'web/package-lock.json').write_text('{}')
            with patch('sim.source_identity.source_snapshot',return_value=deepcopy(IDENTITY['source'])),patch.object(runner,'_git') as git:
                with self.assertRaisesRegex(ValueError,'Unsafe'):runner.capture_identity(root)
                git.assert_not_called()


if __name__=='__main__':unittest.main()
