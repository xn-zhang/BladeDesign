import unittest,tempfile,pathlib,sys,threading,json,urllib.request,urllib.error
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server,core
from unittest.mock import patch
class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(self.tmp.name);self.manager=core.Manager(p/'jobs',p/'templates')
        self.http=server.make_server('127.0.0.1',0,self.manager,'test-token-which-is-at-least-24-characters',{'https://design.example'})
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.http.server_port)
    def test_scheduler_requires_auth_and_rejects_invalid_settings(self):
        self.assertEqual(self.req('/api/scheduler',token=False)[0],401)
        self.assertEqual(self.req('/api/scheduler',token=False,method='POST',data={'max_parallel':1})[0],401)
        self.assertEqual(self.req('/api/scheduler',origin='https://untrusted.example',method='POST',data={'max_parallel':1})[0],403)
        for value in [0,999,True,1.5,'2']:
            self.assertEqual(self.req('/api/scheduler',method='POST',data={'max_parallel':value})[0],400)
        self.assertEqual(self.req('/api/scheduler',method='POST',data={'max_parallel':1,'command':'anything'})[0],400)
        status,_,body=self.req('/api/scheduler',method='POST',data={'max_parallel':1})
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['max_parallel'],1)
        status,_,body=self.req('/api/jobs');self.assertEqual(status,200);self.assertEqual(json.loads(body)['scheduler']['max_parallel'],1)
    def test_full_queue_uses_429_without_creating_a_job(self):
        with patch.object(self.manager,'submit',side_effect=core.QueueFullError('queue full')):
            self.assertEqual(self.req('/api/jobs',method='POST',data={'schema':'aeroblade-cfd-v1'})[0],429)
        self.assertEqual(self.manager.list(),[])
    def tearDown(self):self.http.shutdown();self.http.server_close();self.manager.pool.shutdown();self.tmp.cleanup()
    def req(self,path,token=True,origin=None,method='GET',data=None):
        headers={}
        if token:headers['Authorization']='Bearer test-token-which-is-at-least-24-characters'
        if origin:headers['Origin']=origin
        if data is not None:headers['Content-Type']='application/json';data=json.dumps(data).encode()
        request=urllib.request.Request(self.base+path,headers=headers,method=method,data=data)
        try:
            with urllib.request.urlopen(request) as r:return r.status,dict(r.headers),r.read()
        except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
    def test_flow_requires_auth_and_completed_job(self):
        id='a'*32
        self.manager.jobs[id]={'id':id,'status':'running'}
        self.assertEqual(self.req('/api/jobs/'+id+'/flow',token=False)[0],401)
        self.assertEqual(self.req('/api/jobs/'+id+'/flow')[0],400)
        self.assertEqual(self.req('/api/jobs/'+'b'*32+'/flow')[0],404)
    def test_flow_returns_actual_cell_values(self):
        from test_flow import fixture
        id='a'*32;self.manager.jobs[id]={'id':id,'status':'completed'}
        fixture(self.manager.root/id/'case')
        code,_,body=self.req('/api/jobs/'+id+'/flow');self.assertEqual(code,200)
        data=json.loads(body);self.assertEqual(data['job_id'],id)
        self.assertEqual(data['fields']['speed']['values'],[5.,0.])
    def test_unauthenticated_health_rejected(self):self.assertEqual(self.req('/api/health',token=False)[0],401)
    def test_model_routes_require_auth_and_do_not_expose_credentials(self):
        for path in ['config','test','clear','chat']:
            self.assertEqual(self.req('/api/design-assistant/'+path,token=False,method='POST',data={})[0],401)
        self.assertEqual(self.req('/api/design-assistant/config',token=False)[0],401)
        cfg={'provider':'general','base_url':'https://model.example/v1','model':'test-model','api_key':'fixture-secret','auth':'bearer','timeout':30,'json_mode':False}
        self.assertEqual(self.req('/api/design-assistant/config',method='POST',origin='https://untrusted.example',data=cfg)[0],403)
        status,_,body=self.req('/api/design-assistant/config',method='POST',data=cfg)
        self.assertEqual(status,200);self.assertNotIn(b'fixture-secret',body)
        status,_,body=self.req('/api/design-assistant/config');self.assertEqual(status,200);self.assertNotIn(b'fixture-secret',body)
        self.assertTrue(json.loads(body)['providers']['general']['has_key'])
        self.assertEqual(self.req('/api/design-assistant/clear',method='POST',data={'provider':'general'})[0],200)
        self.assertEqual(self.req('/api/design-assistant/chat',method='POST',data={'provider':'general','messages':[{'role':'user','content':'hello'}]})[0],503)
    def test_model_frontend_modules_are_public_but_source_is_not(self):
        for name in ['design-assistant.js','design-assistant-client.js','design-assistant.css','model-settings.js','model-settings.css']:
            self.assertEqual(self.req('/'+name,token=False)[0],200)
        self.assertEqual(self.req('/bridge/design_assistant.py',token=False)[0],404)
    def test_correct_origin_and_auth_get_real_not_ready(self):
        code,headers,body=self.req('/api/health',origin='https://design.example');self.assertEqual(code,200);self.assertFalse(json.loads(body)['ready']);self.assertEqual(headers['Access-Control-Allow-Origin'],'https://design.example')
    def test_other_origin_rejected(self):self.assertEqual(self.req('/api/jobs',origin='https://evil.example')[0],403)
    def test_preflight_is_explicit(self):
        code,headers,_=self.req('/api/jobs',token=False,origin='https://design.example',method='OPTIONS');self.assertEqual(code,204);self.assertEqual(headers['Access-Control-Allow-Origin'],'https://design.example')
    def test_cannot_submit_without_solver(self):self.assertEqual(self.req('/api/jobs',method='POST',data={'schema':'aeroblade-cfd-v1'})[0],400)
    def test_no_source_or_path_traversal_exposure(self):
        for path in ['/bridge/core.py','/../bridge/core.py','/%2e%2e/bridge/core.py']:
            self.assertEqual(self.req(path,token=False)[0],404)
if __name__=='__main__':unittest.main()
