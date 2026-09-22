import json,pathlib,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from server import make_server
from session_store import StateStore
from evaluation_service import EvaluationService
from batch_service import BatchService
from test_batch_data import PLAN

class BatchAPITests(unittest.TestCase):
    def test_model_only_generate_handoff_restore_and_authenticated_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);state=StateStore(root/'state.sqlite3');state.create_admin('admin','fixture-password-123');key,session=state.login('admin','fixture-password-123','local');evaluation=EvaluationService(root/'data',root/'jobs');batches=BatchService(root/'data',None,False);evaluation.batch_service=batches
            http=make_server('127.0.0.1',0,None,'batch-api-fixture-token-32-characters',set(),state=state,evaluation=evaluation,batches=batches);threading.Thread(target=http.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(http.server_port)
            def req(path,body=None,auth=True,origin=None):
                headers={'Cookie':'aeroblade_session='+key,'X-CSRF-Token':session['csrf']} if auth else {}
                if body is not None:headers['Content-Type']='application/json'
                if origin:headers['Origin']=origin
                r=urllib.request.Request(url+path,headers=headers,data=None if body is None else json.dumps(body).encode())
                try:
                    with urllib.request.urlopen(r) as response:return response.status,response.read()
                except urllib.error.HTTPError as e:return e.code,e.read()
            try:
                self.assertEqual(req('/api/batches',auth=False)[0],401);self.assertEqual(req('/api/batches',origin='https://evil.example')[0],403)
                self.assertEqual(req('/batch.js',auth=False)[0],200)
                self.assertEqual(req('/api/batches',{'design_batch_id':'../private'})[0],400)
                self.assertEqual(req('/api/evaluation/dataset',{'selection':{}})[0],400)
                code,raw=req('/api/evaluation/batch_generate',{'plan':PLAN});self.assertEqual(code,202);tid=json.loads(raw)['id'];deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    task=json.loads(req('/api/evaluation/tasks/'+tid)[1])
                    if task['status'] in ('completed','failed'):break
                    time.sleep(.05)
                self.assertEqual(task['status'],'completed',task['message']);mid=task['result']['id']
                code,raw=req('/api/batches',{'design_batch_id':mid});self.assertEqual(code,201);batch=json.loads(raw);self.assertEqual(batch['case_count'],10)
                self.assertEqual(json.loads(req('/api/batches',{'design_batch_id':mid})[1])['id'],batch['id'])
                self.assertEqual(req('/api/batches/'+batch['id']+'/start',{})[0],400)
                self.assertEqual(req('/api/batches/designs/'+mid)[0],200)
                self.assertEqual(req('/api/evaluation/dataset',{'batch_id':batch['id']})[0],400)
                self.assertEqual(req('/api/batches/'+batch['id']+'/cancel',{'all_jobs':True})[0],400)
            finally:http.shutdown();http.server_close();batches.shutdown();evaluation.shutdown();state.close()

if __name__=='__main__':unittest.main()
