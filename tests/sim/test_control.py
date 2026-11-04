"""Owned-process cancellation contracts; never starts SUMO or traffic."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sim.control import RunControl, SimulationCancelled
from sim.run import run_pair


class ControlTests(unittest.TestCase):
    def test_pre_cancelled_control_never_starts_a_process_or_creates_output(self):
        control = RunControl()
        control.cancel()
        with patch('sim.control.subprocess.Popen') as popen:
            with self.assertRaises(SimulationCancelled):
                control.start_process(['not-executed'])
            popen.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            from types import SimpleNamespace
            target = Path(directory) / 'new-run'
            with self.assertRaises(SimulationCancelled):
                run_pair(SimpleNamespace(output=target), control=control)
            self.assertFalse(target.exists())
        control.close()

    def test_progress_uses_a_copy_and_stops_after_cancellation(self):
        events = []
        with RunControl(on_progress=events.append) as control:
            event = {'type': 'progress', 'phase': 'unit', 'completed_steps': 10}
            control.emit(event)
            event['completed_steps'] = 11
            self.assertEqual(events[0]['completed_steps'], 10)
            route = {'type': 'route', 'route_edges': ['first', 'last']}
            control.emit(route)
            events[-1]['route_edges'].append('consumer-edit')
            self.assertEqual(route['route_edges'], ['first', 'last'])
            control.cancel()
            with self.assertRaises(SimulationCancelled):
                control.progress('unit', 'must not reach callback')
            self.assertEqual(len(events), 2)

    def test_cancel_stops_only_its_owned_child_even_without_a_simulation_checkpoint(self):
        other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        control = RunControl()
        try:
            owned = control.start_process([sys.executable, '-c', 'import time; time.sleep(30)'])
            control.cancel()
            owned.wait(timeout=4)
            self.assertIsNotNone(owned.poll())
            self.assertIsNone(other.poll(), 'A request must never terminate unrelated processes')
        finally:
            control.close()
            other.terminate()
            other.wait(timeout=4)

    def test_cancel_interrupts_a_blocked_owned_command_and_reaps_it(self):
        event = threading.Event()
        control = RunControl(event)
        result = []
        def execute():
            try:
                control.run_command([sys.executable, '-c', 'import time; time.sleep(30)'], capture_output=True, text=True)
            except BaseException as exc:
                result.append(exc)
        worker = threading.Thread(target=execute)
        worker.start()
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                with control._lock:
                    if control._processes:
                        break
                time.sleep(.01)
            event.set()
            worker.join(timeout=4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(result), 1)
            self.assertIsInstance(result[0], SimulationCancelled)
            self.assertFalse(control._processes)
        finally:
            event.set()
            control.close()
            worker.join(timeout=4)

    def test_owned_command_keeps_stdout_stderr_exit_code_and_checked_failure(self):
        command = [sys.executable, '-c', 'import sys; print("out"); print("err",file=sys.stderr); sys.exit(3)']
        with RunControl() as control:
            result = control.run_command(command, capture_output=True, text=True)
            self.assertEqual((result.returncode, result.stdout.strip(), result.stderr.strip()), (3, 'out', 'err'))
            self.assertFalse(control._processes)
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                control.run_command(command, capture_output=True, text=True, check=True)
            self.assertEqual(raised.exception.returncode, 3)
            self.assertFalse(control._processes)

    def test_context_exit_reaps_an_owned_child_after_a_callback_error(self):
        owned = None
        with self.assertRaisesRegex(ValueError, 'closed stream'):
            with RunControl(on_progress=lambda event: (_ for _ in ()).throw(ValueError('closed stream'))) as control:
                owned = control.start_process([sys.executable, '-c', 'import time; time.sleep(30)'])
                control.progress('unit', 'callback failure')
        self.assertIsNotNone(owned.poll())

    def test_traci_startup_registers_owned_process_before_unpooled_connection(self):
        process = Mock()
        process.poll.return_value = None
        connection = Mock()
        class NotReady(Exception):
            pass
        traci = SimpleNamespace(connect=Mock(side_effect=[NotReady(), connection]),
                                exceptions=SimpleNamespace(FatalTraCIError=NotReady))
        miscutils = SimpleNamespace(getFreeSocketPort=lambda: 12345)
        with RunControl() as control, patch.dict(sys.modules, {'traci': traci, 'sumolib': SimpleNamespace(), 'sumolib.miscutils': miscutils}), \
             patch('sim.control.subprocess.Popen', return_value=process) as popen:
            actual, owned = control.start_traci(['sumo-test-only', '--seed', '7'], label='unit', stdout=None)
            self.assertIs(actual, connection)
            self.assertIs(owned, process)
            popen.assert_called_once_with(['sumo-test-only', '--seed', '7', '--remote-port', '12345'], stdout=None)
            self.assertEqual(traci.connect.call_args.kwargs['proc'], process)
            self.assertEqual(traci.connect.call_args.kwargs['host'], '127.0.0.1')
            self.assertNotIn('label', traci.connect.call_args.kwargs)
            self.assertIn(process, control._processes)

    def test_cancel_during_traci_startup_reaps_its_process_before_raising(self):
        process = Mock()
        process.poll.return_value = None
        class NotReady(Exception):
            pass
        with RunControl() as control:
            def connect(**kwargs):
                control.cancel()
                raise NotReady()
            traci = SimpleNamespace(connect=connect, exceptions=SimpleNamespace(FatalTraCIError=NotReady))
            miscutils = SimpleNamespace(getFreeSocketPort=lambda: 12345)
            with patch.dict(sys.modules, {'traci': traci, 'sumolib': SimpleNamespace(), 'sumolib.miscutils': miscutils}), \
                 patch('sim.control.subprocess.Popen', return_value=process):
                with self.assertRaises(SimulationCancelled):
                    control.start_traci(['sumo-test-only'], label='unit', stdout=None)
            process.terminate.assert_called()
            self.assertFalse(control._processes)


class WorldControlHookTests(unittest.TestCase):
    def run_fixture(self, directory, control=None, cancel_after=None):
        from sim.run import run_world
        connection = Mock()
        connection.getVersion.return_value = (0, 'SYNTHETIC TEST, NOT SUMO')
        for method in ('getDepartedIDList', 'getArrivedIDList', 'getCollidingVehiclesIDList', 'getStartingTeleportIDList'):
            getattr(connection.simulation, method).return_value = []
        connection.vehicle.getIDList.return_value = []
        if cancel_after is not None:
            def step():
                if connection.simulationStep.call_count == cancel_after:
                    control.cancel()
            connection.simulationStep.side_effect = step
        traci = SimpleNamespace(start=Mock(), getConnection=Mock(return_value=connection))
        cache = SimpleNamespace(vehicles={}, refresh=lambda ids: None, poses=lambda: [])
        process = Mock()
        process.poll.return_value = 0
        demand = {'network_kind': 'fixture', 'dispatch_s': 1, 'demand_end_s': 2, 'seed': 7,
                  'reference_definition': 'synthetic unit reference',
                  'vehicles': [{'id': 'ambulance', 'type': 'ambulance', 'route': ['edge'],
                                'depart_s': 1, 'depart_pos_m': 0, 'reference_s': 10}]}
        network = {'signals': {}, 'edges': {'edge': {'length_m': 100, 'speed_mps': 10, 'lanes': ['edge_0']}}}
        analytical = {'lead_s': 0}
        with patch.dict(sys.modules, {'traci': traci}), patch('sim.run.validate_saved_demand'), \
             patch('sim.run.binary', return_value='not-started'), patch('sim.traci_cache.ObservationCache', return_value=cache), \
             patch('sim.run.choose_lead', return_value=analytical), patch('sim.run.reconcile_tripinfo', return_value=[]):
            if control is not None:
                control.start_traci = Mock(return_value=(connection, process))
            result = run_world(world_id='baseline', policy='ordinary', lead_s=0,
                               network_dir=directory, demand_dir=directory, demand=demand, network=network,
                               output=directory/'world', horizon_s=10, drain_s=0, step_s=.5, sample_s=.5,
                               control=control)
        return result, connection, traci

    def test_optional_progress_reports_only_completed_steps_and_preserves_sampled_output(self):
        events = []
        with tempfile.TemporaryDirectory() as directory, RunControl(on_progress=events.append) as control:
            controlled, connection, traci = self.run_fixture(Path(directory), control)
            traci.start.assert_not_called()
            self.assertEqual(connection.simulationStep.call_count, 20)
        with tempfile.TemporaryDirectory() as directory:
            original, connection, traci = self.run_fixture(Path(directory))
            traci.start.assert_called_once()
            traci.getConnection.assert_called_once()
        for field in ('frames', 'events', 'decision', 'status'):
            self.assertEqual(controlled[field], original[field])
        self.assertEqual(len(controlled['frames']), 21)
        actual = [event for event in events if event['phase'] == 'simulating']
        self.assertEqual([(e['completed_steps'], e['total_steps'], e['simulation_time_s']) for e in actual],
                         [(10, 20, 5), (20, 20, 10)])

    def test_mid_world_cancellation_has_no_completed_outcome(self):
        events = []
        with tempfile.TemporaryDirectory() as directory, RunControl(on_progress=events.append) as control:
            with self.assertRaises(SimulationCancelled):
                self.run_fixture(Path(directory), control, cancel_after=11)
            world = Path(directory)/'world'
            self.assertTrue((world/'cancelled.json').is_file())
            self.assertFalse((world/'outcome.json').exists())
            actual = [event for event in events if event['phase'] == 'simulating']
            self.assertEqual([event['completed_steps'] for event in actual], [10])


if __name__ == '__main__':
    unittest.main()
