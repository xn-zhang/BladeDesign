import pathlib,sys,tempfile,unittest,sqlite3,hashlib,concurrent.futures,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from session_store import StateStore,AuthError

class MultiUserStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=pathlib.Path(self.tmp.name)/'state.sqlite3'
        self.s=StateStore(self.path); self.s.create_admin('admin','test-password-123'); self.admin=self.s.admin_id()
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def register(self,name='alice'):
        return self.s.register(name,'user-password-123',self.s.create_invite(self.admin)['code'],'test')
    def test_invite_is_private_and_limited_to_ten_uses(self):
        inv=self.s.create_invite(self.admin);u=self.s.register('Alice','user-password-123',inv['code'],'test')
        self.assertEqual(u['role'],'user');self.assertNotIn(inv['code'],json.dumps(self.s.list_invites(self.admin)))
        self.assertEqual(inv['max_uses'],10);self.assertEqual(inv['used_count'],0)
        self.assertAlmostEqual(inv['expires_at']-__import__('time').time(),604800,delta=5)
        for i in range(9):self.s.register('tester'+str(i),'user-password-123',inv['code'],'test')
        with self.assertRaises(AuthError):self.s.register('eleventh','user-password-123',inv['code'],'test')
        row=self.s.list_invites(self.admin)[0];self.assertEqual(row['used_count'],10)
        self.assertEqual(self.s.login('ALICE','user-password-123','test')[1]['user_id'],u['id'])
    def test_disabled_password_and_model_isolation(self):
        a=self.register();b=self.register('bob');key,session=self.s.login('alice','user-password-123','test')
        self.s.model_store(a['id']).save_models({'general':{'api_key':'only-alice'}})
        self.assertIsNone(self.s.model_store(b['id']).load_models())
        self.s.set_disabled(self.admin,a['id'],True);self.assertIsNone(self.s.session(key))
        with self.assertRaises(AuthError):self.s.create_invite(b['id'])
        self.s.set_disabled(self.admin,a['id'],False)
        key,_=self.s.login('alice','user-password-123','test')
        self.s.change_password(a['id'],'user-password-123','new-password-123');self.assertIsNone(self.s.session(key))
    def test_duplicate_rolls_back_invite_and_revocation(self):
        self.register();inv=self.s.create_invite(self.admin)
        with self.assertRaises(AuthError):self.s.register('ALICE','user-password-123',inv['code'],'test')
        self.s.register('bob','user-password-123',inv['code'],'test')
        row=next(i for i in self.s.list_invites(self.admin) if i['id']==inv['id']);self.assertEqual(row['used_count'],1)
        self.s.revoke_invite(self.admin,inv['id'])
        with self.assertRaises(AuthError):self.s.register('revoked','user-password-123',inv['code'],'test')
        inv=self.s.create_invite(self.admin);self.s.revoke_invite(self.admin,inv['id'])
        with self.assertRaises(AuthError):self.s.register('carol','user-password-123',inv['code'],'test')
    def test_concurrent_consumption(self):
        inv=self.s.create_invite(self.admin)
        for i in range(9):self.s.register('prefill'+str(i),'user-password-123',inv['code'],'test')
        def attempt(name):
            other=StateStore(self.path)
            try:other.register(name,'user-password-123',inv['code'],'test');return True
            except AuthError:return False
            finally:other.close()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(attempt,['alice','bob'])),1)
    def test_expired_invite(self):
        inv=self.s.create_invite(self.admin);self.s.db.execute('UPDATE invites SET expires_at=0');self.s.db.commit()
        with self.assertRaises(AuthError):self.s.register('alice','user-password-123',inv['code'],'test')

class MigrationTests(unittest.TestCase):
    def test_existing_database_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'old.sqlite3';db=sqlite3.connect(path);salt=b'old-salt'
            db.executescript('CREATE TABLE admin(id INTEGER PRIMARY KEY,username TEXT,salt BLOB,digest BLOB);CREATE TABLE sessions(digest TEXT PRIMARY KEY,username TEXT,csrf TEXT,expires REAL);CREATE TABLE settings(name TEXT PRIMARY KEY,value TEXT);CREATE TABLE failures(bucket TEXT PRIMARY KEY,count INTEGER,since REAL);')
            db.execute('INSERT INTO admin VALUES(1,?,?,?)',('admin',salt,StateStore.password_digest('old-password-123',salt)))
            db.execute('INSERT INTO settings VALUES(?,?)',('models','{"general":{"api_key":"old-private"}}'))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(b'old-token').hexdigest(),'admin','old-csrf',9999999999));db.commit();db.close()
            for _ in range(2):
                s=StateStore(path);self.assertIsNone(s.session('old-token'));self.assertEqual(s.login('admin','old-password-123','test')[1]['role'],'admin')
                self.assertEqual(s.model_store(s.admin_id()).load_models()['general']['api_key'],'old-private');self.assertEqual(len(s.list_users(s.admin_id())),1);s.close()
class InviteMigrationTests(unittest.TestCase):
    def test_v1_preserves_usage_expiry_and_revoke_without_resetting_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'v1.sqlite3';s=StateStore(path)
            s.create_admin('admin','fixture-password-123');token,_=s.login('admin','fixture-password-123','test');s.close()
            db=sqlite3.connect(path)
            db.execute('DROP TABLE invites')
            db.execute('CREATE TABLE invites(id TEXT PRIMARY KEY,digest TEXT UNIQUE,created_by TEXT,created_at REAL,expires_at REAL,revoked INTEGER DEFAULT 0,used_by TEXT,used_at REAL)')
            db.execute('INSERT INTO invites VALUES(?,?,?,?,?,?,?,?)',('old','digest','admin',100,604900,1,'existing-user',200))
            db.execute('PRAGMA user_version=1');db.commit();db.close()
            for _ in range(2):
                s=StateStore(path)
                try:
                    row=s.list_invites(s.admin_id())[0]
                    self.assertEqual(row['max_uses'],10);self.assertEqual(row['used_count'],1)
                    self.assertEqual(row['expires_at'],604900);self.assertEqual(row['revoked'],1)
                    self.assertIsNotNone(s.session(token))
                finally:s.close()
if __name__=='__main__':unittest.main()
