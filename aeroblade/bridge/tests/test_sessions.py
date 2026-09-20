import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from session_store import StateStore, AuthError
from design_assistant import ModelService


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.temp.name)/'private'/'state.sqlite3'
        self.store=StateStore(self.path)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def test_setup_login_restart_and_logout(self):
        self.store.create_admin('admin','fixture-password-123')
        token,session=self.store.login('admin','fixture-password-123','local')
        self.assertEqual(self.store.session(token)['username'],'admin')
        self.assertNotIn(b'fixture-password-123',self.path.read_bytes())
        self.store.close();self.store=StateStore(self.path)
        self.assertEqual(self.store.session(token)['csrf'],session['csrf'])
        self.store.logout(token);self.assertIsNone(self.store.session(token))
    def test_no_second_admin_and_wrong_password(self):
        self.store.create_admin('admin','fixture-password-123')
        with self.assertRaises(AuthError):self.store.create_admin('other','fixture-password-456')
        with self.assertRaises(AuthError):self.store.login('admin','wrong-password','local')
    def test_login_rate_limit(self):
        self.store.create_admin('admin','fixture-password-123')
        for _ in range(10):
            with self.assertRaises(AuthError):self.store.login('admin','wrong-password','local')
        with self.assertRaises(AuthError) as ctx:self.store.login('admin','fixture-password-123','local')
        self.assertEqual(ctx.exception.status,429)
    def test_expired_session(self):
        self.store.create_admin('admin','fixture-password-123')
        token,_=self.store.login('admin','fixture-password-123','local')
        self.store.db.execute('UPDATE sessions SET expires=0');self.store.db.commit()
        self.assertIsNone(self.store.session(token))
    def test_model_config_persisted_and_clear_survives_restart(self):
        model=ModelService(environ={},store=self.store)
        model.configure({'provider':'general','base_url':'https://model.example/v1','model':'fixture','api_key':'private-fixture-key'})
        restored=ModelService(environ={},store=self.store)
        self.assertTrue(restored.describe()['providers']['general']['has_key'])
        self.assertNotIn('private-fixture-key',json.dumps(restored.describe()))
        restored.clear('general')
        self.assertFalse(ModelService(environ={},store=self.store).describe()['providers']['general']['configured'])
    def test_saved_state_takes_priority_over_stale_environment(self):
        self.store.save_models({})
        restored=ModelService(environ={'AEROBLADE_LLM_GENERAL_BASE_URL':'stale-invalid-url'},store=self.store)
        self.assertFalse(restored.describe()['providers']['general']['configured'])

if __name__=='__main__':unittest.main()
