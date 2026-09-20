"""Fixture orchestration tests: these do not represent CFD solver validation."""
import copy,json,pathlib,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from evaluation_service import EvaluationService,Cancelled,write
from session_store import StateStore
from server import make_server

P={'model':'pritchard-1985','radius':150,'bladeCount':51,'axialChord':28,'tangentialChord':15,'throat':8.5,'leadingRadius':.7,'trailingRadius':.4,'inletAngle':35,'outletAngle':-57,'inletHalfWedge':9,'unguidedTurning':6.5,'height':60}
C={'inletTotalPressure':100200,'inletTotalTemperature':300,'outletStaticPressure':100000,'iterations':3000}
CFG={'parameters':P,'conditions':C,'mode':'cfd','bounds':{'radius':[145,155]},'budget':4,'seed':42,'objectives':[{'metric':'loss_coefficient','direction':'min'}],'constraints':[]}

class FakeManager:
    def __init__(self):self.jobs={};self.cancelled=[];self.release=threading.Event();self.release.set()
    def health(self):return {'ready':True}
    def submit(self,p):
        jid=f'{len(self.jobs)+1:032x}';self.jobs[jid]={'id':jid,'status':'running','parameters':copy.deepcopy(p['parameters'])};return self.jobs[jid]
    def get(self,jid):
        j=self.jobs[jid]
        if self.release.is_set() and j['status']=='running':j['status']='completed'
        return copy.deepcopy(j)
    def cancel(self,jid):self.cancelled.append(jid);self.jobs[jid]['status']='cancelled'

class FixtureService(EvaluationService):
    def compute(self,tid,kind,payload):
        self.checkpoint(tid,running=True)
        if kind=='geometry':return {}
        if kind=='analyze':
            j=self.manager.get(payload['job_id']);r=j['parameters']['radius']
            return {'source':'orchestration-test-fixture','quality':'workflow','metrics':{'version':'fixture-v1','values':{'loss_coefficient':(r-149)**2}},'template_hash':'fixture-template','thermo_hash':'fixture-thermo','condition_hash':'fixture-condition','parameters':j['parameters'],'job_id':j['id']}
        if kind=='predict_batch':return [{'domain':{'in_domain':False},'values':{'loss_coefficient':0}} for _ in payload['parameters']]
        return {'fixture':True}

def wait_for(condition,seconds=5):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if condition():return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for fixture state')

class TaskTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.manager=FakeManager();self.s=FixtureService(self.root/'data',self.root/'jobs',self.manager)
    def tearDown(self):self.manager.release.set();self.s.shutdown();self.tmp.cleanup()
    def test_closed_loop_budget_snapshots_pareto_and_restart(self):
        cfg=copy.deepcopy(CFG);t=self.s.submit('optimize',cfg);cfg['parameters']['radius']=999
        wait_for(lambda:self.s.get(t['id'])['status']=='completed');r=self.s.get(t['id'])
        self.assertEqual(len(self.manager.jobs),4);self.assertEqual(r['payload']['parameters']['radius'],150)
        self.assertEqual(len(r['result']['history']),4);self.assertTrue(r['result']['pareto_indices']);self.assertTrue(any(c['stage']=='refinement' for c in r['result']['candidates']))
        restarted=EvaluationService(self.root/'data',self.root/'jobs');self.assertEqual(restarted.get(t['id'])['status'],'completed');restarted.shutdown()
    def test_pause_between_jobs_resume_then_cancel_owns_only_current(self):
        self.manager.release.clear();t=self.s.submit('optimize',copy.deepcopy(CFG));tid=t['id'];wait_for(lambda:len(self.manager.jobs)==1)
        self.s.control(tid,'pause');self.manager.release.set();wait_for(lambda:self.s.get(tid)['status']=='paused');self.assertEqual(len(self.manager.jobs),1)
        self.manager.release.clear();self.s.control(tid,'resume');wait_for(lambda:len(self.manager.jobs)==2);self.s.control(tid,'cancel');wait_for(lambda:self.s.get(tid)['status']=='cancelled')
        self.assertEqual(set(self.manager.cancelled),{f'{2:032x}'})
    def test_stale_tasks_interrupted_and_manager_absence_gated(self):
        other=self.root/'other';write(other/'tasks'/('a'*32)/'task.json',{'id':'a'*32,'status':'running','created_at':0,'kind':'train'})
        s=EvaluationService(other,self.root/'jobs')
        try:
            self.assertEqual(s.get('a'*32)['status'],'interrupted');self.assertFalse(s.capabilities()['cfd_ready'])
            with self.assertRaises(ValueError):s.submit('optimize',CFG)
            with self.assertRaises(ValueError):s.submit('analyze',{'job_id':'../etc'})
            with self.assertRaises(ValueError):s.submit('dataset',{'command':'bad'})
        finally:s.shutdown()
    def test_mixed_cfd_context_is_excluded_from_ranking(self):
        original=self.s.compute
        def mixed(tid,kind,payload):
            result=original(tid,kind,payload)
            if kind=='analyze' and int(payload['job_id'],16)>1:
                result['template_hash']='changed-template';result['metrics']['values']['loss_coefficient']=-100
            return result
        self.s.compute=mixed;t=self.s.submit('optimize',copy.deepcopy(CFG));wait_for(lambda:self.s.get(t['id'])['status']=='completed');r=self.s.get(t['id'])['result']
        self.assertEqual(r['best_index'],0);self.assertEqual(sum(c['status']=='verified' for c in r['candidates']),1)
    def test_surrogate_context_mismatch_stops_after_baseline(self):
        mid='a'*24;write(self.root/'data/models'/mid/'card.json',{'model_id':mid,'experimental':False});original=self.s.compute
        def outdated(tid,kind,payload):
            if kind=='predict_batch':return [{'domain':{'in_domain':True},'metric_version':'fixture-v1','template_hash':'outdated','thermo_hash':'fixture-thermo','condition_hash':'fixture-condition','values':{'loss_coefficient':0}} for _ in payload['parameters']]
            return original(tid,kind,payload)
        self.s.compute=outdated;t=self.s.submit('optimize',{**copy.deepcopy(CFG),'mode':'surrogate','model_id':mid});wait_for(lambda:self.s.get(t['id'])['status'] in ('completed','failed'));r=self.s.get(t['id'])
        self.assertEqual(r['status'],'failed');self.assertEqual(len(self.manager.jobs),1)
    def test_matching_surrogate_screens_after_baseline_and_ranks_cfd(self):
        mid='b'*24;write(self.root/'data/models'/mid/'card.json',{'model_id':mid,'experimental':False});original=self.s.compute;events=[]
        def compatible(tid,kind,payload):
            events.append(kind)
            if kind=='predict_batch':return [{'domain':{'in_domain':True},'metric_version':'fixture-v1','template_hash':'fixture-template','thermo_hash':'fixture-thermo','condition_hash':'fixture-condition','values':{'loss_coefficient':-123}} for _ in payload['parameters']]
            return original(tid,kind,payload)
        self.s.compute=compatible;t=self.s.submit('optimize',{**copy.deepcopy(CFG),'mode':'surrogate','model_id':mid});wait_for(lambda:self.s.get(t['id'])['status'] in ('completed','failed'));r=self.s.get(t['id'])
        self.assertEqual(r['status'],'completed',r['message']);self.assertEqual(len(self.manager.jobs),4);self.assertLess(events.index('analyze'),events.index('predict_batch'))
        best=r['result']['candidates'][r['result']['best_index']];self.assertGreaterEqual(best['values']['loss_coefficient'],0);self.assertEqual(best['prediction']['values']['loss_coefficient'],-123)
    def test_real_worker_empty_dataset(self):
        s=EvaluationService(self.root/'real',self.root/'empty')
        try:
            t=s.submit('dataset',{});wait_for(lambda:s.get(t['id'])['status'] in ('completed','failed'),30);r=s.get(t['id']);self.assertEqual(r['status'],'completed',r['message']);self.assertEqual(r['result']['summary']['accepted'],0)
        finally:s.shutdown()
    def test_authenticated_api_static_allowlist_and_cross_origin(self):
        state=StateStore(self.root/'state.sqlite3');http=make_server('127.0.0.1',0,None,'fixture-api-token-at-least-24-characters',set(),state=state,evaluation=self.s)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(http.server_port)
        def req(path,auth=True,body=None,origin=None):
            headers={'Authorization':'Bearer fixture-api-token-at-least-24-characters'} if auth else {}
            if body is not None:headers['Content-Type']='application/json'
            if origin:headers['Origin']=origin
            request=urllib.request.Request(base+path,headers=headers,data=None if body is None else json.dumps(body).encode())
            try:
                with urllib.request.urlopen(request) as r:return r.status,r.read()
            except urllib.error.HTTPError as e:return e.code,e.read()
        try:
            self.assertEqual(req('/api/evaluation/capabilities',False)[0],401);self.assertEqual(req('/api/evaluation/capabilities',origin='https://evil.example')[0],403)
            self.assertEqual(req('/api/evaluation/capabilities')[0],200);self.assertEqual(req('/evaluation.js',False)[0],200)
            self.assertEqual(req('/ai-data/models/secret')[0],404);self.assertEqual(req('/api/evaluation/dataset',body={'command':'bad'})[0],400)
            code,body=req('/api/evaluation/dataset',body={});self.assertEqual(code,202);tid=json.loads(body)['id'];wait_for(lambda:self.s.get(tid)['status']=='completed');self.assertEqual(req('/api/evaluation/tasks/'+tid)[0],200)
        finally:http.shutdown();http.server_close();state.close()

if __name__=='__main__':unittest.main()
