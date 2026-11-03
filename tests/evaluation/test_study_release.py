"""Synthetic release/claim guards; no SUMO, model fitting or real test access."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.protocol import digest
from evaluation.study_release import release_test, load_test_release, claim_test_attempt


class StudyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.study_dir=self.root/'local-runtime/study';self.study_dir.mkdir(parents=True)
        self.selection_dir=self.root/'local-runtime/selection';self.selection_dir.mkdir()
        self.output=self.root/'local-runtime/test-attempt'
        self.study={'source':{'source_commit':'unit','source_dirty':False},'dependencies':{'sumo':'unit'},
                    'protocol':{'synthetic':True},'episodes':[{'episode_id':'test-a','split':'test'},{'episode_id':'train-a','split':'train'}]}
        self.study_envelope={'sha256':digest(self.study),'study':self.study}
        self.selection={'schema':'afterlight.study-selection.v2','status':'baseline_only',
            'validation_fixed_selection':{'conclusive':True},'source':self.study['source'],
            'simulation_dependencies':self.study['dependencies'],'study_sha256':self.study_envelope['sha256'],
            'protocol_sha256':digest(self.study['protocol']),'test_outcomes_accessed':False,'test_release_authorized':False,
            'artifacts_sha256':{'analytical-selector.json':'a','fixed-selector.json':'f','analytical-vs-fixed.json':'af'}}
        self.write_selection()
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.network.ROOT',self.root))
        stack.enter_context(patch('evaluation.study_release.load_study',return_value=self.study_envelope))
        stack.enter_context(patch('evaluation.study_release.assert_study_runtime'))
        stack.enter_context(patch('evaluation.study_release.assert_saved_inputs'))
        stack.enter_context(patch('evaluation.study_reporting.verify_selection_artifacts',side_effect=lambda *args:self.selection_envelope,create=True))

    def write_selection(self):
        self.selection_envelope={'sha256':digest(self.selection),'selection':deepcopy(self.selection)}
        (self.selection_dir/'selection.json').write_text(json.dumps(self.selection_envelope))

    def release(self):
        return release_test(self.study_dir,self.selection_dir,mode='baseline_only')

    def test_explicit_baseline_mode_binds_pair_and_full_test_inventory(self):
        result=self.release()
        self.assertEqual(result['release']['comparison_artifacts_sha256'],{'analytical-vs-fixed.json':'af'})
        self.assertIsNone(result['release']['selected_model_sha256'])
        self.assertEqual(result['release']['test_episode_ids'],['test-a'])
        self.assertEqual(result['release']['expected_worlds'],7)
        self.assertEqual(load_test_release(self.study_dir),result)
        self.assertFalse((self.study_dir/'test-attempt.json').exists())

    def test_learned_requires_both_frozen_comparisons_and_model_hash(self):
        self.selection['status']='learned_ready'
        self.selection['artifacts_sha256']={'model.json':'m','learned-selector.json':'l','fixed-selector.json':'f',
            'analytical-selector.json':'a','learned-vs-fixed.json':'lf','learned-vs-analytical.json':'la'}
        self.write_selection()
        result=release_test(self.study_dir,self.selection_dir,mode='learned')
        self.assertEqual(result['release']['selected_model_sha256'],'m')
        self.assertEqual(set(result['release']['comparison_artifacts_sha256']),{'learned-vs-fixed.json','learned-vs-analytical.json'})

    def test_no_silent_baseline_fallback(self):
        with self.assertRaisesRegex(ValueError,'complete conclusive'):
            release_test(self.study_dir,self.selection_dir,mode='learned')
        self.assertFalse((self.study_dir/'test-release.json').exists())

    def test_inconclusive_selection_cannot_release(self):
        self.selection['status']='inconclusive';self.selection['validation_fixed_selection']['conclusive']=False
        self.write_selection()
        with self.assertRaises(ValueError):self.release()
        self.assertFalse((self.study_dir/'test-release.json').exists())

    def test_failed_selection_directory_cannot_release(self):
        (self.selection_dir/'selection-failure.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Failed/partial'):self.release()
        self.assertFalse((self.study_dir/'test-release.json').exists())

    def test_release_is_exclusive_and_preserves_original_bytes(self):
        self.release();before=(self.study_dir/'test-release.json').read_bytes()
        with self.assertRaises(FileExistsError):self.release()
        self.assertEqual((self.study_dir/'test-release.json').read_bytes(),before)

    def test_mutated_selection_bytes_prevent_claim(self):
        release=self.release()
        with (self.selection_dir/'selection.json').open('a') as stream:stream.write(' ')
        with self.assertRaisesRegex(ValueError,'differs from frozen'):
            claim_test_attempt(self.study_dir,self.output,expected_release_sha256=release['sha256'])
        self.assertFalse((self.study_dir/'test-attempt.json').exists())

    def test_claim_is_exclusive_even_without_any_world_executed(self):
        release=self.release()
        claimed=claim_test_attempt(self.study_dir,self.output,expected_release_sha256=release['sha256'])
        self.assertEqual(claimed['attempt']['expected_worlds'],7)
        self.assertFalse(self.output.exists())
        before=(self.study_dir/'test-attempt.json').read_bytes()
        with self.assertRaises(FileExistsError):
            claim_test_attempt(self.study_dir,self.output,expected_release_sha256=release['sha256'])
        self.assertEqual((self.study_dir/'test-attempt.json').read_bytes(),before)

    def test_wrong_release_digest_and_existing_output_do_not_claim(self):
        release=self.release()
        with self.assertRaises(ValueError):claim_test_attempt(self.study_dir,self.output,expected_release_sha256='wrong')
        self.output.mkdir()
        with self.assertRaises(FileExistsError):claim_test_attempt(self.study_dir,self.output,expected_release_sha256=release['sha256'])
        self.assertFalse((self.study_dir/'test-attempt.json').exists())

    def test_changed_release_content_cannot_be_claimed(self):
        release=self.release()
        release['release']['test_episode_ids']=[]
        (self.study_dir/'test-release.json').write_text(json.dumps(release))
        with self.assertRaisesRegex(ValueError,'hash/schema'):
            claim_test_attempt(self.study_dir,self.output,expected_release_sha256=release['sha256'])
        self.assertFalse((self.study_dir/'test-attempt.json').exists())

    def test_symlink_release_marker_rejected_before_read(self):
        self.release()
        marker=self.study_dir/'test-release.json'
        original=Path.is_symlink
        def redirected(path):
            return True if path==marker else original(path)
        with patch.object(Path,'is_symlink',redirected),patch('evaluation.study_release.read_json') as reader:
            with self.assertRaisesRegex(ValueError,'must not be a symlink'):
                load_test_release(self.study_dir)
            reader.assert_not_called()

    def test_output_cannot_overlap_frozen_inputs(self):
        release=self.release()
        with self.assertRaisesRegex(ValueError,'overlap'):
            claim_test_attempt(self.study_dir,self.study_dir/'attempt',expected_release_sha256=release['sha256'])
        self.assertFalse((self.study_dir/'test-attempt.json').exists())


if __name__=='__main__':unittest.main()
