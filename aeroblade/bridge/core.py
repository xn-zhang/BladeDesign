"""Owner-operated bounded concurrent OpenFOAM runner. No shell or client-selected commands."""
from collections import deque
import concurrent.futures, json, math, os, pathlib, re, shutil, signal, subprocess, threading, time, uuid, zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
COMMANDS={'extrudeMesh','createPatch','blockMesh','surfaceFeatureExtract','snappyHexMesh','checkMesh','rhoSimpleFoam','rhoPimpleFoam','simpleFoam','foamToVTK'}
SOLVERS={'rhoSimpleFoam','rhoPimpleFoam','simpleFoam'}
TERMINAL={'completed','failed','cancelled','interrupted'}
ID=re.compile(r'^[a-z][a-z0-9-]{0,63}$')
TOKEN=re.compile(r'\{\{([A-Z][A-Z0-9_]*)\}\}')
NUM=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
RESIDUAL=re.compile(r'Solving for (\w+), Initial residual = ('+NUM+r'), Final residual = ('+NUM+r')')

def atomic(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)

def parse_residuals(log):
    iteration=0.;rows=[]
    for line in log.splitlines():
        m=re.match(r'^Time = ('+NUM+r')\s*$',line)
        if m:iteration=float(m[1])
        m=RESIDUAL.search(line)
        if m:
            a,b=float(m[2]),float(m[3])
            if all(math.isfinite(v) for v in [iteration,a,b]):rows.append({'iteration':iteration,'field':m[1],'initial':a,'final':b})
    return rows[-4000:]

def load_template(folder):
    folder=pathlib.Path(folder).resolve();m=json.loads((folder/'aeroblade-template.json').read_text(encoding='utf-8'))
    if not ID.fullmatch(m.get('id','')):raise ValueError('Invalid template id')
    if m.get('solver') not in SOLVERS:raise ValueError('Unsupported solver')
    for path in folder.rglob('*'):
        if path.is_symlink():raise ValueError('Template symlinks are not allowed')
    for required in ['0','constant','system','system/controlDict']:
        if not (folder/required).exists():raise ValueError('Missing '+required)
    if (folder/'constant/polyMesh').exists():raise ValueError('Use a mesh-generation template, not a stale volume mesh')
    geometry=m.get('geometry_file','')
    if not re.fullmatch(r'constant/triSurface/[A-Za-z0-9_-]+\.stl',geometry):raise ValueError('Invalid geometry_file')
    bounds=m.get('geometry_bounds_m')
    if not isinstance(bounds,list) or len(bounds)!=2 or any(not isinstance(v,list) or len(v)!=3 for v in bounds):raise ValueError('geometry_bounds_m must be two SI coordinate vectors')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in bounds[0]+bounds[1]) or any(bounds[0][i]>=bounds[1][i] for i in range(3)):raise ValueError('Invalid geometry envelope')
    inputs=m.get('inputs',[])
    if not isinstance(inputs,list) or not 1<=len(inputs)<=24:raise ValueError('Require 1–24 numeric inputs')
    keys=set();tokens=set()
    for inp in inputs:
        if not re.fullmatch(r'[a-z][a-zA-Z0-9_]{0,40}',inp.get('key','')) or inp['key'] in keys:raise ValueError('Invalid input key')
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,50}',inp.get('token','')) or inp['token'] in tokens:raise ValueError('Invalid input token')
        if any(type(inp.get(k)) not in (int,float) or not math.isfinite(inp[k]) for k in ['min','max','default']):raise ValueError('Invalid numeric range')
        if not inp['min']<=inp['default']<=inp['max']:raise ValueError('Default outside range')
        keys.add(inp['key']);tokens.add(inp['token'])
    for con in m.get('constraints',[]):
        if con.get('op') not in ('>','>=','<','<=') or con.get('left') not in keys or con.get('right') not in keys:raise ValueError('Invalid numeric constraint')
    pipeline=m.get('pipeline',[])
    if not 3<=len(pipeline)<=12:raise ValueError('Invalid pipeline length')
    allowed_flags={'extrudeMesh':set(),'createPatch':{'-overwrite'},'blockMesh':set(),'surfaceFeatureExtract':set(),'snappyHexMesh':{'-overwrite'},'checkMesh':{'-allTopology','-allGeometry','-meshQuality'},'rhoSimpleFoam':set(),'rhoPimpleFoam':set(),'simpleFoam':set(),'foamToVTK':{'-latestTime','-ascii'}}
    for args in pipeline:
        if not isinstance(args,list) or not args or args[0] not in COMMANDS or any(a not in allowed_flags[args[0]] for a in args[1:]):raise ValueError('Disallowed pipeline command or argument')
    names=[x[0] for x in pipeline]
    if names.count(m['solver'])!=1 or any(x in SOLVERS and x!=m['solver'] for x in names):raise ValueError('Pipeline solver mismatch')
    if any(x not in names for x in ['blockMesh','snappyHexMesh','checkMesh']):raise ValueError('Require blockMesh, snappyHexMesh and checkMesh')
    if not names.index('blockMesh')<names.index('snappyHexMesh')<names.index('checkMesh')<names.index(m['solver']):raise ValueError('Mesh must be generated and checked before solving')
    if 'extrudeMesh' in names and ('createPatch' not in names or names.index('createPatch')<names.index('extrudeMesh')):raise ValueError('Extrusion requires periodic reconstruction before checking')
    for command in ('extrudeMesh','createPatch'):
        if command in names and not names.index('snappyHexMesh')<names.index(command)<names.index('checkMesh'):raise ValueError('All mesh changes must precede checkMesh')
    bounds=m.get('parameter_bounds',{})
    if not isinstance(bounds,dict):raise ValueError('Invalid parameter bounds')
    for key,limits in bounds.items():
        if key not in {'chord','thickness','position','inlet','outlet','stagger','height','taper','twist','sweep','lean','radius','bladeCount','axialChord','tangentialChord','throat','leadingRadius','trailingRadius','inletAngle','outletAngle','inletHalfWedge','unguidedTurning'} or not isinstance(limits,list) or len(limits)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in limits) or limits[0]>limits[1]:raise ValueError('Invalid parameter bounds')
    if 'recommended_parameters' in m:validate_template_design(m,m['recommended_parameters'])
    m['_path']=str(folder)
    return m

def validate_conditions(tpl,conditions):
    if not isinstance(conditions,dict) or set(conditions)!={i['key'] for i in tpl['inputs']}:raise ValueError('工况字段必须与选定模板完全一致')
    for i in tpl['inputs']:
        v=conditions[i['key']]
        if type(v) not in (int,float) or not math.isfinite(v) or not i['min']<=v<=i['max'] or (i.get('integer') and int(v)!=v):raise ValueError('工况超出模板范围: '+i['key'])
    for c in tpl.get('constraints',[]):
        a,b=conditions[c['left']],conditions[c['right']]
        if not {'>':a>b,'>=':a>=b,'<':a<b,'<=':a<=b}[c['op']]:raise ValueError('工况约束不满足: '+c['left']+' '+c['op']+' '+c['right'])
    return conditions.copy()

def validate_design(parameters):
    if isinstance(parameters,dict) and parameters.get('model')=='pritchard-1985':
        from pritchard_model import validate_parameters
        return validate_parameters(parameters)
    ranges={'chord':(20,100),'thickness':(8,24),'position':(20,60),'inlet':(10,65),'outlet':(-60,-5),'stagger':(-20,60),'height':(30,160),'taper':(.5,1.3),'twist':(-40,40),'sweep':(-20,20),'lean':(-20,20)}
    if not isinstance(parameters,dict) or set(parameters)!=set(ranges):raise ValueError('叶片参数字段不匹配')
    for k,(lo,hi) in ranges.items():
        v=parameters[k]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('叶片参数超出范围: '+k)
    return parameters.copy()

def prepare_extrusion(case):
    # Preserve matching cyclic points through snappyHexMesh. The OpenCFD
    # extruder requires uncoupled source edges; createPatch reconstructs them.
    path=pathlib.Path(case)/'constant/polyMesh/boundary'
    text,count=re.subn(r'\btype\s+cyclic;', 'type patch;',path.read_text())
    if count!=2:raise ValueError('Planar extrusion requires exactly two cyclic source patches')
    path.write_text(text)

def validate_template_design(tpl,parameters):
    parameters=validate_design(parameters)
    if parameters.get('model','legacy')!=tpl.get('geometry_model','legacy'):
        raise ValueError('几何模型与模板不匹配；Pritchard叶片须选择Pritchard模板')
    for key,(lo,hi) in tpl.get('parameter_bounds',{}).items():
        if not lo<=parameters[key]<=hi:raise ValueError('模板几何约束: '+key+' 必须在 '+str(lo)+'–'+str(hi)+' 范围内；请应用模板推荐叶片')
    return parameters

def prepare_case(tpl,request,case):
    params=validate_template_design(tpl,request.get('parameters'));conditions=validate_conditions(tpl,request.get('conditions'));case=pathlib.Path(case)
    shutil.copytree(tpl['_path'],case)
    mapping={i['token']:format(conditions[i['key']],'.15g') for i in tpl['inputs']}
    if params.get('model')=='pritchard-1985':
        from pritchard_model import mesh_tokens
        mapping.update(mesh_tokens(params))
    used=set()
    for p in case.rglob('*'):
        if not p.is_file() or p.name=='aeroblade-template.json':continue
        try:content=p.read_text()
        except UnicodeDecodeError:continue
        def replace(match):
            key=match[1]
            if key not in mapping:raise ValueError('Unresolved template token: '+key)
            used.add(key);return mapping[key]
        changed=TOKEN.sub(replace,content)
        if changed!=content:p.write_text(changed)
    if used!=set(mapping):raise ValueError('模板参数未用于算例文件: '+', '.join(set(mapping)-used))
    payload={'schema':'aeroblade-cfd-v1','template_id':tpl['id'],'parameters':params,'conditions':conditions,'geometry_units':'m','source_design_units':'mm','geometry_model':params.get('model','legacy')}
    atomic(case/'aeroblade-request.json',payload)
    dst=case/tpl['geometry_file'];dst.parent.mkdir(parents=True,exist_ok=True)
    result=subprocess.run(['node',str(ROOT/'bridge/generate-geometry.mjs'),str(case/'aeroblade-request.json'),str(dst)],capture_output=True,text=True,timeout=45,check=False)
    if result.returncode:raise ValueError('Geometry generation failed: '+result.stderr[-1000:])
    report=json.loads(result.stdout)
    lo,hi=tpl['geometry_bounds_m']
    if any(report['bounds_m'][0][i]<lo[i]-1e-9 or report['bounds_m'][1][i]>hi[i]+1e-9 for i in range(3)):raise ValueError('叶片超出模板允许的几何包络，请更换计算域或叶片参数')
    atomic(case/'aeroblade-geometry.json',report)
    return report

class QueueFullError(ValueError):
    pass

class Manager:
    def __init__(self,jobs,templates,timeout=7200,max_parallel=2,max_pending=16,case_threads=1):
        cpus=os.cpu_count() or 1
        if type(case_threads) is not int or not 1<=case_threads<=cpus:raise ValueError('case_threads must be an integer between 1 and CPU count')
        self.max_parallel_limit=min(8,max(1,cpus//case_threads))
        if type(max_pending) is not int or not 1<=max_pending<=64:raise ValueError('max_pending must be an integer between 1 and 64')
        self.max_parallel_limit=min(self.max_parallel_limit,max_pending)
        if type(max_parallel) is not int or not 1<=max_parallel<=self.max_parallel_limit:raise ValueError('max_parallel must be an integer between 1 and '+str(self.max_parallel_limit))
        self.max_parallel=max_parallel;self.max_pending=max_pending;self.case_threads=case_threads
        self.pending=deque();self.running=set();self.closing=False;self.scheduler_revision=0
        self.root=pathlib.Path(jobs).resolve();self.root.mkdir(parents=True,exist_ok=True);self.templates={};self.template_errors=[];self.timeout=timeout
        self.lock=threading.RLock();self.jobs={};self.submissions={};self.processes={};self.cancelled=set();self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=self.max_parallel_limit);self.condition=threading.Condition(self.lock)
        for path in sorted(pathlib.Path(templates).glob('*/aeroblade-template.json')):
            try:
                tpl=load_template(path.parent)
                if tpl['id'] in self.templates:raise ValueError('Duplicate template id')
                self.templates[tpl['id']]=tpl
            except (ValueError,OSError,KeyError,TypeError) as e:self.template_errors.append(path.parent.name+': '+str(e))
        for path in self.root.glob('*/job.json'):
            try:
                j=json.loads(path.read_text(encoding='utf-8'))
                if j.get('id')!=path.parent.name:continue
                if j.get('status') not in TERMINAL:j.update(status='interrupted',message='服务重启；未完成任务需重新提交',updated_at=time.time());atomic(path,j)
                self.jobs[j['id']]=j
                if j.get('submission_key'):self.submissions[j['submission_key']]=j['id']
            except (ValueError,OSError):pass
    def health(self):
        with self.lock:return self._health()
    def _health(self):
        cmds={c for t in self.templates.values() for stage in t['pipeline'] for c in stage[:1]};missing=sorted(c for c in cmds|{'node'} if not shutil.which(c))
        return {'api':'aeroblade-openfoam-v1','ready':bool(self.templates) and not missing,'openfoam_version':os.environ.get('WM_PROJECT_VERSION','未加载环境'),'missing_commands':missing,'template_errors':self.template_errors,'templates':[{k:v for k,v in t.items() if k not in ('_path','pipeline')} for t in self.templates.values()],**self.scheduler()}
    def scheduler(self):
        with self.lock:
            return {'revision':self.scheduler_revision,'max_parallel':self.max_parallel,'max_parallel_limit':self.max_parallel_limit,
                    'max_pending':self.max_pending,'case_threads':self.case_threads,
                    'running_jobs':len(self.running),'queued_jobs':len(self.pending),
                    'active_jobs':len(self.running)+len(self.pending),'accepting_jobs':not self.closing}
    def configure(self,max_parallel):
        with self.condition:
            if self.closing:raise ValueError('服务正在停止')
            if type(max_parallel) is not int or not 1<=max_parallel<=self.max_parallel_limit:
                raise ValueError('并发数必须为1–'+str(self.max_parallel_limit)+'的整数')
            self.max_parallel=max_parallel;self.scheduler_revision+=1;self.condition.notify_all()
            return self.scheduler()
    def shutdown(self):
        with self.condition:
            self.closing=True
            for id in list(self.jobs):
                if self.jobs[id]['status'] not in TERMINAL:self.cancel(id)
            self.condition.notify_all()
        self.pool.shutdown(wait=True,cancel_futures=True)
    def save(self,j):
        j['updated_at']=time.time();atomic(self.root/j['id']/'job.json',j)
    def get(self,id):
        with self.lock:
            if not re.fullmatch('[0-9a-f]{32}',id) or id not in self.jobs:raise KeyError('Task not found')
            return json.loads(json.dumps(self.jobs[id]))
    def list(self):
        with self.lock:return [self.get(j['id']) for j in sorted(self.jobs.values(),key=lambda j:(j['status'] not in TERMINAL,j.get('created_at',0)),reverse=True)[:100]]
    def find_submission(self,key):
        with self.lock:return self.get(self.submissions[key]) if key in self.submissions else None
    def same_submission(self,payload):
        old=self.find_submission(payload.get('submission_key'))
        if old:
            for key in ('template_id','parameters','conditions','batch_id','batch_case_id'):
                if old.get(key)!=payload.get(key):raise ValueError('幂等键已用于不同的任务快照')
        return old
    def submit(self,payload,*,template_override=None):
        if not isinstance(payload,dict) or payload.get('schema')!='aeroblade-cfd-v1':raise ValueError('请求格式不匹配')
        for key,length in [('submission_key',64),('batch_id',32),('batch_case_id',24)]:
            if key in payload and (not isinstance(payload[key],str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',payload[key])):raise ValueError('批次任务标识无效')
        with self.lock:
            old=self.same_submission(payload)
            if old:return old
        if not self.health()['ready']:raise ValueError('求解服务未就绪：检查 OpenFOAM 环境和算例模板')
        tpl=template_override if template_override is not None else self.templates.get(payload.get('template_id'))
        if not tpl:raise ValueError('Unknown template')
        if tpl['id']!=payload.get('template_id'):raise ValueError('模板快照与请求不匹配')
        name=payload.get('name','')
        if not isinstance(name,str) or len(name)>80:raise ValueError('算例名称必须为80字以内文本')
        request={'name':name.strip(),'parameters':validate_template_design(tpl,payload.get('parameters')),'conditions':validate_conditions(tpl,payload.get('conditions'))}
        with self.lock:
            old=self.same_submission(payload)
            if old:return old
            if self.closing:raise ValueError('服务正在停止')
            if len(self.running)+len(self.pending)>=self.max_pending:raise QueueFullError('队列已满（运行与排队合计最多 '+str(self.max_pending)+' 个），请稍后重试')
            id=uuid.uuid4().hex;folder=self.root/id;folder.mkdir()
            j={'id':id,'name':request['name'],'status':'queued','stage':'queued','template_id':tpl['id'],'solver':tpl['solver'],'created_at':time.time(),'conditions':request['conditions'],'parameters':request['parameters'],'message':'等待可用计算槽位','convergence':'unknown'}
            j.update({k:payload[k] for k in ('submission_key','batch_id','batch_case_id') if k in payload})
            self.jobs[id]=j;atomic(folder/'request.json',request);self.save(j);self.pending.append(id)
            if j.get('submission_key'):self.submissions[j['submission_key']]=id
            try:self.pool.submit(self.run,id,tpl,request)
            except RuntimeError:
                self.pending.remove(id);j.update(status='failed',message='任务调度器已停止',ended_at=time.time());self.save(j);raise ValueError('任务调度器已停止')
            return self.get(id)
    def tail(self,id,limit=500000):
        self.get(id);path=self.root/id/'run.log'
        if not path.exists():return ''
        with path.open('rb') as f:f.seek(max(0,path.stat().st_size-limit));return f.read(limit).decode('utf-8',errors='replace')
    def detail(self,id):
        j=self.get(id);log=self.tail(id);j['log_tail']=log[-24000:];j['residuals']=parse_residuals(log);j['artifact_ready']=(self.root/id/'results.zip').is_file();return j
    def cancel(self,id):
        with self.condition:
            j=self.jobs[self.get(id)['id']]
            if j['status'] in TERMINAL:return self.get(id)
            self.cancelled.add(id)
            if id in self.pending:
                self.pending.remove(id);j.update(status='cancelled',message='排队任务已取消',ended_at=time.time())
            elif id in self.running:
                proc=self.processes.get(id)
                if proc and proc.poll() is None:
                    try:os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                j.update(status='cancelling',message='正在停止该算例，其他任务继续运行')
            else:j.update(status='cancelled',message='任务已取消',ended_at=time.time())
            self.save(j);self.condition.notify_all();return self.get(id)
    def run(self,id,tpl,request):
        j=self.jobs[id];folder=self.root/id;case=folder/'case'
        with self.condition:
            self.condition.wait_for(lambda: id in self.cancelled or self.closing or
                (self.pending and self.pending[0]==id and len(self.running)<self.max_parallel))
            if id in self.cancelled or self.closing:
                if id in self.pending:self.pending.remove(id)
                self.cancelled.discard(id);self.condition.notify_all();return
            self.pending.popleft();self.running.add(id);j['started_at']=time.time()
            self.condition.notify_all()
        started=time.monotonic()
        try:
            with self.lock:
                if id in self.cancelled:raise InterruptedError('任务已取消')
                j.update(status='preparing',stage='geometry',message='生成米制几何并冻结工况');self.save(j)
            report=prepare_case(tpl,request,case)
            with self.lock:j['geometry']=report;self.save(j)
            with (folder/'run.log').open('ab',buffering=0) as log:
                for command in tpl['pipeline']:
                    with self.lock:
                        if id in self.cancelled:raise InterruptedError('任务已取消')
                        j.update(status='running',stage=command[0],message='执行 '+command[0]);self.save(j)
                        log.write(('\n--- '+command[0]+' ---\n').encode())
                        if command[0]=='extrudeMesh':prepare_extrusion(case);log.write(b'Uncoupled two matched source patches for extrusion; createPatch must restore them.\n')
                        proc=subprocess.Popen([*command,'-case',str(case)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=case,env={**os.environ,'PWD':str(case),**{key:str(self.case_threads) for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}})
                        self.processes[id]=proc
                        stage_record={'command':command[0],'pid':proc.pid,'started_at':time.time()}
                        j.setdefault('stage_history',[]).append(stage_record);self.save(j)
                    while proc.poll() is None:
                        if id in self.cancelled or time.monotonic()-started>self.timeout:
                            try:os.killpg(proc.pid,signal.SIGTERM)
                            except ProcessLookupError:pass
                            try:proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                try:os.killpg(proc.pid,signal.SIGKILL)
                                except ProcessLookupError:pass
                                proc.wait()
                            if id in self.cancelled:raise InterruptedError('任务已取消')
                            raise TimeoutError('达到服务端运行时限')
                        time.sleep(.2)
                    with self.lock:
                        stage_record.update(ended_at=time.time(),returncode=proc.returncode);self.save(j)
                    if id in self.cancelled:raise InterruptedError('任务已取消')
                    if proc.returncode:raise RuntimeError(command[0]+' exited with code '+str(proc.returncode))
                    if command[0]=='checkMesh':
                        text=self.tail(id,2000000)
                        part=text.rsplit('--- checkMesh ---',1)[-1]
                        if not re.search(r'\bMesh OK\.',part) or re.search(r'Failed\s+\d+\s+mesh checks',part):raise RuntimeError('checkMesh 未确认 Mesh OK，已阻止求解')
            if id in self.cancelled:raise InterruptedError('任务已取消')
            logtext=self.tail(id,2000000)
            solverpart=logtext.split('--- '+tpl['solver']+' ---',1)[-1].split('\n--- ',1)[0]
            has_end=bool(re.search(r'^End\s*$',solverpart,re.M))
            if not has_end:raise RuntimeError('求解器未输出正常结束标记 End')
            with self.lock:
                j.update(status='packaging',stage='results',message='打包真实算例、日志与场数据');j['convergence']='solver_reported' if re.search(r'\bconverged in\b',solverpart,re.I) else 'not_confirmed';self.save(j)
            total=sum(p.stat().st_size for p in case.rglob('*') if p.is_file() and not p.is_symlink())
            if total>2_000_000_000:raise RuntimeError('结果超过 2 GB 下载限制，请在求解机读取算例目录')
            temporary=folder/'results.tmp'
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                for p in case.rglob('*'):
                    if id in self.cancelled:raise InterruptedError('任务已取消')
                    if p.is_file() and not p.is_symlink():archive.write(p,'case/'+str(p.relative_to(case)))
                archive.write(folder/'run.log','run.log');archive.writestr('summary.json',json.dumps(j,ensure_ascii=False,indent=2))
            with self.lock:
                if id in self.cancelled:raise InterruptedError('任务已取消')
                temporary.replace(folder/'results.zip');j.update(status='completed',stage='completed',message='求解进程已完成；需审核残差、质量守恒与网格独立性');self.save(j)
        except InterruptedError as e:
            with self.lock:j.update(status='cancelled',message=str(e));self.save(j)
        except Exception as e:
            with self.lock:j.update(status='failed',message=str(e)[:1500]);self.save(j)
        finally:
            with self.condition:
                proc=self.processes.pop(id,None)
                if j.get('stage_history') and 'ended_at' not in j['stage_history'][-1]:j['stage_history'][-1].update(ended_at=time.time(),returncode=proc.poll() if proc else None)
                self.running.discard(id);self.cancelled.discard(id)
                j['ended_at']=time.time();self.save(j);self.condition.notify_all()
