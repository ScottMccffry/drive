"""Isolated regression tests for Drive moves; no Frappe site or network needed."""

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1] / "drive"


def method(source, class_name, name, globals_):
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    fn.decorator_list = []
    namespace = dict(globals_)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(source), "exec"), namespace)
    return namespace[name]


class StorageMoveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        (self.site / "old").mkdir()
        (self.site / "new").mkdir()
        self.manager = SimpleNamespace(site_folder=self.site, s3_enabled=False, flat=False)
        self.move = method(
            ROOT / "utils/files.py", "FileManager", "move",
            {"storage_key": lambda url: str(url).lstrip("/"), "shutil": __import__("shutil"), "Path": Path},
        )

    def test_missing_source_cannot_update_metadata(self):
        with self.assertRaisesRegex(RuntimeError, "source content is missing"):
            self.move(self.manager, SimpleNamespace(file_url="old/missing"), "new/file")
        self.assertFalse((self.site / "new/file").exists())

    def test_existing_destination_is_never_overwritten(self):
        (self.site / "old/file").write_bytes(b"source")
        (self.site / "new/file").write_bytes(b"existing")
        with self.assertRaisesRegex(RuntimeError, "destination already has content"):
            self.move(self.manager, SimpleNamespace(file_url="old/file"), "new/file")
        self.assertEqual((self.site / "old/file").read_bytes(), b"source")
        self.assertEqual((self.site / "new/file").read_bytes(), b"existing")

    def test_move_preserves_bytes(self):
        (self.site / "old/file").write_bytes(b"source")
        self.move(self.manager, SimpleNamespace(file_url="old/file"), "new/file")
        self.assertFalse((self.site / "old/file").exists())
        self.assertEqual((self.site / "new/file").read_bytes(), b"source")

    def test_same_path_is_a_noop(self):
        (self.site / "old/file").write_bytes(b"source")
        self.move(self.manager, SimpleNamespace(file_url="old/file"), "old/file")
        self.assertEqual((self.site / "old/file").read_bytes(), b"source")


class MetadataMoveTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        db = SimpleNamespace(
            get_value=lambda doctype, name, field: "folder name",
            savepoint=lambda name: self.events.append(("savepoint", name)),
            rollback=lambda **kwargs: self.events.append(("rollback", kwargs["save_point"])),
        )
        frappe = SimpleNamespace(
            db=db, session=SimpleNamespace(user="tester"),
            generate_hash=lambda length: "test123456", _dict=lambda **kw: SimpleNamespace(**kw),
            get_value=lambda *args, **kwargs: {"name": "new"},
            throw=lambda message, kind: (_ for _ in ()).throw(kind(message)),
            PermissionError=PermissionError,
        )
        self.move = method(
            ROOT / "overrides/file.py", "File", "move",
            {"frappe": frappe, "user_has_permission": lambda *args: True,
             "create_new_activity_log": lambda **kw: self.events.append(("activity", kw["entity"])),
             "update_file_size": lambda folder, delta: self.events.append(("size", folder, delta)),
             "get_new_file_name": lambda name, *args: name, "now": lambda: "new-time"},
        )
        def disk_move(entity, target):
            self.events.append(("disk", entity.file_url, target))
        manager = SimpleNamespace(flat=False, get_disk_path=lambda entity: Path("new") / entity.file_name, move=disk_move)
        self.file = SimpleNamespace(
            name="file-id", file_name="file.pdf", file_size=42, folder="old", team="team",
            file_url="old/file-id", is_folder=False, flags=SimpleNamespace(), manager=manager,
            get_children=lambda: [], _not_in_disk=lambda: False,
            recursive_path_move=lambda old, new: self.events.append(("recursive", old, new)),
            save=lambda: self.events.append(("save",)),
            db_set=lambda field, value: self.events.append(("db_set", field, value)),
        )

    def test_storage_path_is_string_when_saving(self):
        self.move(self.file, "new", "team")
        self.assertIn(("recursive", "old/file-id", "new/file.pdf"), self.events)
        self.assertNotIn("rollback", [event[0] for event in self.events])

    def test_failed_metadata_save_restores_blob_and_rolls_back_database(self):
        def fail_save():
            raise ValueError("simulated database failure")
        self.file.save = fail_save
        with self.assertRaisesRegex(ValueError, "simulated database failure"):
            self.move(self.file, "new", "team")
        self.assertIn(("disk", "old/file-id", "new/file.pdf"), self.events)
        self.assertIn(("disk", "new/file.pdf", "old/file-id"), self.events)
        self.assertIn(("rollback", "drive_move_test123456"), self.events)
        self.assertEqual(self.file.file_url, "old/file-id")
        self.assertEqual(self.file.folder, "old")

    def test_failed_disk_move_rolls_back_sizes_without_attempting_compensation(self):
        self.file.manager.move = lambda entity, target: (_ for _ in ()).throw(FileNotFoundError("source missing"))
        with self.assertRaisesRegex(FileNotFoundError, "source missing"):
            self.move(self.file, "new", "team")
        self.assertIn(("rollback", "drive_move_test123456"), self.events)
        self.assertEqual(self.file.folder, "old")

    def test_failed_modified_timestamp_also_restores_blob(self):
        self.file.db_set = lambda field, value: (_ for _ in ()).throw(ValueError("timestamp failed"))
        with self.assertRaisesRegex(ValueError, "timestamp failed"):
            self.move(self.file, "new", "team")
        self.assertIn(("disk", "new/file.pdf", "old/file-id"), self.events)
        self.assertIn(("rollback", "drive_move_test123456"), self.events)


if __name__ == "__main__":
    unittest.main()
