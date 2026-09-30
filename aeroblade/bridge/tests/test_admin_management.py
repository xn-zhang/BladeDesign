import concurrent.futures
import json
import pathlib
import sys
import time
import tempfile
import sqlite3
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from session_store import StateStore, AuthError
from design_assistant import ModelService
from user_services import UserServices


class AdminManagementTests(unittest.TestCase):
    def setUp(self):
        self.state = StateStore()
        self.state.create_admin('admin', 'fixture-password-123')
        self.admin = self.state.admin_id()
        self.user = self.state.register('alice', 'fixture-password-123', self.state.create_invite(self.admin)['code'], 'test')['id']
        self.services = UserServices(self.state, ModelService(environ={}, store=self.state))

    def tearDown(self):
        self.services.close()
        self.state.close()

    def test_invite_edit_preserves_usage_and_revocation(self):
        invite = self.state.create_invite(self.admin, expires_in=3600, max_uses=2)
        self.state.register('bob', 'fixture-password-123', invite['code'], 'test')
        expiry = int(time.time()) + 7200
        self.state.update_invite(self.admin, invite['id'], expiry, 3)
        row = next(i for i in self.state.list_invites(self.admin) if i['id'] == invite['id'])
        self.assertEqual((row['used_count'], row['max_uses'], row['expires_at']), (1, 3, expiry))
        with self.assertRaises(AuthError):self.state.update_invite(self.admin, invite['id'], expiry, 0)
        self.state.revoke_invite(self.admin, invite['id'])
        with self.assertRaises(AuthError):self.state.update_invite(self.admin, invite['id'], expiry, 3)
        with self.assertRaises(AuthError):self.state.update_invite(self.user, invite['id'], expiry, 3)

    def test_force_logout_invalidates_all_sessions_without_disabling_user(self):
        first, _ = self.state.login('alice', 'fixture-password-123', 'a')
        second, _ = self.state.login('alice', 'fixture-password-123', 'b')
        self.state.force_logout(self.admin, self.user)
        self.assertIsNone(self.state.session(first))
        self.assertIsNone(self.state.session(second))
        self.assertFalse(self.state.user(self.user)['disabled'])
        with self.assertRaises(AuthError):self.state.force_logout(self.user, self.admin)

    def test_public_model_fallback_private_override_and_no_secret_disclosure(self):
        self.services.public_models.configure({'provider':'general', 'base_url':'https://model.example/v1', 'model':'shared', 'api_key':'shared-secret'})
        self.state.set_model_policy(self.admin, {'enabled':{'general':True,'domain':False}, 'default_provider':'general', 'daily_limit':2})
        model = self.services.for_user({'user_id':self.user})['models']
        public = model.describe()
        self.assertTrue(public['providers']['general']['configured'])
        self.assertEqual(public['providers']['general']['source'], 'public')
        self.assertNotIn('shared-secret', json.dumps(public))
        self.assertNotIn('model.example', json.dumps(public))
        self.assertEqual(model.get_config('general')['model'], 'shared')
        model.configure({'provider':'general','base_url':'https://private.example/v1','model':'mine','api_key':'private-secret'})
        self.assertEqual(model.get_config('general')['model'], 'mine')
        model.clear('general')
        self.state.set_model_policy(self.admin, {'enabled':{'general':False,'domain':False}, 'default_provider':'general', 'daily_limit':2})
        self.assertIsNone(model.get_config('general'))

    def test_atomic_daily_quota_persists_usage_and_rolls_over_in_shanghai_time(self):
        self.state.set_model_policy(self.admin, {'enabled':{'general':True,'domain':False}, 'default_provider':'general', 'daily_limit':2})
        def consume(_):
            try:self.state.consume_public_call(self.user);return True
            except AuthError as error:self.assertEqual(error.status,429);return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(sum(pool.map(consume, range(6))), 2)
        self.assertEqual(self.state.public_usage(self.user)['used'], 2)
        with patch('session_store.time.time', return_value=time.time()+86400):
            self.state.consume_public_call(self.user)
            self.assertEqual(self.state.public_usage(self.user)['used'], 1)

    def test_public_chat_enforces_quota_and_private_calls_do_not_consume_it(self):
        self.services.public_models.configure({'provider':'general','base_url':'https://model.example/v1','model':'shared','auth':'none'})
        self.state.set_model_policy(self.admin, {'enabled':{'general':True,'domain':False}, 'default_provider':'general', 'daily_limit':1})
        model = self.services.for_user({'user_id':self.user})['models']
        # Only the external HTTP transport is replaced; routing, validation and quota stay real.
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,_):return b'{"choices":[{"message":{"content":"hello"}}]}'
        with patch.object(self.services.public_models.opener, 'open', return_value=Response()), patch.object(model.opener, 'open', return_value=Response()):
            model.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})
            with self.assertRaises(AuthError):model.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})
            model.configure({'provider':'general','base_url':'https://private.example/v1','model':'mine','auth':'none'})
            model.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})
        self.assertEqual(self.state.public_usage(self.user)['used'], 1)

    def test_audit_records_changes_and_excludes_keys_and_invite_codes(self):
        invite = self.state.create_invite(self.admin)
        self.state.revoke_invite(self.admin, invite['id'])
        self.state.force_logout(self.admin, self.user)
        self.services.configure_public(self.admin, {'provider':'general','base_url':'https://model.example/v1','model':'shared','api_key':'never-log-key'})
        logs = self.state.admin_logs(self.admin)
        self.assertIn('public_model.configure', [row['action'] for row in logs])
        self.assertNotIn('never-log-key', json.dumps(logs))
        self.assertNotIn(invite['code'], json.dumps(logs))
        with self.assertRaises(AuthError):self.state.admin_logs(self.user)

    def test_public_connections_policy_usage_and_logs_survive_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/'state.sqlite3'
            state=StateStore(path);state.create_admin('admin','fixture-password-123');uid=state.admin_id()
            registry=UserServices(state,ModelService(environ={},store=state))
            registry.configure_public(uid,{'provider':'general','base_url':'http://127.0.0.1:1234/v1','model':'shared','auth':'none'})
            state.set_model_policy(uid,{'enabled':{'general':True,'domain':False},'default_provider':'general','daily_limit':5})
            state.consume_public_call(uid);registry.close();state.close()
            state=StateStore(path);registry=UserServices(state,ModelService(environ={},store=state))
            try:
                self.assertEqual(registry.for_user({'user_id':uid})['models'].get_config('general')['model'],'shared')
                self.assertEqual(state.public_usage(uid)['used'],1)
                self.assertEqual(state.public_usage(uid)['limit'],5)
                self.assertIn('public_model.configure',[l['action'] for l in state.admin_logs(uid)])
            finally:registry.close();state.close()

    def test_shanghai_quota_day_changes_at_utc_1600(self):
        with patch('session_store.time.time',return_value=1790783999):self.assertEqual(self.state.usage_day(),'2026-09-30')
        with patch('session_store.time.time',return_value=1790784000):self.assertEqual(self.state.usage_day(),'2026-10-01')

    def test_version_two_invitation_records_migrate_without_losing_usage(self):
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/'old.sqlite3';db=sqlite3.connect(path)
            db.executescript('CREATE TABLE invites(id TEXT PRIMARY KEY,digest TEXT UNIQUE,created_by TEXT,created_at REAL,expires_at REAL,revoked INTEGER DEFAULT 0,used_by TEXT,used_at REAL,max_uses INTEGER NOT NULL DEFAULT 10,used_count INTEGER NOT NULL DEFAULT 0);PRAGMA user_version=2;')
            db.execute('INSERT INTO invites VALUES(?,?,?,?,?,?,?,?,?,?)',('old','hash','admin',100,200,1,'user',150,10,7));db.commit();db.close()
            state=StateStore(path)
            try:self.assertEqual(state.db.execute('SELECT created_at,expires_at,revoked,max_uses,used_count,updated_at FROM invites').fetchone(),(100,200,1,10,7,100))
            finally:state.close()


if __name__ == '__main__':unittest.main()
