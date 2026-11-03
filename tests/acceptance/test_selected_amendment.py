"""Post-report trace-adapter guards; no outcomes, simulator, fitting or traces."""
from pathlib import Path
import hashlib
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from scripts import export_selected_amended as adapter


class SelectedAmendmentTests(unittest.TestCase):
    def test_amended_report_gate_precedes_test_collection_or_output(self):
        runtime=Path(__file__).resolve().parents[2]/'local-runtime'
        analysis=SimpleNamespace(verify_report_artifacts=Mock(side_effect=ValueError('wrong amendment')),
                                 verify_released_test_collection=Mock())
        with patch.multiple(adapter,load_study=Mock(return_value={'study':{}}),
                            assert_study_runtime=Mock(),create=True),patch.object(Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'wrong amendment'):
                adapter.export_selected_amended(runtime/'study',runtime/'test',runtime/'report','case',runtime/'output',
                    analysis_module=analysis,analysis_binding={'sha256':'synthetic'})
            analysis.verify_released_test_collection.assert_not_called()
            mkdir.assert_not_called()
            analysis.verify_report_artifacts.assert_called_once_with(runtime/'study',runtime/'test',runtime/'report',
                analysis_amendment={'sha256':'synthetic'})

    def cli_fixture(self, root, output):
        original=root/'export'/'selected_replay.py';original.parent.mkdir()
        original.write_bytes(b'synthetic original source, never executed')
        frozen={'study':{'source':{'source_files':{'export/selected_replay.py':hashlib.sha256(original.read_bytes()).hexdigest()}}}}
        argv=['export_selected_amended.py','--checkout',str(root),'--study','local-runtime/study',
              '--collection','local-runtime/test','--report','local-runtime/report',
              '--amendment','local-runtime/bundle/analysis-amendment.json','--output',str(output),'--case','case']
        return frozen,argv

    def test_cli_rejected_existing_destination_does_not_write_failure_marker_into_evidence(self):
        for reason in ('wrong amendment','overlap existing evidence'):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);output=root/'local-runtime'/'study';output.mkdir(parents=True)
                (output/'study.json').write_bytes(b'original untouched study bytes')
                frozen,argv=self.cli_fixture(root,output)
                before={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
                loader=SimpleNamespace(load_amended_analysis=Mock(return_value=(object(),{},{})))
                with patch.dict(sys.modules,{'run_analysis_amendment':loader}),patch.object(sys,'argv',argv),\
                     patch('evaluation.study_manifest.load_study',return_value=frozen),\
                     patch.object(adapter,'export_selected_amended',side_effect=ValueError(reason)):
                    with self.assertRaisesRegex(ValueError,reason):adapter.main()
                after={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
                self.assertEqual(before,after)

    def test_cli_post_success_identity_failure_marks_only_owned_fresh_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'local-runtime'/'new-export'
            output.parent.mkdir();frozen,argv=self.cli_fixture(root,output)
            def exported(*args,**kwargs):
                output.mkdir();(output/'replay.json').write_bytes(b'new owned export')
                return {'status':'exported'}
            loader=SimpleNamespace(load_amended_analysis=Mock(side_effect=[(object(),{'sha256':'initial'},{}),
                                                                          (object(),{'sha256':'changed'},{})]))
            with patch.dict(sys.modules,{'run_analysis_amendment':loader}),patch.object(sys,'argv',argv),\
                 patch('evaluation.study_manifest.load_study',return_value=frozen),\
                 patch.object(adapter,'export_selected_amended',side_effect=exported):
                with self.assertRaisesRegex(ValueError,'changed during trace export'):adapter.main()
            self.assertTrue((output/'export-failure.json').is_file())
            self.assertEqual((output/'replay.json').read_bytes(),b'new owned export')


if __name__=='__main__':unittest.main()
