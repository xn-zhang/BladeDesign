"""Durable batch orchestration over the existing bounded CFD manager."""
import copy,hashlib,json,os,pathlib,re,shutil,threading,time
from core import ROOT,TERMINAL,QueueFullError,load_template
from batch_contract import SCHEMA,TEMPLATE

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8');os.replace(tmp,path)
def safe_child(root,kind,identifier,length):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',identifier):raise ValueError('批次标识无效')
    p=root/kind/identifier
    if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('批次路径无效')
    return p
def tree_digest(folder):
    if folder.is_symlink():raise ValueError('模板不能是符号链接')
    files={}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('模板含符号链接')
        if p.is_file():files[p.relative_to(folder).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return digest(files)

class BatchService:
    def __init__(self,root=None,manager=None,start_pump=True):
        self.root=pathlib.Path(root or ROOT/'ai-data').resolve();self.manager=manager;self.lock=threading.RLock();self.batches={};self.stop=threading.Event();self.thread=None
        for p in (self.root/'batches').glob('*/batch.json'):
            try:
                b=json.loads(p.read_text(encoding='utf-8'))
                if b['id']!=p.parent.name or not re.fullmatch('[a-f0-9]{32}',b['id']):continue
                if b['status'] in ('running','cancelling'):b.update(status='paused',message='服务重启，已停止补充队列；核对任务后继续')
                self.batches[b['id']]=b;self.save(b)
            except (ValueError,OSError,KeyError):continue
        if start_pump:self.thread=threading.Thread(target=self.loop,daemon=True,name='batch-scheduler');self.thread.start()
    def save(self,b):b['updated_at']=time.time();write(self.root/'batches'/b['id']/'batch.json',b)
    def summary(self,b):
        counts={k:sum(c['status']==k for c in b['cases']) for k in sorted({c['status'] for c in b['cases']})}
        return {k:copy.deepcopy(b.get(k)) for k in ('id','name','design_batch_id','status','message','created_at','updated_at','max_in_flight','dataset_ids','template_digest')}|{'counts':counts,'case_count':len(b['cases']),'geometry_count':len(b['manifest']['designs']),'quality_passed':sum(c.get('quality')=='accepted' for c in b['cases'])}
    def list(self):
        with self.lock:return [self.summary(b) for b in sorted(self.batches.values(),key=lambda b:b['created_at'],reverse=True)]
    def designs(self):
        rows=[]
        for path in (self.root/'design-batches').glob('*/manifest.json'):
            if path.is_symlink() or path.parent.is_symlink():continue
            try:
                m=self.design(path.parent.name);rows.append({'id':m['id'],'name':m['name'],'geometry_count':len(m['designs']),'case_count':m['case_count'],'created_at':path.stat().st_mtime})
            except (ValueError,OSError,KeyError):continue
        return sorted(rows,key=lambda r:r['created_at'],reverse=True)
    def design(self,identifier):
        path=safe_child(self.root,'design-batches',identifier,24)/'manifest.json'
        if not path.is_file() or path.is_symlink():raise ValueError('参数包不存在，请先生成或导入并校验')
        m=json.loads(path.read_text(encoding='utf-8'))
        if m.get('id')!=identifier or digest({k:v for k,v in m.items() if k!='id'})[:24]!=identifier or m.get('schema')!=SCHEMA:raise ValueError('参数包摘要不一致，请重新生成')
        return m
    def get(self,bid):
        with self.lock:
            if bid not in self.batches:raise KeyError(bid)
            b=self.batches[bid];return {**copy.deepcopy(b),**self.summary(b)}
    def create(self,design_batch_id):
        m=self.design(design_batch_id)
        if not m.get('designs'):raise ValueError('没有有效几何')
        bid=digest(['production-batch',design_batch_id])[:32]
        with self.lock:
            if bid in self.batches:return self.get(bid)
            rows=[{'id':digest([d['id'],c['id']])[:24],'geometry_id':d['id'],'condition_id':c['id'],'status':'pending','attempt':0,'jobs':[],'quality':'unknown'} for d in m['designs'] for c in m['conditions']]
            b={'id':bid,'design_batch_id':design_batch_id,'name':m['name'],'manifest':m,'cases':rows,'status':'ready','message':'参数已校验；等待启动CFD批次','created_at':time.time(),'max_in_flight':2,'dataset_ids':[]}
            self.batches[bid]=b;self.save(b);return self.get(bid)
    def template(self,b):
        target=self.root/'batches'/b['id']/'template'
        if not target.exists():
            original=self.manager.templates.get(TEMPLATE)
            if not original:raise ValueError('计算服务未安装二维Pritchard模板')
            source=pathlib.Path(original['_path']);before=tree_digest(source);stage=target.with_name('template-staging-'+os.urandom(4).hex())
            shutil.copytree(source,stage)
            if tree_digest(stage)!=before or tree_digest(source)!=before:raise ValueError('复制期间模板发生变化，请重新启动批次')
            os.replace(stage,target);b['template_digest']=before
        actual=tree_digest(target)
        if b.get('template_digest') and actual!=b['template_digest']:raise ValueError('批次模板快照被修改，不能继续混合计算')
        b['template_digest']=actual
        return load_template(target)
    def control(self,bid,action,data):
        if not isinstance(data,dict):raise ValueError('控制参数须为对象')
        with self.lock:
            if bid not in self.batches:raise KeyError(bid)
            b=self.batches[bid]
            if action in ('start','resume'):
                if set(data)-{'max_in_flight'}:raise ValueError('控制字段无效')
                if b['status']=='running':return self.get(bid)
                if b['status']=='cancelling':raise ValueError('请等待取消结束')
                limit=data.get('max_in_flight',b['max_in_flight'])
                if type(limit)!=int or not 1<=limit<=8:raise ValueError('批次在途上限须为1–8')
                if not self.manager or not self.manager.health().get('ready'):raise ValueError('需要同源完整OpenFOAM后端；当前可保存参数包，不能启动真实CFD')
                self.reconcile(b)
                if not any(c['status'] in ('pending','submitting') for c in b['cases']):raise ValueError('没有待提交算例；失败项需先选择重试')
                self.template(b);b.update(status='running',max_in_flight=limit,message='正在补充CFD队列')
            elif action=='pause':
                if data:raise ValueError('暂停不接受附加字段')
                if b['status']=='running':b.update(status='paused',message='已暂停新增提交；已有CFD任务继续运行')
            elif action=='cancel':
                if data:raise ValueError('取消不接受附加字段')
                self.reconcile(b)
                for c in b['cases']:
                    if c['status'] in ('pending','submitting') and not c.get('job_id'):c['status']='cancelled'
                    elif c['status'] not in TERMINAL|{'unknown'} and c.get('job_id') and self.manager:
                        try:self.manager.cancel(c['job_id'])
                        except KeyError:c.update(status='unknown',error='任务记录缺失；已跳过取消，需人工核对')
                b.update(status='cancelling',message='正在取消本批次；其他任务不受影响')
            elif action=='retry':
                if set(data)!={'case_ids'} or not isinstance(data['case_ids'],list) or not data['case_ids']:raise ValueError('请选择需要重试的失败或质检拒收项')
                if b['status'] in ('running','cancelling'):raise ValueError('先暂停批次并等待所选任务结束')
                wanted=set(data['case_ids']);selected=[c for c in b['cases'] if c['id'] in wanted]
                if len(selected)!=len(wanted) or any(c['status'] not in ('failed','cancelled','interrupted','unknown') and not(c['status']=='completed' and c.get('quality')=='rejected') for c in selected):raise ValueError('只能重试失败、取消、中断或质检拒收的已结束算例')
                for c in selected:
                    c.update(status='pending',attempt=c['attempt']+1,quality='unknown');c.pop('job_id',None);c.pop('submission_key',None);c.pop('error',None)
                b.update(status='paused',message='已准备所选重试项；点击继续提交')
            else:raise ValueError('未知批次操作')
            self.save(b);return self.get(bid)
    def reconcile(self,b):
        if not self.manager:return
        for c in b['cases']:
            if c['status'] in TERMINAL or c['status']=='unknown':continue
            if not c.get('job_id') and c.get('submission_key'):
                j=self.manager.find_submission(c['submission_key'])
                if j:c['job_id']=j['id'];c['jobs'].append(j['id']) if j['id'] not in c['jobs'] else None
            if c.get('job_id'):
                try:
                    j=self.manager.get(c['job_id']);c['status']=j['status'];c['error']=j.get('message','')
                except KeyError:c.update(status='unknown',error='任务记录缺失，请核对后选择重试')
    def tick(self):
        with self.lock:
            for b in self.batches.values():
                if b['status'] not in ('running','paused','cancelling'):continue
                self.reconcile(b)
                if b['status']=='running':
                    try:
                        tpl=self.template(b);active=sum(bool(c.get('job_id')) and c['status'] not in TERMINAL|{'unknown'} for c in b['cases'])
                        for c in b['cases']:
                            if active>=b['max_in_flight']:break
                            if c['status'] not in ('pending','submitting'):continue
                            d=next(d for d in b['manifest']['designs'] if d['id']==c['geometry_id']);cond=next(v for v in b['manifest']['conditions'] if v['id']==c['condition_id'])
                            key=digest([b['id'],c['id'],c['attempt']]);c.update(status='submitting',submission_key=key);self.save(b)
                            payload={'schema':'aeroblade-cfd-v1','name':f"{b['name'][:50]} {c['geometry_id']}/{c['condition_id']}",'template_id':TEMPLATE,'parameters':d['parameters'],'conditions':{k:v for k,v in cond.items() if k!='id'},'submission_key':key,'batch_id':b['id'],'batch_case_id':c['id']}
                            try:j=self.manager.submit(payload,template_override=tpl)
                            except QueueFullError:b['message']='CFD队列已满，等待空位后继续';break
                            except ValueError as e:c.update(status='failed',error=str(e));continue
                            except Exception as e:b.update(status='paused',message='提交响应未确认；核对幂等键后继续：'+str(e)[:300]);break
                            c.update(job_id=j['id'],status=j['status']);c['jobs'].append(j['id']) if j['id'] not in c['jobs'] else None;active+=1;self.save(b)
                    except Exception as e:b.update(status='paused',message=str(e)[:1000])
                if all(c['status'] in TERMINAL|{'unknown'} for c in b['cases']) and b['status'] in ('running','cancelling'):
                    b.update(status='cancelled' if b['status']=='cancelling' else 'completed',message='批次调度结束；CFD完成不等于质量通过，请构建数据集进行检查')
                self.save(b)
    def selection(self,bid,allow_partial=False):
        if type(allow_partial)!=bool:raise ValueError('allow_partial须为布尔值')
        with self.lock:
            b=self.batches.get(bid)
            if b is None:raise KeyError(bid)
            self.reconcile(b)
            if not allow_partial and any(c['status'] not in TERMINAL|{'unknown'} for c in b['cases']):raise ValueError('批次尚未结束；如需阶段数据，请明确启用部分结果')
            rows=[{k:c[k] for k in ('id','geometry_id','condition_id','status','attempt','job_id') if k in c} for c in b['cases']];submitted=[c for c in rows if c.get('job_id') and (not allow_partial or c['status'] in TERMINAL)]
            if not submitted:raise ValueError('本批次没有可检查的CFD任务')
            return {'batch_id':bid,'batch_name':b['name'],'design_batch_id':b['design_batch_id'],'template_digest':b.get('template_digest'),'allow_partial':allow_partial,'cases':submitted,'unselected_cases':[c for c in rows if c not in submitted]}
    def attach_dataset(self,bid,result):
        with self.lock:
            b=self.batches[bid];reports={r['job_id']:('accepted',r.get('sample_id')) for r in result['accepted']};reports.update({r['job_id']:('rejected',r['reason']) for r in result['rejected']})
            for c in b['cases']:
                if c.get('job_id') in reports:c['quality'],c['quality_detail']=reports[c['job_id']]
            if result['dataset_id'] not in b['dataset_ids']:b['dataset_ids'].append(result['dataset_id'])
            self.save(b)
    def loop(self):
        while not self.stop.wait(.5):
            try:self.tick()
            except Exception:
                # Keep the pump alive; individual batch errors are persisted by tick.
                continue
    def shutdown(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=5)
        with self.lock:
            for b in self.batches.values():
                if b['status']=='running':b.update(status='paused',message='服务停止；重新启动后手动继续');self.save(b)
