"""Package metadata fixtures only; no simulator or wheel execution."""
import importlib.metadata
import unittest
from unittest.mock import patch
from sim.run import dependency_versions


class DependencyMetadataTests(unittest.TestCase):
    def metadata(self, names):
        def version(name):
            if name not in names:
                raise importlib.metadata.PackageNotFoundError(name)
            return '1.28.0'
        return version

    def test_records_required_data_companion(self):
        names={'traci','sumolib','eclipse-sumo','sumo-data'}
        with patch('sim.run.importlib.metadata.version', side_effect=self.metadata(names)):
            self.assertEqual(set(dependency_versions()), names)

    def test_refuses_incomplete_wheel_installation(self):
        with patch('sim.run.importlib.metadata.version', side_effect=self.metadata({'traci','sumolib','eclipse-sumo'})):
            with self.assertRaisesRegex(RuntimeError, 'sumo-data'):
                dependency_versions()

    def test_portable_binary_mode_has_truthful_null_metadata(self):
        with patch('sim.run.importlib.metadata.version', side_effect=self.metadata({'traci','sumolib'})):
            versions=dependency_versions()
            self.assertIsNone(versions['eclipse-sumo'])
            self.assertIsNone(versions['sumo-data'])


if __name__=='__main__':
    unittest.main()
