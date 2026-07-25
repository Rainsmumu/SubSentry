import json
import tempfile
import unittest
from pathlib import Path

from windows_manage import activate, backup, initialize, rollback


class WindowsManageTests(unittest.TestCase):
    def _root(self, parent: str) -> Path:
        root = Path(parent) / "SubSentry"
        root.mkdir()
        return root

    def test_initialize_preserves_shared_data_and_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._root(temp)
            (root / "versions" / "v1").mkdir(parents=True)
            bootstrap = root / "bootstrap"
            bootstrap.mkdir()
            source = bootstrap / "latest.xlsx"
            source.write_bytes(b"xlsx")
            reference = bootstrap / "reference"
            reference.mkdir()
            (reference / "manual.xlsx").write_bytes(b"manual")

            initialize(str(root), "v1", str(source), str(reference))

            self.assertFalse((root / "current_version.txt").exists())
            self.assertEqual(
                (root / "data/uploads/current_circuit_table.xlsx").read_bytes(),
                b"xlsx",
            )
            self.assertTrue((root / "reference/manual.xlsx").is_file())
            meta = json.loads(
                (root / "data/uploads/current_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["original_name"], "latest.xlsx")

    def test_activate_backup_and_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._root(temp)
            (root / "versions" / "v1").mkdir(parents=True)
            (root / "versions" / "v2").mkdir(parents=True)
            (root / "data").mkdir()
            (root / "data/fault_state.json").write_text('{"events":[]}')
            (root / "reference").mkdir()
            (root / "reference/manual.xlsx").write_bytes(b"manual")

            activate(str(root), "v1")
            activate(str(root), "v2")
            backup_path = backup(str(root), "update")
            self.assertTrue((backup_path / "data/fault_state.json").is_file())
            self.assertTrue((backup_path / "reference/manual.xlsx").is_file())

            self.assertEqual(rollback(str(root)), "v1")
            self.assertEqual((root / "current_version.txt").read_text().strip(), "v1")


if __name__ == "__main__":
    unittest.main()
