"""Private, single-owner SQLite state. Never expose this directory as static content."""
import hashlib
import hmac
import json
import pathlib
import re
import secrets
import sqlite3
import threading
import time

COOKIE_NAME='aeroblade_session'
SESSION_SECONDS=12*60*60


class AuthError(Exception):
    def __init__(self,message,status=401):
        super().__init__(message);self.status=status


class StateStore:
    def __init__(self,path=None):
        if path is not None:
            path=pathlib.Path(path)
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(str(path) if path else ':memory:',check_same_thread=False,timeout=10)
        if path:path.chmod(0o600)
        self.lock=threading.RLock()
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY CHECK(id=1),username TEXT UNIQUE,salt BLOB,digest BLOB);
          CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY,username TEXT,csrf TEXT,expires REAL);
          CREATE TABLE IF NOT EXISTS failures (bucket TEXT PRIMARY KEY,count INTEGER,since REAL);
          CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY,value TEXT);
        ''')
        self.db.commit()

    @staticmethod
    def password_digest(password,salt):
        return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,600000)

    def initialized(self):
        with self.lock:return self.db.execute('SELECT 1 FROM admin').fetchone() is not None

    def create_admin(self,username,password):
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username):
            raise AuthError('用户名须为3–64位字母、数字、点、下划线或短横线',400)
        if not isinstance(password,str) or not 12<=len(password)<=1024:
            raise AuthError('登录密码须为12–1024个字符',400)
        salt=secrets.token_bytes(16);digest=self.password_digest(password,salt)
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.initialized():raise AuthError('管理员已创建，请直接登录',409)
            self.db.execute('INSERT INTO admin VALUES(1,?,?,?)',(username,salt,digest))

    def login(self,username,password,address):
        if not isinstance(username,str) or not isinstance(password,str) or len(username)>64 or len(password)>1024:
            raise AuthError('用户名或密码错误')
        now=time.time();bucket=hashlib.sha256(str(address).encode()).hexdigest()
        with self.lock,self.db:
            self.db.execute('DELETE FROM failures WHERE since < ?',(now-900,))
            row=self.db.execute('SELECT count FROM failures WHERE bucket=?',(bucket,)).fetchone()
            if row and row[0]>=10:raise AuthError('登录尝试过多，请15分钟后再试',429)
            admin=self.db.execute('SELECT username,salt,digest FROM admin').fetchone()
            actual=self.password_digest(password,admin[1] if admin else b'no-user-placeholder')
            valid=admin is not None and hmac.compare_digest(username.encode(),admin[0].encode()) and hmac.compare_digest(actual,admin[2])
            if not valid:
                self.db.execute('INSERT INTO failures VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(bucket,now))
                self.db.commit() # Preserve the counter before raising out of the transaction.
                raise AuthError('用户名或密码错误')
            self.db.execute('DELETE FROM failures WHERE bucket=?',(bucket,))
            self.db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);expires=now+SESSION_SECONDS
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),username,csrf,expires))
            return token,{'username':username,'csrf':csrf,'expires':expires}

    def session(self,token):
        if not isinstance(token,str) or not token or len(token)>128:return None
        with self.lock:
            row=self.db.execute('SELECT username,csrf,expires FROM sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not row or row[2]<=time.time():return None
            return dict(zip(('username','csrf','expires'),row))

    def logout(self,token):
        with self.lock,self.db:self.db.execute('DELETE FROM sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def load_models(self):
        with self.lock:row=self.db.execute("SELECT value FROM settings WHERE name='models'").fetchone()
        if row is None:return None
        try:return json.loads(row[0])
        except ValueError:raise ValueError('模型配置数据库内容无效，请恢复备份') from None

    def save_models(self,configs):
        value=json.dumps(configs,ensure_ascii=False,allow_nan=False)
        with self.lock,self.db:self.db.execute("INSERT INTO settings VALUES('models',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(value,))

    def close(self):
        with self.lock:self.db.close()
