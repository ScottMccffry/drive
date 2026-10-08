"""Execute the production permission functions with a fake Frappe boundary."""
import ast
import __future__
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

class AccessTests(unittest.TestCase):
 def setUp(self):
  tree=ast.parse((Path(__file__).parents[1]/'drive/api/permissions.py').read_text())
  tree.body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('restrict_access','get_user_access','user_has_permission')]
  self.f=SimpleNamespace(whitelist=lambda **kw:lambda fn:fn,session=SimpleNamespace(user='member'),get_hooks=lambda key:['policy'],get_attr=MagicMock(),get_cached_doc=lambda *args:{'team':'company'})
  self.ns={'frappe':self.f,'NO_ACCESS':{k:0 for k in ['read','comment','share','write','upload']},'is_site_file':lambda doc:False}
  exec(compile(tree,'permissions.py','exec',flags=__future__.annotations.compiler_flag),self.ns)
 def test_owned_file_permissions_are_capped(self):
  self.ns['_get_user_access']=lambda *args:{'read':1,'write':1,'upload':1,'share':1,'comment':1,'type':'admin'}
  self.f.get_attr.return_value=lambda **kw:{'read':1}
  self.assertEqual(self.ns['get_user_access']({'team':'company'}),{'read':1,'write':0,'upload':0,'share':0,'comment':0,'type':'guest'})
 def test_extension_cannot_elevate_native_permissions(self):
  self.f.get_attr.return_value=lambda **kw:{k:1 for k in self.ns['NO_ACCESS']}
  self.assertEqual(self.ns['restrict_access']({},'member',dict(self.ns['NO_ACCESS']))['write'],0)
 def test_creation_is_denied_for_readonly_members(self):
  self.f.get_attr.return_value=lambda **kw:{'read':1}
  self.assertFalse(self.ns['user_has_permission']({},'create'))
 def test_unmanaged_personal_files_keep_native_access(self):
  self.f.get_attr.return_value=lambda **kw:None
  access={'read':1,'write':1,'type':'admin'}
  self.assertEqual(self.ns['restrict_access']({},'member',access),access)

if __name__=='__main__':unittest.main()
