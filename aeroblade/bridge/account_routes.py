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
            if h.command=='POST':
                data=fields(h.body(),(),('expires_in','max_uses'));state.throttle('invite:'+uid,100)
                h.send_json(state.create_invite(uid,**data));return True
        if path=='/api/admin/users' and h.command=='GET':
            h.send_json({'users':[{**u,'public_usage':state.public_usage(u['id']) if not u['disabled'] else None} for u in state.list_users(uid)]});return True
        if path=='/api/admin/logs' and h.command=='GET':h.send_json({'logs':state.admin_logs(uid)});return True
        if path=='/api/admin/models':
            if h.command=='GET':h.send_json({**services.public_models.describe(),'policy':state.model_policy()});return True
            if h.command=='POST':h.send_json(services.configure_public(uid,h.body()));return True
        if path=='/api/admin/models/test' and h.command=='POST':
            state.throttle('public-model-test:'+uid,30);h.send_json(services.public_models.test(h.body()));return True
        if path=='/api/admin/models/clear' and h.command=='POST':
            data=fields(h.body(),('provider',));services.clear_public(uid,data['provider']);h.send_json({'ok':True});return True
        if path=='/api/admin/model-policy' and h.command=='POST':
            data=h.body()
            if isinstance(data,dict) and isinstance(data.get('enabled'),dict):
                for provider,enabled in data['enabled'].items():
                    if enabled and not services.public_models.get_config(provider):raise ValueError('请先配置要启用的公共模型')
                if any(data['enabled'].values()) and not data['enabled'].get(data.get('default_provider')):raise ValueError('默认模型必须已启用')
            h.send_json(state.set_model_policy(uid,data));return True
        match=re.fullmatch(r'/api/admin/(invites|users)/([a-f0-9]{32})/(revoke|status|update|logout)',path)
        if match and h.command=='POST':
            kind,iid,action=match.groups();data=h.body()
            if kind=='invites' and action=='revoke':fields(data,());state.revoke_invite(uid,iid)
            elif kind=='invites' and action=='update':
                fields(data,('expires_at','max_uses'));state.update_invite(uid,iid,data['expires_at'],data['max_uses'])
            elif kind=='users' and action=='logout':fields(data,());state.force_logout(uid,iid)
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
