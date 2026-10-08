"""Exercise production folder storage methods without a Frappe installation."""
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from urllib.parse import unquote

SOURCE = Path(__file__).resolve().parents[1] / 'drive/utils/files.py'

class FolderPathTests(unittest.TestCase):
    def manager(self, site, s3=False):
        tree=ast.parse(SOURCE.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='FileManager')
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('get_disk_path','create_folder')]
        for method in methods: method.decorator_list=[]
        storage=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='storage_key')
        namespace={'Path':Path,'unquote':unquote,'S3_URL_PREFIX':'/api/method/drive.api.s3.fetch?path='}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[storage,ast.ClassDef(name='Manager',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])),str(SOURCE),'exec'),namespace)
        manager=namespace['Manager']();manager.flat=False;manager.site_folder=site;manager.s3_enabled=s3
        return manager
    def test_absolute_private_url_is_resolved_inside_site_and_nested_folders_work(self):
        with TemporaryDirectory() as root:
            site=Path(root);parent=site/'private/files/drive/team';parent.mkdir(parents=True)
            manager=self.manager(site)
            result=manager.create_folder(SimpleNamespace(team='team',file_name='test',parent_path=Path('/private/files/drive/team')),None)
            self.assertEqual(result,'private/files/drive/team/test/')
            self.assertTrue((parent/'test').is_dir())
            nested=manager.create_folder(SimpleNamespace(team='team',file_name='nested',parent_path=Path(result)),None)
            self.assertTrue((site/nested).is_dir())
            with self.assertRaises(FileExistsError):manager.create_folder(SimpleNamespace(team='team',file_name='test',parent_path=Path('/private/files/drive/team')),None)
    def test_s3_fetch_url_is_decoded_to_key(self):
        manager=self.manager(Path('/unused'),True)
        keys=[];manager.get_bucket=lambda team:'bucket'
        manager.conn=SimpleNamespace(put_object=lambda **kwargs:keys.append(kwargs))
        result=manager.create_folder(SimpleNamespace(team='team',file_name='test',parent_path='/api/method/drive.api.s3.fetch?path=team%20one/root'),None)
        self.assertEqual(result,'team one/root/test/')
        self.assertEqual(keys,[{'Bucket':'bucket','Key':result,'Body':''}])

if __name__=='__main__':unittest.main()
