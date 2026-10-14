import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-release-executor.py"
SPEC = importlib.util.spec_from_file_location("release_executor", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseExecutorTests(unittest.TestCase):
    def lock(self, root: Path, image: bool) -> Path:
        path = root / "release.lock.json"
        data = {"schema_version": 1, "maintenance_adapter": "example"}
        if image:
            data.pop("maintenance_adapter")
            data["image_release"] = {"repository": "dshanpi/ArmBianOS"}
        path.write_text(json.dumps(data))
        return path

    def test_complete_image_testing_rejects_github_hosted_executor(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = self.lock(Path(temporary), image=True)
            with self.assertRaisesRegex(ValueError, "controlled local builder"):
                MODULE.validate(lock, "testing", "github-hosted")

    def test_complete_image_testing_allows_local_executor(self):
        with tempfile.TemporaryDirectory() as temporary:
            MODULE.validate(self.lock(Path(temporary), image=True), "testing", "local")

    def test_apt_operations_remain_available_on_github_hosted_executor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            MODULE.validate(self.lock(root, image=False), "testing", "github-hosted")
            MODULE.validate(self.lock(root, image=True), "testing-packages", "github-hosted")
            MODULE.validate(self.lock(root, image=True), "stable", "github-hosted")

    def test_package_only_operation_requires_complete_release_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "complete image release lock"):
                MODULE.validate(
                    self.lock(Path(temporary), image=False),
                    "testing-packages",
                    "github-hosted",
                )


if __name__ == "__main__":
    unittest.main()
