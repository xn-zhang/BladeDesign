import copy,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]));sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from batch_service import BatchService
from core import ROOT,QueueFullError,load_template
from evaluation.batch_data import generate
from test_batch_data import PLAN

class FakeManager:
    def __init__(self):self.jobs={};self.keys={};self.cancelled=[];self.full=False;self.uncertain=False;self.templates={'pritchard-cascade-2d':load_template(ROOT/'templates/pritchard-cascade-2d')}
    def health(self):return {'ready':True}
    def find_submission(self,k):return copy.deepcopy(self.jobs[self.keys[k]]) if k in self.keys else None
    def submit(self,payload,template_override=None):
        old=self.find_submission(payload['submission_key'])
        if old:return old
        if self.full:raise QueueFullError('fixture queue full')
        jid=f'{len(self.jobs)+1:032x}';j={**copy.deepcopy(payload),'id':jid,'status':'running','message':'explicit orchestration fixture'};self.jobs[jid]=j;self.keys[payload['submission_key']]=jid
        if self.uncertain:self.uncertain=False;raise OSError('fixture uncertain response')
        return copy.deepcopy(j)
    def get(self,jid):return copy.deepcopy(self.jobs[jid])
    def cancel(self,jid):self.cancelled.append(jid);self.jobs[jid]['status']='cancelled';return self.get(jid)

class BatchServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.m=FakeManager();self.s=BatchService(self.root,self.m,False);self.manifest=generate({**PLAN,'count':3},self.root);self.b=self.s.create(self.manifest['id']);self.bid=self.b['id']
    def tearDown(self):self.s.shutdown();self.tmp.cleanup()
    def test_duplicate_create_bounded_queue_pause_resume_cancel(self):
        self.assertEqual(self.s.create(self.manifest['id'])['id'],self.bid);self.s.control(self.bid,'start',{'max_in_flight':2});self.s.tick();self.assertEqual(len(self.m.jobs),2)
        self.s.control(self.bid,'pause',{});self.m.jobs[next(iter(self.m.jobs))]['status']='completed';self.s.tick();self.assertEqual(len(self.m.jobs),2)
        self.s.control(self.bid,'resume',{});self.s.tick();self.assertEqual(len(self.m.jobs),3)
        self.s.control(self.bid,'cancel',{});self.s.tick();self.assertEqual(self.s.get(self.bid)['status'],'cancelled');self.assertEqual(len(self.m.cancelled),2)
        b=self.s.get(self.bid);chosen=next(c for c in b['cases'] if c['status']=='cancelled');self.s.control(self.bid,'retry',{'case_ids':[chosen['id']]});self.assertEqual(next(c for c in self.s.get(self.bid)['cases'] if c['id']==chosen['id'])['attempt'],1)
    def test_queue_full_does_not_fail_or_duplicate_and_snapshot_is_frozen(self):
        self.m.full=True;self.s.control(self.bid,'start',{});self.s.tick();self.assertEqual(len(self.m.jobs),0);self.assertEqual(self.s.get(self.bid)['status'],'running')
        self.m.full=False;self.s.tick();self.assertEqual(len(self.m.jobs),2);snapshot=self.root/'batches'/self.bid/'template';self.assertTrue((snapshot/'system/controlDict').is_file())
        (snapshot/'system/controlDict').write_text('changed',encoding='utf-8');self.s.tick();self.assertEqual(self.s.get(self.bid)['status'],'paused');self.assertIn('修改',self.s.get(self.bid)['message'])
    def test_uncertain_submit_reconciles_on_restart_without_duplicate(self):
        self.m.uncertain=True;self.s.control(self.bid,'start',{});self.s.tick();self.assertEqual(len(self.m.jobs),1);self.assertEqual(self.s.get(self.bid)['status'],'paused')
        resumed=BatchService(self.root,self.m,False)
        try:
            resumed.control(self.bid,'resume',{});resumed.tick();self.assertEqual(len(self.m.jobs),2);self.assertEqual(len(resumed.get(self.bid)['cases'][0]['jobs']),1)
        finally:resumed.shutdown()
    def test_dataset_selection_requires_completion_or_explicit_partial(self):
        self.s.control(self.bid,'start',{});self.s.tick()
        with self.assertRaises(ValueError):self.s.selection(self.bid)
        self.m.jobs[next(iter(self.m.jobs))]['status']='completed';self.s.tick();selection=self.s.selection(self.bid,True)
        self.assertEqual(len(selection['cases']),1);self.assertEqual(len(selection['unselected_cases']),5)
        self.s.attach_dataset(self.bid,{'dataset_id':'d'*24,'accepted':[],'rejected':[{'job_id':selection['cases'][0]['job_id'],'reason':'not converged'}]})
        self.s.control(self.bid,'pause',{});self.s.control(self.bid,'retry',{'case_ids':[selection['cases'][0]['id']]});self.assertEqual(self.s.get(self.bid)['cases'][0]['quality'],'unknown')
    def test_model_only_can_save_but_not_run_and_validates_import_hash(self):
        s=BatchService(self.root,None,False)
        try:
            with self.assertRaisesRegex(ValueError,'OpenFOAM'):s.control(self.bid,'start',{})
            path=self.root/'design-batches'/self.manifest['id']/'manifest.json';data=json.loads(path.read_text());data['designs'][0]['parameters']['radius']=999;path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'摘要'):s.create(self.manifest['id'])
        finally:s.shutdown()
    def test_missing_job_does_not_prevent_cancelling_other_batch_jobs(self):
        self.s.control(self.bid,'start',{});self.s.tick();missing=next(iter(self.m.jobs));del self.m.jobs[missing]
        self.s.control(self.bid,'cancel',{});self.s.tick();b=self.s.get(self.bid)
        self.assertEqual(b['status'],'cancelled');self.assertEqual(b['cases'][0]['status'],'unknown');self.assertEqual(len(self.m.cancelled),1)

if __name__=='__main__':unittest.main()
