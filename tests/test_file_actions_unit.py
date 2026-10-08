import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'drive/utils/file_actions.py'
spec=importlib.util.spec_from_file_location('drive_file_actions_fixture',SOURCE);actions=importlib.util.module_from_spec(spec);spec.loader.exec_module(actions)

class FileActionTests(unittest.TestCase):
 def setUp(self):
  self.writes=[];self.locks=[]
  self.docs={key:SimpleNamespace(name=key,file_name=key+'.pdf',modified='old-db-time',file_modified='2026-10-08 12:00:00',team='team',folder='parent',is_folder=0,status='Active',permanent_delete=lambda key=key:self.writes.append(key)) for key in ['a','b']}
  self.files=[{'id':key,'name':key+'.pdf','modified':'2026-10-08 12:00:00'} for key in ['b','a']]
  def fail(message,kind):raise kind(message)
  def get_doc(doctype,name,for_update):
   self.assertEqual(doctype,'File');self.assertTrue(for_update);self.locks.append(name);return self.docs[name]
  self.frappe=SimpleNamespace(throw=fail,ValidationError=ValueError,PermissionError=PermissionError,TimestampMismatchError=RuntimeError,get_doc=get_doc)
  self.permissions=SimpleNamespace(get_teams=lambda:['team'],user_has_permission=lambda doc,kind:True)
  self.patcher=patch.dict('sys.modules',{'frappe':self.frappe,'drive.api.permissions':self.permissions});self.patcher.start();self.addCleanup(self.patcher.stop)
 def test_requires_explicit_confirmation_and_valid_bounded_unique_selection(self):
  for files,confirmed in [(self.files,False),(self.files,'true'),([],True),(self.files*26,True),([self.files[0]]*2,True),([{'id':'a'}],True)]:
   with self.assertRaises(ValueError):actions.delete_selected_files('team',files,confirmed)
  self.assertEqual(self.writes,[]);self.assertEqual(self.locks,[])
 def test_all_documents_are_locked_and_checked_before_deletion(self):
  result=actions.delete_selected_files('team',self.files,True)
  self.assertEqual(self.locks,['a','b']);self.assertEqual(self.writes,['a','b']);self.assertEqual(result,{'deleted':['a','b']})
 def test_denied_second_file_does_not_delete_first(self):
  self.permissions.user_has_permission=lambda doc,kind:getattr(doc,'name',doc)!='b'
  with self.assertRaises(PermissionError):actions.delete_selected_files('team',self.files,True)
  self.assertEqual(self.writes,[])
 def test_refuses_folders_foreign_teams_removed_files_and_stale_snapshots(self):
  for field,value,exception in [('is_folder',1,ValueError),('team','other',ValueError),('status','Removed',ValueError),('file_name','renamed.pdf',RuntimeError),('file_modified','later',RuntimeError)]:
   old=getattr(self.docs['b'],field);setattr(self.docs['b'],field,value)
   with self.assertRaises(exception):actions.delete_selected_files('team',self.files,True)
   setattr(self.docs['b'],field,old);self.assertEqual(self.writes,[])
 def test_permanently_removed_files_cannot_be_restored_through_trash_toggle(self):
  source=SOURCE.parents[1]/'api/files.py';tree=ast.parse(source.read_text())
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='remove_or_restore');fn.decorator_list=[]
  frappe=SimpleNamespace(throw=lambda message,kind:(_ for _ in ()).throw(kind(message)),ValidationError=ValueError,get_doc=lambda *args:SimpleNamespace(status='Removed'))
  namespace={'frappe':frappe,'json':json,'FileManager':lambda:None,'STATUS_ACTIVE':'Active','STATUS_TRASHED':'Trashed'}
  exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(source),'exec'),namespace)
  with self.assertRaisesRegex(ValueError,'définitivement'):namespace['remove_or_restore'](['a'])
 def test_inaccessible_team_never_reads_documents(self):
  with self.assertRaises(PermissionError):actions.delete_selected_files('other',self.files,True)
  self.assertEqual(self.locks,[])

if __name__=='__main__':unittest.main()
