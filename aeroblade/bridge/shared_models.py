"""Public connections stay server-side; personal connections override them."""
import json
from design_assistant import ModelService, PROVIDERS


class PublicModelStore:
    def __init__(self,state):self.state=state
    def load_models(self):
        with self.state.lock:row=self.state.db.execute("SELECT value FROM settings WHERE name='public_models'").fetchone()
        return json.loads(row[0]) if row else {}
    def save_models(self,configs):
        with self.state.transaction():
            self.state.db.execute("INSERT INTO settings VALUES('public_models',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(json.dumps(configs,ensure_ascii=False,allow_nan=False),))


class OwnedModels(ModelService):
    def __init__(self,state,uid,public_models,**kwargs):
        self.state=state;self.uid=uid;self.public_models=public_models
        super().__init__(**kwargs)
    def get_config(self,provider):
        private=super().get_config(provider)
        if private:return private
        if self.state.model_policy()['enabled'].get(provider):
            shared=self.public_models.get_config(provider)
            if shared:return {**shared,'_public':True}
        return None
    def before_request(self,cfg):
        if cfg.get('_public'):self.state.consume_public_call(self.uid,cfg['provider'])
    def transport_for(self,cfg):
        return self.public_models.opener if cfg.get('_public') else self.opener
    def describe(self):
        result=super().describe();private=result['providers'];effective={}
        policy=self.state.model_policy()
        for provider in PROVIDERS:
            cfg=self.get_config(provider)
            shared=bool(policy['enabled'][provider] and self.public_models.get_config(provider))
            if cfg and cfg.get('_public'):
                effective[provider]={'provider':provider,'configured':True,'model':cfg['model'],'source':'public','public_available':shared}
            else:effective[provider]={**private[provider],'source':'personal','public_available':shared}
        return {**result,'providers':effective,'personal_providers':private,'default_provider':policy['default_provider'],'public_usage':self.state.public_usage(self.uid)}
