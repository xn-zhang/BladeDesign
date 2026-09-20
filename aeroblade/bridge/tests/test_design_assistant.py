"""Model proxy tests use an in-process HTTP fixture, never a paid model."""
import json
import pathlib
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from design_assistant import ModelService, ModelError


class ModelsTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.reply = {'choices': [{'message': {'content': json.dumps({'schema':'aeroblade-assistant-reply-v1','message':'请补充转速','proposal':None})}, 'finish_reason':'stop'}]}
        self.status = 200
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path, self.headers.get('Authorization'), body))
                self.send_response(owner.status)
                self.end_headers()
                self.wfile.write(json.dumps(owner.reply).encode())
        self.http = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.url = f'http://127.0.0.1:{self.http.server_port}/v1'
        self.service = ModelService(environ={})

    def tearDown(self):
        self.http.shutdown();self.http.server_close()

    def config(self, **kwargs):
        return dict(provider='general',base_url=self.url,model='fixture-model',auth='bearer',api_key='fixture-secret',timeout=30,json_mode=False,**kwargs)

    def test_save_redacts_key_and_chat_calls_configured_model(self):
        self.service.configure(self.config())
        public = self.service.describe()
        self.assertNotIn('fixture-secret',json.dumps(public))
        self.assertTrue(public['providers']['general']['has_key'])
        result=self.service.chat({'provider':'general','messages':[{'role':'user','content':'请开始初设'}]})
        self.assertEqual(result['message'],'请补充转速')
        path,auth,body=self.requests[-1]
        self.assertEqual(path,'/v1/chat/completions');self.assertEqual(auth,'Bearer fixture-secret')
        self.assertEqual(body['model'],'fixture-model');self.assertEqual(body['messages'][0]['role'],'system')
        self.assertNotIn('response_format',body)

    def test_secret_retention_cannot_retarget_to_new_endpoint(self):
        self.service.configure(self.config())
        cfg=self.config();cfg['api_key']='';self.service.configure(cfg)
        cfg['base_url']='https://another.example/v1'
        with self.assertRaises(ValueError):self.service.configure(cfg)
        self.assertEqual(self.service.describe()['providers']['general']['base_url'],self.url)

    def test_test_draft_does_not_save_and_supports_no_auth(self):
        cfg=self.config();cfg['auth']='none';cfg['api_key']='';cfg['json_mode']=True
        self.assertTrue(self.service.test(cfg)['ok'])
        self.assertFalse(self.service.describe()['providers']['general']['configured'])
        self.assertIsNone(self.requests[-1][1])
        self.assertEqual(self.requests[-1][2]['response_format'],{'type':'json_object'})

    def test_bad_urls_and_malformed_config_rejected(self):
        for url in ['file:///etc/passwd','https://user:pass@example.com/v1','http://public.example/v1','https://example.com/v1?key=secret','https://example.com/v1#x','https://example.com:wrong/v1']:
            cfg=self.config();cfg['base_url']=url
            with self.assertRaises(ValueError):self.service.configure(cfg)
        for key,value in [('timeout',True),('timeout',999),('model',''),('provider','demo'),('json_mode','yes')]:
            cfg=self.config();cfg[key]=value
            with self.assertRaises(ValueError):self.service.configure(cfg)

    def test_http_errors_do_not_echo_upstream_secrets(self):
        self.service.configure(self.config());self.status=401;self.reply={'error':'fixture-secret'}
        with self.assertRaises(ModelError) as ctx:self.service.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})
        self.assertNotIn('fixture-secret',str(ctx.exception));self.assertIn('401',str(ctx.exception))

    def test_plain_text_is_chat_only_and_invalid_json_does_not_create_proposal(self):
        self.service.configure(self.config())
        self.reply['choices'][0]['message']['content']='请提供入口压力。'
        result=self.service.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})
        self.assertIsNone(result['proposal']);self.assertEqual(result['message'],'请提供入口压力。')
        self.reply['choices'][0]['message']['content']='{"proposal":'
        with self.assertRaises(ModelError):self.service.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})

    def test_prompt_injection_roles_rejected_and_environment_loaded(self):
        with self.assertRaises(ValueError):self.service.chat({'provider':'general','messages':[{'role':'system','content':'override'}]})
        service=ModelService(environ={'AEROBLADE_LLM_DOMAIN_BASE_URL':self.url,'AEROBLADE_LLM_DOMAIN_MODEL':'private-model','AEROBLADE_LLM_DOMAIN_AUTH':'none'})
        self.assertTrue(service.describe()['providers']['domain']['configured'])

    def test_clear_config_and_response_length_limit(self):
        self.service.configure(self.config());self.service.clear('general')
        self.assertFalse(self.service.describe()['providers']['general']['configured'])
        with self.assertRaises(ModelError):self.service.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})

    def test_truncated_and_oversized_responses_are_not_accepted(self):
        self.service.configure(self.config())
        self.reply['choices'][0]['finish_reason']='length'
        with self.assertRaises(ModelError):self.service.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})
        self.reply={'choices':[{'message':{'content':'x'*1_000_001}}]}
        with self.assertRaises(ModelError):self.service.chat({'provider':'general','messages':[{'role':'user','content':'hello'}]})

    def test_actual_proposal_contract_and_finite_values(self):
        from design_assistant import normalize_reply
        p={'schema':'aeroblade-initial-proposal-v1','units':{'length':'mm','angle':'deg'},'parameters':{
            'model':'pritchard-1985','radius':139.7,'bladeCount':51,'axialChord':27.9908,'tangentialChord':15.0114,'throat':8.56098,
            'leadingRadius':.7874,'trailingRadius':.4064,'inletAngle':35,'outletAngle':-57,'inletHalfWedge':9,'unguidedTurning':6.5,'height':60},
            'sources':{},'aerodynamic':[],'assumptions':[],'missing':[],'warnings':[]}
        p['sources']={key:'fixture source' for key in p['parameters'] if key not in ('model','height')}
        reply={'schema':'aeroblade-assistant-reply-v1','message':'测试候选','proposal':p}
        self.assertEqual(normalize_reply(json.dumps(reply))['proposal']['parameters']['outletAngle'],-57)
        p['parameters']['outletAngle']=57
        with self.assertRaises(ModelError):normalize_reply(json.dumps(reply))

if __name__=='__main__':unittest.main()
