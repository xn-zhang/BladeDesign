"""Owned account and personal-resource HTTP routes."""
import re
from personal_store import PersonalStore

def fields(data,required,optional=()):
    if not isinstance(data,dict) or set(data)-set(required)-set(optional) or set(required)-set(data):raise ValueError('请求字段无效')
    return data

def dispatch(h,path,principal,state,services):
    uid=principal['user_id']
    if path=='/api/session/password' and h.command=='POST':
        data=fields(h.body(),('current_password','new_password'))
        state.change_password(uid,data['current_password'],data['new_password']);h.cookie('',clear=True);h.send_json({'ok':True});return True
    if path.startswith('/api/admin/'):
        state.require_user(uid,True)
        if path=='/api/admin/invites':
            if h.command=='GET':h.send_json({'invites':state.list_invites(uid)});return True
            if h.command=='POST':fields(h.body(),());state.throttle('invite:'+uid,100);h.send_json(state.create_invite(uid));return True
        if path=='/api/admin/users' and h.command=='GET':h.send_json({'users':state.list_users(uid)});return True
        match=re.fullmatch(r'/api/admin/(invites|users)/([a-f0-9]{32})/(revoke|status)',path)
        if match and h.command=='POST':
            kind,iid,action=match.groups();data=h.body()
            if kind=='invites' and action=='revoke':fields(data,());state.revoke_invite(uid,iid)
            elif kind=='users' and action=='status':
                fields(data,('disabled',));state.set_disabled(uid,iid,data['disabled'])
                if data['disabled']:services.disable(iid)
            else:raise KeyError(path)
            h.send_json({'ok':True});return True
        raise KeyError(path)
    if path.startswith('/api/personal/'):
        match=re.fullmatch(r'/api/personal/(designs|conversations)(?:/([a-f0-9]{32})(?:/(rename|delete))?)?',path)
        if not match:raise KeyError(path)
        kind,iid,action=match.groups();store=PersonalStore(state)
        if h.command=='GET' and not action:
            h.send_json(store.get(uid,kind,iid) if iid else {'items':store.list(uid,kind)});return True
        if h.command=='POST':
            state.throttle('personal:'+uid,120)
            data=h.body(1100000)
            if not iid:
                fields(data,('name','payload'),('id',));h.send_json(store.save(uid,kind,data['name'],data['payload'],data.get('id')));return True
            if action=='rename':fields(data,('name',));store.rename(uid,kind,iid,data['name'])
            elif action=='delete':fields(data,());store.delete(uid,kind,iid)
            else:raise KeyError(path)
            h.send_json({'ok':True});return True
        raise KeyError(path)
    return False
