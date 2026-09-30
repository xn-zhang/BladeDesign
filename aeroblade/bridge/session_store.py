"""Private multi-user SQLite identity, invitations and model settings."""
import hashlib,hmac,json,pathlib,re,secrets,sqlite3,threading,time
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
COOKIE_NAME='aeroblade_session'
SESSION_SECONDS=12*60*60
class AuthError(Exception):
    def __init__(self,message,status=401):super().__init__(message);self.status=status

class StateStore:
    def __init__(self,path=None):
        self.path=pathlib.Path(path) if path is not None else None
        if self.path:self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(str(path) if path else ':memory:',check_same_thread=False,timeout=15)
        if self.path:self.path.chmod(0o600)
        self.lock=threading.RLock()
        with self.transaction():
            version=self.db.execute('PRAGMA user_version').fetchone()[0]
            if version>3:raise ValueError('Database version is newer than this application')
            self.db.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL,digest BLOB NOT NULL,role TEXT NOT NULL,disabled INTEGER NOT NULL DEFAULT 0,created_at REAL NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,value TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS failures(bucket TEXT PRIMARY KEY,count INTEGER,since REAL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS user_settings(user_id TEXT,name TEXT,value TEXT,PRIMARY KEY(user_id,name))')
            self.db.execute('CREATE TABLE IF NOT EXISTS invites(id TEXT PRIMARY KEY,digest TEXT UNIQUE,created_by TEXT,created_at REAL,expires_at REAL,revoked INTEGER DEFAULT 0,used_by TEXT,used_at REAL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS personal_items(id TEXT PRIMARY KEY,user_id TEXT,kind TEXT,name TEXT,payload TEXT,created_at REAL,updated_at REAL)')
            self.db.execute('CREATE INDEX IF NOT EXISTS personal_owner ON personal_items(user_id,kind)')
            if version==0:
                exists=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin'").fetchone()
                if exists:
                    old=self.db.execute('SELECT username,salt,digest FROM admin WHERE id=1').fetchone()
                    if old:
                        uid=secrets.token_hex(16)
                        self.db.execute('INSERT INTO users VALUES(?,?,?,?,?,0,?)',(uid,old[0].strip().casefold(),old[1],old[2],'admin',time.time()))
                        self.db.execute("INSERT INTO user_settings SELECT ?,name,value FROM settings WHERE name='models'",(uid,))
                    self.db.execute('DROP TABLE admin')
                self.db.execute('DROP TABLE IF EXISTS sessions')
                self.db.execute('PRAGMA user_version=1')
            self.db.execute('CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,user_id TEXT,csrf TEXT,expires REAL)')
            if version<2:
                self.db.execute('ALTER TABLE invites ADD COLUMN max_uses INTEGER NOT NULL DEFAULT 10')
                self.db.execute('ALTER TABLE invites ADD COLUMN used_count INTEGER NOT NULL DEFAULT 0')
                self.db.execute('UPDATE invites SET used_count=CASE WHEN used_by IS NULL THEN 0 ELSE 1 END')
                self.db.execute('PRAGMA user_version=2')
            if version<3:
                self.db.execute('ALTER TABLE invites ADD COLUMN updated_at REAL')
                self.db.execute('UPDATE invites SET updated_at=created_at')
                self.db.execute('PRAGMA user_version=3')
            self.db.execute('CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,action TEXT,target TEXT,detail TEXT,created_at REAL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS public_usage(user_id TEXT,day TEXT,used INTEGER,PRIMARY KEY(user_id,day))')
    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:yield;self.db.commit()
            except Exception:self.db.rollback();raise
    @staticmethod
    def password_digest(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,600000)
    @staticmethod
    def credentials(username,password):
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username.strip()):raise AuthError('用户名须为3–64位字母、数字、点、下划线',400)
        if not isinstance(password,str) or not 12<=len(password)<=1024:raise AuthError('密码须为12–1024个字符',400)
        return username.strip().casefold()
    def admin_id(self):
        with self.lock:row=self.db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        return row[0] if row else None
    def initialized(self):return self.admin_id() is not None
    def user(self,uid):
        with self.lock:row=self.db.execute('SELECT id,username,role,disabled,created_at FROM users WHERE id=?',(uid,)).fetchone()
        if not row:raise AuthError('账号不存在',404)
        return dict(zip(('id','username','role','disabled','created_at'),row))
    def require_user(self,uid,admin=False):
        u=self.user(uid)
        if u['disabled']:raise AuthError('账号已禁用',403)
        if admin and u['role']!='admin':raise AuthError('需要管理员权限',403)
        return u
    def create_admin(self,username,password):
        username=self.credentials(username,password);salt=secrets.token_bytes(16);digest=self.password_digest(password,salt)
        with self.transaction():
            if self.initialized():raise AuthError('管理员已创建，请直接登录',409)
            uid=secrets.token_hex(16)
            self.db.execute('INSERT INTO users VALUES(?,?,?,?,?,0,?)',(uid,username,salt,digest,'admin',time.time()))
            self.db.execute('INSERT INTO user_settings SELECT ?,name,value FROM settings',(uid,))
    def throttle(self,bucket,limit=20,window=900):
        now=time.time();key=hashlib.sha256(bucket.encode()).hexdigest()
        with self.transaction():
            self.db.execute('DELETE FROM failures WHERE since < ?',(now-window,))
            row=self.db.execute('SELECT count FROM failures WHERE bucket=?',(key,)).fetchone()
            if row and row[0]>=limit:raise AuthError('请求过于频繁，请稍后重试',429)
            self.db.execute('INSERT INTO failures VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(key,now))
    def create_invite(self,admin_id,expires_in=604800,max_uses=10):
        if type(expires_in) is not int or not 60<=expires_in<=7776000:raise AuthError('邀请码有效期须为1分钟至90天',400)
        if type(max_uses) is not int or not 1<=max_uses<=1000:raise AuthError('使用次数须为1–1000',400)
        with self.transaction():
            self.require_user(admin_id,True)
            now=time.time();iid=secrets.token_hex(16)
            for _ in range(5):
                code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
                if not self.db.execute('SELECT 1 FROM invites WHERE digest=?',(hashlib.sha256(code.encode()).hexdigest(),)).fetchone():break
            else:raise AuthError('邀请码生成繁忙，请重试',503)
            self.db.execute('INSERT INTO invites(id,digest,created_by,created_at,expires_at,max_uses,updated_at) VALUES(?,?,?,?,?,?,?)',(iid,hashlib.sha256(code.encode()).hexdigest(),admin_id,now,now+expires_in,max_uses,now))
            self.log_admin(admin_id,'invite.create',iid,{'expires_at':now+expires_in,'max_uses':max_uses})
        return {'id':iid,'code':code,'expires_at':now+expires_in,'max_uses':max_uses,'used_count':0}
    def list_invites(self,admin_id):
        with self.lock:
            self.require_user(admin_id,True)
            rows=self.db.execute('SELECT id,created_at,expires_at,revoked,used_by,max_uses,used_count,updated_at FROM invites ORDER BY created_at DESC LIMIT 200').fetchall()
        return [dict(zip(('id','created_at','expires_at','revoked','used_by','max_uses','used_count','updated_at'),r)) for r in rows]
    def revoke_invite(self,admin_id,iid):
        with self.transaction():
            self.require_user(admin_id,True)
            if self.db.execute('UPDATE invites SET revoked=1,updated_at=? WHERE id=?',(time.time(),iid)).rowcount!=1:raise AuthError('邀请码不存在',404)
            self.log_admin(admin_id,'invite.revoke',iid,{})
    def update_invite(self,admin_id,iid,expires_at,max_uses):
        if type(expires_at) not in (int,float) or not time.time()<expires_at<=time.time()+7776000:raise AuthError('到期时间须在未来90天内',400)
        if type(max_uses) is not int or not 1<=max_uses<=1000:raise AuthError('使用次数须为1–1000',400)
        with self.transaction():
            self.require_user(admin_id,True)
            row=self.db.execute('SELECT revoked,used_count FROM invites WHERE id=?',(iid,)).fetchone()
            if not row:raise AuthError('邀请码不存在',404)
            if row[0]:raise AuthError('已撤销的邀请码不能修改',400)
            if max_uses<row[1]:raise AuthError('使用上限不能低于已使用次数',400)
            self.db.execute('UPDATE invites SET expires_at=?,max_uses=?,updated_at=? WHERE id=?',(expires_at,max_uses,time.time(),iid))
            self.log_admin(admin_id,'invite.update',iid,{'expires_at':expires_at,'max_uses':max_uses})
    def register(self,username,password,invite,address):
        self.throttle('register-global',200);self.throttle('register:'+str(address),30)
        username=self.credentials(username,password)
        if not isinstance(invite,str):raise AuthError('邀请码格式无效',400)
        invite=invite.strip()
        if len(invite)==8:
            invite=invite.upper()
            if not re.fullmatch('[A-HJ-NP-Z2-9]{8}',invite):raise AuthError('邀请码格式无效',400)
        elif not 20<=len(invite)<=100:raise AuthError('邀请码格式无效',400)
        digest=hashlib.sha256(invite.encode()).hexdigest()
        with self.lock:
            if not self.db.execute('SELECT 1 FROM invites WHERE digest=? AND revoked=0 AND used_count<max_uses AND expires_at>?',(digest,time.time())).fetchone():raise AuthError('邀请码无效、已过期或使用次数已满',400)
        salt=secrets.token_bytes(16);hashed=self.password_digest(password,salt);uid=secrets.token_hex(16)
        try:
            with self.transaction():
                if not self.initialized():raise AuthError('管理员尚未初始化',403)
                used=self.db.execute('UPDATE invites SET used_by=?,used_at=?,used_count=used_count+1 WHERE digest=? AND used_count<max_uses AND revoked=0 AND expires_at>?',(uid,time.time(),digest,time.time()))
                if used.rowcount!=1:raise AuthError('邀请码无效、已过期或使用次数已满',400)
                self.db.execute('INSERT INTO users VALUES(?,?,?,?,?,0,?)',(uid,username,salt,hashed,'user',time.time()))
        except sqlite3.IntegrityError:raise AuthError('用户名已存在',409) from None
        return self.user(uid)
    def login(self,username,password,address):
        if not isinstance(username,str) or not isinstance(password,str) or len(username)>64 or len(password)>1024:raise AuthError('用户名或密码错误')
        username=username.strip().casefold()
        self.throttle('login-global',500)
        bucket=hashlib.sha256(('login:'+username+':'+str(address)).encode()).hexdigest();now=time.time()
        with self.lock:
            self.db.execute('DELETE FROM failures WHERE since < ?',(now-900,));self.db.commit()
            row=self.db.execute('SELECT count FROM failures WHERE bucket=?',(bucket,)).fetchone()
            if row and row[0]>=10:raise AuthError('登录尝试过多，请15分钟后再试',429)
            u=self.db.execute('SELECT id,salt,digest,disabled FROM users WHERE username=?',(username,)).fetchone()
            actual=self.password_digest(password,u[1] if u else b'no-user-placeholder')
            valid=u is not None and not u[3] and hmac.compare_digest(actual,u[2])
            if not valid:
                self.db.execute('INSERT INTO failures VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(bucket,now));self.db.commit();raise AuthError('用户名或密码错误')
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            self.db.execute('DELETE FROM failures WHERE bucket=?',(bucket,));self.db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u[0],csrf,now+SESSION_SECONDS));self.db.commit()
            return token,self.session(token)
    def session(self,token):
        if not isinstance(token,str) or not token or len(token)>128:return None
        with self.lock:
            row=self.db.execute('SELECT u.id,u.username,u.role,s.csrf,s.expires FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.digest=? AND u.disabled=0 AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(zip(('user_id','username','role','csrf','expires'),row)) if row else None
    def logout(self,token):
        with self.transaction():self.db.execute('DELETE FROM sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def list_users(self,admin_id):
        with self.lock:
            self.require_user(admin_id,True);ids=self.db.execute('SELECT id FROM users ORDER BY created_at').fetchall()
            return [self.user(r[0]) for r in ids]
    def set_disabled(self,admin_id,uid,disabled):
        if type(disabled) is not bool:raise AuthError('状态无效',400)
        with self.transaction():
            self.require_user(admin_id,True);u=self.user(uid)
            if u['role']=='admin':raise AuthError('不能禁用管理员',403)
            self.db.execute('UPDATE users SET disabled=? WHERE id=?',(int(disabled),uid))
            if disabled:self.db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            self.log_admin(admin_id,'user.disable' if disabled else 'user.enable',uid,{})
    def force_logout(self,admin_id,uid):
        with self.transaction():
            self.require_user(admin_id,True);user=self.user(uid)
            if user['role']=='admin':raise AuthError('管理员请通过账号菜单退出登录',403)
            self.db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            self.log_admin(admin_id,'user.logout',uid,{})
    def log_admin(self,actor,action,target,detail):
        # Call inside the same transaction as the change; details are explicit safe fields.
        self.db.execute('INSERT INTO admin_logs(actor,action,target,detail,created_at) VALUES(?,?,?,?,?)',(actor,action,target,json.dumps(detail,ensure_ascii=False,allow_nan=False),time.time()))
    def admin_logs(self,admin_id):
        with self.lock:
            self.require_user(admin_id,True)
            rows=self.db.execute('SELECT l.id,u.username,l.action,l.target,l.detail,l.created_at FROM admin_logs l LEFT JOIN users u ON u.id=l.actor ORDER BY l.id DESC LIMIT 200').fetchall()
            return [dict(id=r[0],actor=r[1],action=r[2],target=r[3],detail=json.loads(r[4]),created_at=r[5]) for r in rows]
    def model_policy(self):
        with self.lock:row=self.db.execute("SELECT value FROM settings WHERE name='public_model_policy'").fetchone()
        return json.loads(row[0]) if row else {'enabled':{'general':False,'domain':False},'default_provider':'general','daily_limit':50}
    def set_model_policy(self,admin_id,data):
        if not isinstance(data,dict) or set(data)!={'enabled','default_provider','daily_limit'}:raise AuthError('模型策略字段无效',400)
        enabled=data['enabled']
        if not isinstance(enabled,dict) or set(enabled)!={'general','domain'} or any(type(v) is not bool for v in enabled.values()):raise AuthError('启用状态无效',400)
        if data['default_provider'] not in ('general','domain'):raise AuthError('默认模型无效',400)
        if type(data['daily_limit']) is not int or not 1<=data['daily_limit']<=10000:raise AuthError('每日限额须为1–10000次',400)
        with self.transaction():
            self.require_user(admin_id,True)
            self.db.execute("INSERT INTO settings VALUES('public_model_policy',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(json.dumps(data),))
            self.log_admin(admin_id,'public_model.policy','platform',data)
        return data
    @staticmethod
    def usage_day():return datetime.fromtimestamp(time.time(),timezone(timedelta(hours=8))).date().isoformat()
    def public_usage(self,uid):
        with self.lock:
            self.require_user(uid)
            day=self.usage_day()
            row=self.db.execute('SELECT used FROM public_usage WHERE user_id=? AND day=?',(uid,day)).fetchone()
            return {'day':day,'used':row[0] if row else 0,'limit':self.model_policy()['daily_limit']}
    def consume_public_call(self,uid,provider=None):
        with self.transaction():
            self.require_user(uid);policy=self.model_policy()
            if provider and not policy['enabled'].get(provider):raise AuthError('此公共模型已停用',503)
            day=self.usage_day()
            row=self.db.execute('SELECT used FROM public_usage WHERE user_id=? AND day=?',(uid,day)).fetchone()
            if row and row[0]>=policy['daily_limit']:raise AuthError('今日公共模型调用次数已达上限，请明日再试或使用个人模型',429)
            self.db.execute('INSERT INTO public_usage VALUES(?,?,1) ON CONFLICT(user_id,day) DO UPDATE SET used=used+1',(uid,day))
            self.db.execute('DELETE FROM public_usage WHERE day<?',((datetime.fromtimestamp(time.time(),timezone(timedelta(hours=8)))-timedelta(days=90)).date().isoformat(),))
    def change_password(self,uid,current_password,new_password):
        self.throttle('password:'+uid,10)
        self.credentials('valid-name',new_password)
        if not isinstance(current_password,str) or len(current_password)>1024:raise AuthError('当前密码错误',400)
        with self.transaction():
            self.require_user(uid)
            salt,digest=self.db.execute('SELECT salt,digest FROM users WHERE id=?',(uid,)).fetchone()
            if not hmac.compare_digest(digest,self.password_digest(current_password,salt)):raise AuthError('当前密码错误',400)
            salt=secrets.token_bytes(16)
            self.db.execute('UPDATE users SET salt=?,digest=? WHERE id=?',(salt,self.password_digest(new_password,salt),uid));self.db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    def model_store(self,uid):return UserModelStore(self,uid)
    def load_models(self):
        uid=self.admin_id()
        if uid:return self.model_store(uid).load_models()
        with self.lock:row=self.db.execute("SELECT value FROM settings WHERE name='models'").fetchone()
        return json.loads(row[0]) if row else None
    def save_models(self,configs):
        uid=self.admin_id()
        if uid:return self.model_store(uid).save_models(configs)
        with self.transaction():self.db.execute("INSERT INTO settings VALUES('models',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(json.dumps(configs),))
    def close(self):
        with self.lock:self.db.close()

class UserModelStore:
    def __init__(self,state,uid):self.state=state;self.uid=uid
    def load_models(self):
        with self.state.lock:
            self.state.require_user(self.uid)
            row=self.state.db.execute("SELECT value FROM user_settings WHERE user_id=? AND name='models'",(self.uid,)).fetchone()
        return json.loads(row[0]) if row else None
    def save_models(self,configs):
        with self.state.transaction():
            self.state.require_user(self.uid)
            self.state.db.execute("INSERT INTO user_settings VALUES(?,'models',?) ON CONFLICT(user_id,name) DO UPDATE SET value=excluded.value",(self.uid,json.dumps(configs,ensure_ascii=False,allow_nan=False)))
