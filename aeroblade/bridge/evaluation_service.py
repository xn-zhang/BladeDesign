"""Bounded authenticated task orchestration. Numerical imports stay in workers."""
import concurrent.futures,copy,json,os,pathlib,re,subprocess,sys,threading,time,uuid
from optimization import run_search,validate_config

ROOT=pathlib.Path(__file__).resolve().parents[1]
TERMINAL={'completed','failed','cancelled','interrupted'}
class Cancelled(Exception):pass

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8');os.replace(tmp,path)

class EvaluationService:
    def __init__(self,root=None,jobs=None,manager=None,python=None):
        self.root=pathlib.Path(root or ROOT/'ai-data').resolve();self.jobs=pathlib.Path(jobs or ROOT/'jobs').resolve();self.manager=manager
        self.batch_service=None
        venv=ROOT.parent/'.venv-evaluation'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        self.python=python or os.environ.get('AEROBLADE_EVALUATION_PYTHON') or (str(venv) if venv.is_file() else sys.executable)
        self.lock=threading.RLock();self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='evaluation');self.tasks={};self.processes={};self.stopped=False
        for p in (self.root/'tasks').glob('*/task.json'):
            try:
                task=json.loads(p.read_text(encoding='utf-8'))
                if task['status'] not in TERMINAL:task.update(status='interrupted',message='服务重启；未自动恢复计算，请检查已有CFD任务后重新发起');write(p,task)
                self.tasks[task['id']]=task
            except (ValueError,KeyError,OSError):continue
    def capabilities(self):
        health=self.manager.health() if self.manager else {}
        return {'schema':'aeroblade-evaluation-v1','cfd_ready':bool(health.get('ready')),'reason':None if health.get('ready') else '需要在已配置OpenFOAM的计算服务上启动完整bridge；当前服务可扫描已有CFD、训练与预测','algorithms':['ridge','extra_trees','mlp'],'max_tasks':4,'max_cfd_budget':30,'template_id':'pritchard-cascade-2d'}
    def get(self,tid):
        with self.lock:
            if tid not in self.tasks:raise KeyError(tid)
            return copy.deepcopy(self.tasks[tid])
    def save(self,t):t['updated_at']=time.time();write(self.root/'tasks'/t['id']/'task.json',t)
    def update(self,tid,**fields):
        with self.lock:self.tasks[tid].update(fields);self.save(self.tasks[tid])
    def catalog(self,kind):
        if kind=='tasks':
            with self.lock:return [copy.deepcopy(t) for t in sorted(self.tasks.values(),key=lambda t:t['created_at'],reverse=True)[:40]]
        filename={'datasets':'manifest.json','models':'card.json'}[kind];out=[]
        for p in (self.root/kind).glob('*/'+filename):
            if re.fullmatch('[a-f0-9]{24}',p.parent.name) and not p.is_symlink() and not p.parent.is_symlink():
                try:out.append(json.loads(p.read_text(encoding='utf-8')))
                except (ValueError,OSError):continue
        return sorted(out,key=lambda d:d.get('created_at',0),reverse=True)
    def submit(self,kind,payload):
        allowed={'dataset':{'batch_id','allow_partial'},'batch_generate':{'plan'},'batch_import':{'bundle'},'train':{'dataset_id','algorithm','seed'},'predict':{'model_id','parameters','conditions'},'analyze':{'job_id'},'evaluate':{'parameters','conditions'},'optimize':{'parameters','conditions','mode','bounds','budget','seed','objectives','constraints','model_id','allow_experimental'}}
        if kind not in allowed or not isinstance(payload,dict) or set(payload)-allowed[kind]:raise ValueError('任务字段无效')
        payload=copy.deepcopy(payload)
        if kind=='batch_generate':
            from batch_contract import validate_plan
            payload['plan']=validate_plan(payload.get('plan'))
        if kind=='batch_import' and not isinstance(payload.get('bundle'),dict):raise ValueError('请上传有效参数包')
        if kind=='dataset' and payload:
            if not payload.get('batch_id') or self.batch_service is None:raise ValueError('批次数据服务未配置或未选择批次')
            payload['selection']=self.batch_service.selection(payload['batch_id'],payload.get('allow_partial',False))
        for key,length in [('dataset_id',24),('model_id',24),('job_id',32)]:
            if key in payload and (not isinstance(payload[key],str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',payload[key])):raise ValueError('记录标识无效')
        if kind in ('evaluate','optimize') and not self.capabilities()['cfd_ready']:raise ValueError(self.capabilities()['reason'])
        if kind=='optimize':
            validate_config(payload)
            if not self.capabilities()['cfd_ready']:raise ValueError(self.capabilities()['reason'])
            if payload['mode']=='surrogate':
                mid=payload.get('model_id');card=next((m for m in self.catalog('models') if m['model_id']==mid),None)
                if card is None:raise ValueError('请选择已训练模型')
                if card['experimental'] and payload.get('allow_experimental') is not True:raise ValueError('当前模型为小样本实验模型；需明确允许实验性筛选')
        with self.lock:
            if self.stopped:raise ValueError('服务正在关闭')
            active=[t for t in self.tasks.values() if t['status'] not in TERMINAL]
            if len(active)>=4:raise ValueError('评估队列已满（最多4个任务）')
            if kind=='optimize' and any(t['kind']=='optimize' for t in active):raise ValueError('已有优化任务运行，请先完成或取消')
            tid=uuid.uuid4().hex;t={'id':tid,'kind':kind,'status':'queued','created_at':time.time(),'payload':copy.deepcopy(payload),'message':'排队等待独立计算进程','result':None};self.tasks[tid]=t;self.save(t);self.pool.submit(self.run,tid);return copy.deepcopy(t)
    def control(self,tid,action):
        with self.lock:
            t=self.tasks.get(tid)
            if t is None:raise KeyError(tid)
            if t['status'] in TERMINAL:return copy.deepcopy(t)
            if action=='cancel':
                t['cancel_requested']=True;t['message']='正在取消本任务';proc=self.processes.get(tid)
                if proc and proc.poll() is None:proc.terminate()
                if t.get('active_job') and self.manager:self.manager.cancel(t['active_job'])
            elif action in ('pause','resume') and t['kind']=='optimize':t['pause_requested']=action=='pause';t['message']='当前CFD结束后暂停' if action=='pause' else '继续优化'
            else:raise ValueError('不支持此控制操作')
            self.save(t);return copy.deepcopy(t)
    def checkpoint(self,tid,job=None,running=False):
        while True:
            with self.lock:
                t=self.tasks[tid]
                if job:t['active_job']=job
                if t.get('cancel_requested') or self.stopped:
                    if job and self.manager:self.manager.cancel(job)
                    raise Cancelled()
                if running or not t.get('pause_requested'):
                    if t['status']=='paused':t['status']='running';self.save(t)
                    return
                if t['status']!='paused':t['status']='paused';t['message']='已暂停；继续后处理下一个候选';self.save(t)
            time.sleep(.15)
    def compute(self,tid,kind,payload):
        # Numeric work can finish the active CFD analysis while a pause is pending.
        self.checkpoint(tid,running=True);folder=self.root/'tasks'/tid;request=folder/'request.json';result=folder/'worker-result.json'
        if result.exists():result.unlink()
        write(request,{'kind':kind,'payload':payload,'root':str(self.root),'jobs':str(self.jobs)})
        env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONUTF8':'1'}
        log=folder/'worker.log'
        with log.open('ab') as f:
            with self.lock:
                if self.tasks[tid].get('cancel_requested') or self.stopped:raise Cancelled()
                proc=subprocess.Popen([self.python,'-X','utf8','-m','evaluation.worker','--request',str(request),'--result',str(result)],cwd=ROOT,env=env,stdout=f,stderr=f,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);self.processes[tid]=proc
            try:proc.wait(timeout=1800)
            except subprocess.TimeoutExpired:proc.kill();proc.wait();raise ValueError('评估计算超时（30分钟）')
            finally:
                with self.lock:self.processes.pop(tid,None)
        self.checkpoint(tid,running=True)
        if proc.returncode or not result.exists():raise ValueError('计算进程失败；请检查数值环境：numpy/scipy/scikit-learn，MLP另需torch。'+log.read_text(encoding='utf-8',errors='replace')[-700:])
        value=json.loads(result.read_text(encoding='utf-8'))
        if not value['ok']:raise ValueError(value['error'])
        return value['result']
    def run(self,tid):
        try:
            self.checkpoint(tid);self.update(tid,status='running',message='计算中');t=self.get(tid)
            if t['kind']=='optimize':
                run_search(t['payload'],lambda k,p:self.compute(tid,k,p),self.manager,lambda job=None,running=False:self.checkpoint(tid,job,running),lambda r:self.update(tid,result=r,message='CFD复核 '+str(r['submitted'])+'/'+str(r['budget'])))
                self.checkpoint(tid,running=True);self.update(tid,status='completed',message='优化结束；仅质量通过的CFD候选参与最优与Pareto排序',active_job=None)
            elif t['kind']=='evaluate':
                self.compute(tid,'geometry',{'parameters':t['payload']['parameters']});self.checkpoint(tid)
                job=self.manager.submit({'schema':'aeroblade-cfd-v1','name':'性能评估','template_id':'pritchard-cascade-2d',**t['payload']})
                self.update(tid,active_job=job['id'])
                while True:
                    self.checkpoint(tid,job['id'],True);job=self.manager.get(job['id'])
                    if job['status'] in TERMINAL:break
                    time.sleep(.25)
                if job['status']!='completed':raise ValueError('CFD '+job['status']+': '+job.get('message',''))
                result=self.compute(tid,'analyze',{'job_id':job['id']});self.update(tid,status='completed',result=result,message='CFD评估完成，质量门槛通过',active_job=None)
            else:
                result=self.compute(tid,t['kind'],t['payload'])
                if t['kind']=='dataset' and t['payload'].get('batch_id'):self.batch_service.attach_dataset(t['payload']['batch_id'],result)
                self.update(tid,status='completed',result=result,message='计算完成')
        except Cancelled:self.update(tid,status='cancelled',message='已取消；保留已有结果',active_job=None)
        except Exception as e:self.update(tid,status='failed',message=str(e)[:1800],active_job=None)
    def shutdown(self):
        with self.lock:
            self.stopped=True
            for proc in self.processes.values():
                if proc.poll() is None:proc.terminate()
            for t in self.tasks.values():
                if t.get('active_job') and t['status'] not in TERMINAL and self.manager:self.manager.cancel(t['active_job'])
        self.pool.shutdown(wait=True,cancel_futures=True)
