"""Owned personal snapshots; no client-selected filesystem paths."""
import json,time,secrets,pathlib,subprocess,threading
from batch_contract import validate_conditions
GEOMETRY_SLOTS=threading.BoundedSemaphore(2)
def text(value,limit):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError('名称或文本长度无效')
    return value.strip()
def geometry(parameters):
    if not isinstance(parameters,dict):raise ValueError('缺少几何参数')
    url=(pathlib.Path(__file__).resolve().parents[1]/'web/geometry.js').as_uri()
    script="import {validate,build} from "+json.dumps(url)+";let s='';for await(const c of process.stdin)s+=c;const p=JSON.parse(s);validate(p);build(p);"
    if not GEOMETRY_SLOTS.acquire(blocking=False):raise ValueError('几何校验繁忙，请重试')
    try:
        r=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(parameters,allow_nan=False),capture_output=True,text=True,timeout=10)
        if r.returncode:raise ValueError('几何参数无效或无法构成有效叶型')
    except FileNotFoundError:raise ValueError('服务器缺少 Node.js 几何校验环境') from None
    finally:GEOMETRY_SLOTS.release()
def validate_payload(kind,payload):
    if not isinstance(payload,dict):raise ValueError('数据格式无效')
    raw=json.dumps(payload,ensure_ascii=False,allow_nan=False)
    if len(raw.encode())>1048576:raise ValueError('每份数据最多1 MiB')
    def no_secrets(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k.lower() in ('api_key','apikey','password','token','authorization'):raise ValueError('个人数据不能包含密钥字段')
                no_secrets(v)
        elif isinstance(value,list):
            for v in value:no_secrets(v)
    no_secrets(payload)
    if kind=='designs':
        if set(payload)!={'schema','parameters','conditions','notes'} or payload['schema']!='aeroblade-saved-design-v1':raise ValueError('设计格式无效')
        if not isinstance(payload['notes'],str) or len(payload['notes'])>4000:raise ValueError('备注最多4000字符')
        validate_conditions([payload['conditions']]);geometry(payload['parameters'])
    elif kind=='conversations':
        if set(payload)!={'schema','messages','provider','candidate','draft'} or payload['schema']!='aeroblade-saved-conversation-v1':raise ValueError('对话格式无效')
        if payload['provider'] not in ('demo','general','domain') or not isinstance(payload['draft'],str) or len(payload['draft'])>6000:raise ValueError('对话配置无效')
        messages=payload['messages']
        if not isinstance(messages,list) or len(messages)>60:raise ValueError('最多60条消息')
        for m in messages:
            if not isinstance(m,dict) or set(m)!={'role','content'} or m['role'] not in ('user','assistant'):raise ValueError('消息格式无效')
            text(m['content'],12000)
        if payload['candidate'] is not None:
            from design_assistant import normalize_reply
            normalize_reply(json.dumps({'schema':'aeroblade-assistant-reply-v1','message':'saved','proposal':payload['candidate']}))
            geometry(payload['candidate']['parameters'])
    else:raise ValueError('未知数据类型')
    return raw
class PersonalStore:
    def __init__(self,state):self.state=state
    def kind(self,kind):
        if kind not in ('designs','conversations'):raise ValueError('未知数据类型')
    def list(self,uid,kind):
        self.kind(kind)
        with self.state.lock:
            self.state.require_user(uid)
            rows=self.state.db.execute('SELECT id,name,created_at,updated_at FROM personal_items WHERE user_id=? AND kind=? ORDER BY updated_at DESC',(uid,kind)).fetchall()
        return [dict(zip(('id','name','created_at','updated_at'),r)) for r in rows]
    def get(self,uid,kind,iid):
        self.kind(kind)
        with self.state.lock:
            self.state.require_user(uid)
            row=self.state.db.execute('SELECT id,name,payload,created_at,updated_at FROM personal_items WHERE user_id=? AND kind=? AND id=?',(uid,kind,iid)).fetchone()
        if not row:raise KeyError(iid)
        result=dict(zip(('id','name','payload','created_at','updated_at'),row));result['payload']=json.loads(result['payload']);return result
    def save(self,uid,kind,name,payload,item_id=None):
        self.state.require_user(uid);name=text(name,120);raw=validate_payload(kind,payload);now=time.time();iid=item_id or secrets.token_hex(16)
        with self.state.transaction():
            self.state.require_user(uid)
            if item_id:
                if self.state.db.execute('UPDATE personal_items SET name=?,payload=?,updated_at=? WHERE user_id=? AND kind=? AND id=?',(name,raw,now,uid,kind,iid)).rowcount!=1:raise KeyError(iid)
            else:
                count=self.state.db.execute('SELECT COUNT(*) FROM personal_items WHERE user_id=? AND kind=?',(uid,kind)).fetchone()[0]
                if count>=(100 if kind=='designs' else 50):raise ValueError('个人保存数量已达上限，请先删除旧记录')
                self.state.db.execute('INSERT INTO personal_items VALUES(?,?,?,?,?,?,?)',(iid,uid,kind,name,raw,now,now))
        return self.get(uid,kind,iid)
    def rename(self,uid,kind,iid,name):
        self.kind(kind);name=text(name,120)
        with self.state.transaction():
            self.state.require_user(uid)
            if self.state.db.execute('UPDATE personal_items SET name=?,updated_at=? WHERE user_id=? AND kind=? AND id=?',(name,time.time(),uid,kind,iid)).rowcount!=1:raise KeyError(iid)
    def delete(self,uid,kind,iid):
        self.kind(kind)
        with self.state.transaction():
            self.state.require_user(uid)
            if self.state.db.execute('DELETE FROM personal_items WHERE user_id=? AND kind=? AND id=?',(uid,kind,iid)).rowcount!=1:raise KeyError(iid)
