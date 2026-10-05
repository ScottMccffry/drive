"""Exercise the production deletion hook with current and legacy settings schemas."""
import ast
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "drive/drive/doctype/drive_team/drive_team.py"
SETTINGS = ROOT / "drive/drive/doctype/drive_settings/drive_settings.json"

class TeamCleanupTests(unittest.TestCase):
    def run_cleanup(self, legacy):
        # Load the unchanged hook body without requiring a running Frappe database.
        tree = ast.parse(SOURCE.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DriveTeam")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "on_trash")
        fields = {f["fieldname"] for f in json.loads(SETTINGS.read_text())["fields"]}
        if legacy:
            fields.add("default_team")
        settings = SimpleNamespace(default_team="fixture-team", save=MagicMock())
        def query(doctype, filters, pluck):
            if "default_team" not in fields:
                raise AssertionError("A removed field must not be queried")
            if not isinstance(pluck, str):
                raise TypeError("Frappe v16 expects one scalar pluck field")
            return ["fixture-user"]
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            own = site / "private/files/drive/fixture-team"
            own.mkdir(parents=True)
            (own / "fixture.txt").write_text("temporary fixture")
            other = site / "private/files/drive/other-team"
            other.mkdir()
            (other / "keep.txt").write_text("unrelated content")
            frappe = SimpleNamespace(
                get_meta=lambda _: SimpleNamespace(has_field=lambda field: field in fields),
                get_list=MagicMock(side_effect=query),
                get_doc=MagicMock(return_value=settings),
                get_site_path=lambda: str(site),
                db=SimpleNamespace(commit=MagicMock(), delete=MagicMock()),
            )
            namespace = {
                "frappe": frappe, "Path": Path, "shutil": shutil,
                "get_home_folder": lambda _: SimpleNamespace(file_url="/private/files/drive/fixture-team"),
                "storage_key": lambda value: value.lstrip("/"),
            }
            exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), namespace)
            namespace["on_trash"](SimpleNamespace(name="fixture-team"))
            self.assertFalse(own.exists())
            self.assertEqual((other / "keep.txt").read_text(), "unrelated content")
            frappe.db.delete.assert_called_once_with("File", {"team": "fixture-team"})
            if legacy:
                self.assertEqual(settings.default_team, "")
                settings.save.assert_called_once()
            else:
                frappe.get_list.assert_not_called()
    def test_current_schema_removes_only_the_owned_directory(self):
        self.run_cleanup(False)
    def test_legacy_default_is_cleared_before_cleanup(self):
        self.run_cleanup(True)

if __name__ == "__main__":
    unittest.main()
