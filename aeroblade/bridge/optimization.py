"""Budgeted, sequential CFD search; surrogate predictions never count as verification."""
import copy,math,random,time

PARAMETERS=('radius','bladeCount','axialChord','tangentialChord','throat','leadingRadius','trailingRadius','inletAngle','outletAngle','inletHalfWedge','unguidedTurning')
METRICS=('loss_coefficient','outlet_angle_deg','turning_angle_deg','mass_flow_per_span','pressure_force_x_coefficient','pressure_force_y_coefficient')

def number(v):return type(v) in (int,float) and math.isfinite(v)

def validate_config(c):
    if c.get('mode') not in ('cfd','surrogate'):raise ValueError('优化模式无效')
    if type(c.get('budget'))!=int or not 2<=c['budget']<=30:raise ValueError('CFD预算须为2–30次')
    if type(c.get('seed',42))!=int or not 0<=c.get('seed',42)<2**31:raise ValueError('随机种子无效')
    bounds=c.get('bounds');params=c.get('parameters')
    if not isinstance(params,dict) or not isinstance(bounds,dict) or not 1<=len(bounds)<=6:raise ValueError('请选择1–6个设计变量')
    for k,b in bounds.items():
        if k not in PARAMETERS or not isinstance(b,list) or len(b)!=2 or not all(number(v) for v in b) or b[0]>=b[1] or not number(params.get(k)) or not b[0]<=params[k]<=b[1]:raise ValueError('设计范围必须包含基准值：'+k)
        if k=='bladeCount' and (b[0]!=int(b[0]) or b[1]!=int(b[1])):raise ValueError('叶片数边界必须为整数')
    objectives=c.get('objectives');constraints=c.get('constraints',[])
    if not isinstance(objectives,list) or not 1<=len(objectives)<=2 or len({o.get('metric') for o in objectives})!=len(objectives):raise ValueError('请选择1–2个不同目标')
    for o in objectives:
        if o.get('metric') not in METRICS or o.get('direction') not in ('min','max'):raise ValueError('目标无效')
    if not isinstance(constraints,list) or len(constraints)>6:raise ValueError('最多6个约束')
    for v in constraints:
        if v.get('metric') not in METRICS or v.get('op') not in ('<=','>=') or not number(v.get('value')):raise ValueError('约束无效')
    return c

def candidate_parameters(base,bounds,count,seed):
    rng=random.Random(seed);rows=[copy.deepcopy(base) for _ in range(count)];n=count-1
    for k,(lo,hi) in bounds.items():
        strata=list(range(n));rng.shuffle(strata)
        for i,s in enumerate(strata,1):
            value=lo+(hi-lo)*(s+rng.random())/n;rows[i][k]=int(round(value)) if k=='bladeCount' else value
    return rows

def feasible(values,constraints):return all(values[c['metric']]<=c['value'] if c['op']=='<=' else values[c['metric']]>=c['value'] for c in constraints)
def score(values,objectives):return tuple(values[o['metric']]*(1 if o['direction']=='min' else -1) for o in objectives)

def rank_candidates(rows,cfg):
    eligible=[]
    for row in rows:
        row['pareto']=False;row['feasible']=row.get('status')=='verified' and feasible(row['values'],cfg.get('constraints',[]))
        if row['feasible']:eligible.append(row)
    for row in eligible:
        s=score(row['values'],cfg['objectives'])
        row['pareto']=not any(all(a<=b for a,b in zip(score(other['values'],cfg['objectives']),s)) and any(a<b for a,b in zip(score(other['values'],cfg['objectives']),s)) for other in eligible if other is not row)
    return sorted(eligible,key=lambda r:score(r['values'],cfg['objectives']))

def run_search(cfg,compute,manager,checkpoint,publish):
    validate_config(cfg);rows=[];history=[];submitted=0;best=[];seed=cfg.get('seed',42);seen=set();context=None
    def context_of(record):
        return (record.get('template_hash'),record.get('thermo_hash'),record.get('condition_hash'),record.get('metric_version',record.get('metrics',{}).get('version')))
    def add(parameters,stage):
        key=tuple(sorted(parameters.items()))
        if key in seen:return None
        seen.add(key);r={'index':len(rows),'parameters':parameters,'status':'pending','stage':stage};rows.append(r)
        try:compute('geometry',{'parameters':parameters});r['status']='ready'
        except ValueError as e:r.update(status='invalid',error=str(e))
        return r
    def report():
        ordered=rank_candidates(rows,cfg);publish({'candidates':copy.deepcopy(rows),'history':copy.deepcopy(history),'submitted':submitted,'budget':cfg['budget'],'comparison_context':context,'best_index':ordered[0]['index'] if ordered else None,'pareto_indices':[r['index'] for r in ordered if r['pareto']]})
        return ordered
    for p in candidate_parameters(cfg['parameters'],cfg['bounds'],min(80,cfg['budget']*4) if cfg['mode']=='surrogate' else cfg['budget'],seed):
        checkpoint();add(p,'DOE')
    pending=[r for r in rows if r['status']=='ready']
    def screen(candidates):
        if cfg['mode']!='surrogate':return candidates
        checkpoint();result=compute('predict_batch',{'model_id':cfg['model_id'],'parameters':[r['parameters'] for r in candidates],'conditions':cfg['conditions']})
        good=[]
        for r,pred in zip(candidates,result):
            if 'error' in pred:r.update(status='prediction_failed',error=pred['error']);continue
            if context_of(pred)!=context:raise RuntimeError('代理模型与基准CFD的模板、热物性、工况或指标版本不一致；请重新训练模型或使用直接CFD模式')
            r['prediction']=pred
            if not pred['domain']['in_domain']:r.update(status='outside_domain');continue
            good.append(r)
        # Feasible surrogate predictions first; real CFD still decides acceptance.
        return sorted(good,key=lambda r:(not feasible(r['prediction']['values'],cfg.get('constraints',[])),score(r['prediction']['values'],cfg['objectives'])))
    baseline=rows[0] if rows and rows[0]['status']=='ready' else None
    if baseline is None:raise ValueError('基准几何无效，请先修正初始设计')
    pending=[baseline]+[r for r in pending if r is not baseline];report()
    while submitted<cfg['budget'] and pending:
        checkpoint();r=pending.pop(0)
        # After exploration, refine around the best feasible CFD result within frozen bounds.
        if best and submitted>=max(2,cfg['budget']//2):
            center=best[0]['parameters'];fraction=.3/(1+submitted-cfg['budget']//2)
            local={k:[max(b[0],center[k]-(b[1]-b[0])*fraction),min(b[1],center[k]+(b[1]-b[0])*fraction)] for k,b in cfg['bounds'].items()}
            proposals=[]
            for p in candidate_parameters(center,local,4,seed+submitted):
                checkpoint();new=add(p,'refinement')
                if new and new['status']=='ready':proposals.append(new)
            proposals=screen(proposals)
            if proposals:pending.insert(0,r);r=proposals[0]
        checkpoint()
        request={'schema':'aeroblade-cfd-v1','name':'优化候选 '+str(r['index']+1),'template_id':'pritchard-cascade-2d','geometry_model':'pritchard-1985','parameters':r['parameters'],'conditions':cfg['conditions'],'design_units':'mm','geometry_export_units':'m'}
        submitted+=1
        try:
            job=manager.submit(request);r.update(status='running',job_id=job['id']);report()
            while True:
                checkpoint(job['id'],True);job=manager.get(job['id'])
                if job['status'] in ('completed','failed','cancelled','interrupted'):break
                time.sleep(.25)
            if job['status']!='completed':raise ValueError('CFD '+job['status']+': '+job.get('message',''))
            checkpoint(job['id'],True);evidence=compute('analyze',{'job_id':job['id']});current=context_of(evidence)
            if any(v is None for v in current):raise ValueError('CFD比较上下文缺失')
            if context is not None and current!=context:raise ValueError('CFD模板、热物性、工况或指标版本偏离基准；不参与排名')
            if context is None:context=current
            r.update(status='verified',values=evidence['metrics']['values'],evidence=evidence,quality=evidence['quality'],source='OpenFOAM')
            if r.get('prediction'):r['prediction_comparable']=True
        except ValueError as e:r.update(status='rejected',error=str(e))
        best=rank_candidates(rows,cfg);history.append({'evaluation':submitted,'candidate_index':r['index'],'best':best[0]['values'][cfg['objectives'][0]['metric']] if best else None});report()
        if r is baseline:
            if r['status']!='verified':raise RuntimeError('基准CFD未通过质量门槛；请先获得有效基准再开始优化')
            if cfg['mode']=='surrogate':
                checkpoint();prediction=compute('predict_batch',{'model_id':cfg['model_id'],'parameters':[baseline['parameters']],'conditions':cfg['conditions']})[0]
                if 'error' in prediction:raise RuntimeError('基准代理预测失败：'+prediction['error'])
                if context_of(prediction)!=context:raise RuntimeError('代理模型与基准CFD的模板、热物性、工况或指标版本不一致；请重新训练模型或使用直接CFD模式')
                baseline['prediction']=prediction;baseline['prediction_comparable']=True;pending=screen(pending);report()
    for r in rows:
        if r['status']=='ready':r['status']='not_evaluated'
    report()
