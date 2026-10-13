import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build-maintenance-release.py'
SPEC = importlib.util.spec_from_file_location('maintenance_dispatch', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintenanceDispatchTests(unittest.TestCase):
    def test_existing_axcl_16g_plan_uses_registered_builder(self):
        selected = MODULE.command(
            'dshanpi-a1', '2026.10.09-4', ROOT / 'output/repository'
        )
        self.assertEqual('python3', selected[0])
        self.assertTrue(selected[1].endswith('/scripts/build-axcl-16g-release.py'))
        self.assertEqual('2026.10.09-4', selected[2])

    def test_full_image_plan_is_not_dispatched_as_maintenance(self):
        with self.assertRaisesRegex(ValueError, 'unsupported maintenance adapter'):
            MODULE.command('dshanpi-a1', '2026.10.10-1', ROOT / 'output/repository')


if __name__ == '__main__':
    unittest.main()
