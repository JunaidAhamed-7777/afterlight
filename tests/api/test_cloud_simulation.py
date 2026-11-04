"""Cloud packaging/lifecycle fixtures only: no simulation or benefit evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cloud.simulation import cloud_parameters, run_cloud_simulation
from sim.control import RunControl, SimulationCancelled


REQUEST = {'request_id': 'a' * 32, 'pickup': 'P001', 'hospital': 'HOSP_EAST'}


def replay_fixture():
    from sim.network import ROOT, load_graph, shortest_route
    graph = load_graph('city')
    pickup = next(point for point in graph['pickups'] if point['id'] == REQUEST['pickup'])
    hospital = next(point for point in graph['hospitals'] if point['id'] == REQUEST['hospital'])
    return {
        'schema': 'afterlight.replay.v1', 'mode': 'recorded', 'duration_s': 900, 'step_s': .5,
        'scenario': {'id': 'synthetic-contract-only', 'network_kind': 'city', 'seed': 7, 'regime': 'moderate',
                     'dispatch_s': 60, 'pickup_id': 'P001', 'hospital_id': 'HOSP_EAST', 'split': 'pilot',
                     'route_edges': shortest_route(graph, pickup['edge_id'], hospital['destination_node'])},
        'coordinates': {'source': 'canonical XY meters', 'position_reference': 'front_bumper', 'render': '[x,z,-y]'},
        'provenance': {'source_commit': 'synthetic-unit-fixture', 'sumo_version': 'NO SUMO EXECUTION',
                       'network_sha256': 'a' * 64, 'demand_sha256': 'b' * 64,
                       'canonical_map_sha256': hashlib.sha256((ROOT/'assets/map/city_manifest.json').read_bytes()).hexdigest()},
        'worlds': {key: {'world_id': key, 'policy': 'ordinary' if key == 'baseline' else 'fixed',
                        'lead_s': 0 if key == 'baseline' else 20, 'status': 'censored',
                        'metrics': {'simulation_step_s': .5, 'horizon_s': 360, 'drain_end_s': 900}, 'events': [],
                        'frames': [{'t': index / 2, 'vehicles': [], 'signals': [], 'queue_count': 0}
                                   for index in range(1801)]}
                   for key in ('baseline', 'afterlight')},
    }


def runner_for(replay, captured=None, wrong_hash=False):
    def run(args, *, control):
        if captured is not None:
            captured.append(args)
        args.output.mkdir(parents=True)
        payload = (json.dumps(replay, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        (args.output / 'replay.json').write_bytes(payload)
        return {'sha256': '0' * 64 if wrong_hash else hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
    return run


class CloudSimulationTests(unittest.TestCase):
    def test_request_uses_all_canonical_anchor_choices_but_no_user_physics_or_paths(self):
        from sim.network import load_graph
        graph = load_graph('city')
        for pickup in (graph['pickups'][0], graph['pickups'][-1]):
            for hospital in graph['hospitals']:
                params = cloud_parameters({**REQUEST, 'pickup': pickup['id'], 'hospital': hospital['id']})
                self.assertEqual(params, {'network': 'city', 'seed': 7, 'regime': 'moderate', 'policy': 'fixed', 'lead': 20,
                                          'pickup': pickup['id'], 'hospital': hospital['id']})
        for request in ({}, {**REQUEST, 'output': '../study'}, {**REQUEST, 'seed': 8},
                        {**REQUEST, 'pickup': '../P001'}, {**REQUEST, 'hospital': None},
                        {**REQUEST, 'request_id': '../' + 'a' * 32}):
            with self.assertRaises(ValueError):
                cloud_parameters(request)

    def test_context_exposes_exact_lossless_bytes_only_until_transfer_finishes(self):
        replay = replay_fixture()
        captured, events = [], []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / 'unrelated-evidence.txt'
            sentinel.write_text('unchanged', encoding='utf-8')
            with patch('cloud.simulation.run_pair', side_effect=runner_for(replay, captured)):
                with run_cloud_simulation(REQUEST, RunControl(on_progress=events.append), root) as result:
                    raw = result['replay_path'].read_bytes()
                    compressed = result['gzip_path'].read_bytes()
                    self.assertEqual(gzip.decompress(compressed), raw)
                    self.assertEqual(result['decoded_sha256'], hashlib.sha256(raw).hexdigest())
                    self.assertEqual(result['compressed_sha256'], hashlib.sha256(compressed).hexdigest())
                    self.assertEqual((result['decoded_bytes'], result['compressed_bytes']), (len(raw), len(compressed)))
                    self.assertEqual(result['world_status'], {'baseline': 'censored', 'afterlight': 'censored'})
                    self.assertIn('not a frozen-study', result['interpretation'])
                    raw_path = result['replay_path']
                self.assertFalse(raw_path.exists())
            self.assertEqual(list(root.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(), 'unchanged')
        args = captured[0]
        self.assertEqual((args.dispatch, args.demand_end, args.horizon, args.drain, args.step, args.sample, args.split),
                         (60, 180, 360, 540, .5, .5, 'pilot'))
        self.assertEqual([event['phase'] for event in events], ['preparing', 'validating_export', 'compressing', 'ready'])

    def test_wrong_request_or_capture_protocol_is_rejected_and_temp_output_removed(self):
        changes = [
            lambda r: r['scenario'].update(seed=8), lambda r: r['scenario'].update(pickup_id='P002'),
            lambda r: r['scenario'].update(hospital_id='HOSP_WEST'), lambda r: r['scenario'].update(split='test'),
            lambda r: r['scenario'].update(dispatch_s=50), lambda r: r['scenario'].update(regime='heavy'),
            lambda r: r.update(step_s=1), lambda r: r['worlds']['afterlight'].update(lead_s=10),
            lambda r: r['worlds']['afterlight'].update(policy='analytical'), lambda r: r.pop('coordinates'),
            lambda r: r['scenario'].update(route_edges=['wrong-edge']),
            lambda r: r['provenance'].update(canonical_map_sha256='0' * 64),
            lambda r: r['worlds']['baseline']['metrics'].update(simulation_step_s=1),
            lambda r: r['worlds']['baseline']['metrics'].update(horizon_s=300),
            lambda r: r['worlds']['baseline'].update(status='infrastructure_error'),
        ]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                replay = replay_fixture()
                change(replay)
                with patch('cloud.simulation.run_pair', side_effect=runner_for(replay)):
                    with self.assertRaises((ValueError, KeyError)):
                        with run_cloud_simulation(REQUEST, RunControl(), Path(directory)):
                            self.fail('Invalid capture must not be advertised')
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_wrong_runner_hash_is_rejected_before_any_result_is_yielded(self):
        with tempfile.TemporaryDirectory() as directory, patch('cloud.simulation.run_pair', side_effect=runner_for(replay_fixture(), wrong_hash=True)):
            with self.assertRaisesRegex(ValueError, 'recorded identity'):
                with run_cloud_simulation(REQUEST, RunControl(), Path(directory)):
                    self.fail('Changed data must not be yielded')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cancellation_during_execution_removes_only_owned_output(self):
        def cancelled(args, *, control):
            args.output.mkdir()
            (args.output / 'partial').write_text('incomplete')
            control.cancel()
            control.check_cancelled()
        with tempfile.TemporaryDirectory() as directory, patch('cloud.simulation.run_pair', side_effect=cancelled):
            with self.assertRaises(SimulationCancelled):
                with run_cloud_simulation(REQUEST, RunControl(), Path(directory)):
                    self.fail('Cancelled runs have no completed replay')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cancellation_during_transfer_keeps_no_success_or_temp_output(self):
        with tempfile.TemporaryDirectory() as directory, patch('cloud.simulation.run_pair', side_effect=runner_for(replay_fixture())):
            control = RunControl()
            with self.assertRaises(SimulationCancelled):
                with run_cloud_simulation(REQUEST, control, Path(directory)) as result:
                    self.assertTrue(result['gzip_path'].is_file())
                    control.cancel()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_size_limits_are_actual_reads_and_physical_transfer_limits(self):
        for limit in ('MAX_DECODED_BYTES', 'MAX_COMPRESSED_BYTES'):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                with patch('cloud.simulation.run_pair', side_effect=runner_for(replay_fixture())), patch('cloud.simulation.' + limit, 32):
                    with self.assertRaisesRegex(ValueError, 'bounded'):
                        with run_cloud_simulation(REQUEST, RunControl(), Path(directory)):
                            self.fail('Oversized result must not be sent')
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_replay_change_between_validation_and_packaging_is_rejected(self):
        captured = []
        def progress(event):
            if event['phase'] == 'compressing':
                (captured[0].output / 'replay.json').write_bytes(b'changed after validation')
        with tempfile.TemporaryDirectory() as directory, patch('cloud.simulation.run_pair', side_effect=runner_for(replay_fixture(), captured)):
            with self.assertRaisesRegex(ValueError, 'changed while packaging'):
                with run_cloud_simulation(REQUEST, RunControl(on_progress=progress), Path(directory)):
                    self.fail('Changed bytes must not become a completed transfer')
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
