"""Exercise the actual new-user hook without a database or network."""
import ast
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock, patch
import unittest


class AttrDict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class SessionTests(unittest.TestCase):
    def test_personal_team_creation_preserves_request_even_on_failure(self):
        tree = ast.parse((Path(__file__).parents[1] / 'drive/utils/users.py').read_text())
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'assign_drive_role_and_create_settings']
        for fail in (False, True):
            with self.subTest(fail=fail):
                session = AttrDict(user='Administrator', sid='original-http-sid', data=AttrDict(user='Administrator', csrf_token='fixture-csrf'))
                original = dict(session)
                form = {'token':'invitation-fixture'}
                f = SimpleNamespace(session=session, local=SimpleNamespace(session=session, form_dict=form), db=MagicMock(), get_doc=MagicMock())
                def set_user(user):
                    session.user=user;session.sid=user;session.data={};f.local.form_dict={}
                f.set_user=set_user
                product=ModuleType('drive.api.product')
                def create_team(**kw):
                    self.assertEqual(f.session.user,'new@example.invalid')
                    if fail: raise ValueError('team creation failed')
                product.create_team=MagicMock(side_effect=create_team)
                ns={'frappe':f}
                exec(compile(tree,'users.py','exec'),ns)
                with patch.dict('sys.modules',{'drive.api.product':product}):
                    try:
                        ns['assign_drive_role_and_create_settings'](SimpleNamespace(name='new@example.invalid',email='new@example.invalid'),'after_insert')
                    except ValueError:
                        self.assertTrue(fail)
                self.assertEqual(dict(session),original)
                self.assertIs(f.local.form_dict,form)
                product.create_team.assert_called_once()


if __name__ == '__main__': unittest.main()
