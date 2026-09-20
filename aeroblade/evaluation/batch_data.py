"""Deterministic candidate sampling and revalidation of imported parameter bundles."""
import copy,json,pathlib,subprocess,time
from bridge.batch_contract import SCHEMA,TEMPLATE,validate_plan,validate_conditions,validate_parameters
from bridge.optimization import candidate_parameters
from .data import ROOT,digest,write_json

def geometry_many(parameters):
    p=subprocess.run(['node',str(ROOT/'bridge/evaluation-geometry.mjs')],input=json.dumps(parameters),capture_output=True,text=True,encoding='utf-8',timeout=180)
    if p.returncode:raise ValueError('几何校验进程失败：'+p.stderr[-600:])
    return json.loads(p.stdout)

def finish(name,designs,conditions,plan,diagnostics,output=None):
    rows=[{'id':f'g{i+1:04}',**d} for i,d in enumerate(designs)];conditions=[{'id':f'c{i+1:02}',**c} for i,c in enumerate(conditions)]
    content={'schema':SCHEMA,'name':name,'units':{'length':'mm','angle':'deg'},'template_id':TEMPLATE,'plan':plan,'designs':rows,'conditions':conditions,'case_count':len(rows)*len(conditions),'diagnostics':diagnostics}
    content['id']=digest(content)[:24]
    if output:
        target=pathlib.Path(output)/'design-batches'/content['id']/'manifest.json'
        if not target.exists():write_json(target,content)
    return content

def generate(plan,output=None):
    plan=validate_plan(plan);wanted=plan['count'];accepted=[];seen=set();rejected=[];duplicates=0;attempted=0;cap=min(3000,max(20,wanted*10));round_id=0
    while len(accepted)<wanted and attempted<cap:
        n=min(max(2,(wanted-len(accepted))*2),cap-attempted)
        pool=candidate_parameters(plan['baseline'],plan['bounds'],n,plan['seed']+round_id);round_id+=1
        for parameters,geo in zip(pool,geometry_many(pool)):
            attempted+=1
            if 'error' in geo:
                if attempted==1:raise ValueError('基准几何无效：'+geo['error'])
                rejected.append({'attempt':attempted,'parameters':parameters,'reason':geo['error']});continue
            if geo['geometry_hash'] in seen:duplicates+=1;continue
            seen.add(geo['geometry_hash']);accepted.append({'parameters':parameters,**geo})
            if len(accepted)==wanted:break
    diagnostics={'requested':wanted,'accepted':len(accepted),'attempted':attempted,'attempt_limit':cap,'duplicates':duplicates,'rejected':rejected,'shortfall':wanted-len(accepted),'method':'LHS + geometric rejection; filtered points need not retain exact LHS strata'}
    return finish(plan['name'],accepted,plan['conditions'],plan,diagnostics,output)

def import_designs(bundle,output=None):
    if not isinstance(bundle,dict) or bundle.get('schema')!=SCHEMA or bundle.get('units')!={'length':'mm','angle':'deg'} or bundle.get('template_id')!=TEMPLATE:raise ValueError('请导入平台导出的二维批量参数JSON包（mm/deg）')
    name=bundle.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>80:raise ValueError('批次名称无效')
    rows=bundle.get('designs');conditions=validate_conditions(bundle.get('conditions'))
    if not isinstance(rows,list) or not 1<=len(rows)<=300 or len(rows)*len(conditions)>1000:raise ValueError('导入数量超过300几何/1000算例上限')
    parameters=[]
    for r in rows:
        if not isinstance(r,dict) or not isinstance(r.get('parameters'),dict):raise ValueError('缺少完整几何参数')
        parameters.append(validate_parameters(r['parameters']))
    accepted=[];seen=set();duplicates=0
    for i,(p,g) in enumerate(zip(parameters,geometry_many(parameters))):
        if 'error' in g:raise ValueError(f'导入第{i+1}组几何无效：'+g['error'])
        if g['geometry_hash'] in seen:duplicates+=1;continue
        seen.add(g['geometry_hash']);accepted.append({'parameters':p,**g})
    # Compare verified numeric inputs, never the importer's claimed ID or status.
    def identity(designs,conditions):
        params=sorted([json.dumps({k:float(v) if type(v) in (int,float) else v for k,v in d['parameters'].items()},sort_keys=True) for d in designs])
        conds=sorted([json.dumps({k:float(v) for k,v in c.items() if k!='id'},sort_keys=True) for c in conditions])
        return digest([TEMPLATE,params,conds])
    if output:
        target_identity=identity(accepted,conditions)
        for path in sorted((pathlib.Path(output)/'design-batches').glob('*/manifest.json')):
            if path.is_symlink() or path.parent.is_symlink():continue
            existing=json.loads(path.read_text(encoding='utf-8'))
            if existing.get('template_id')!=TEMPLATE or existing.get('units')!={'length':'mm','angle':'deg'}:continue
            if digest({k:v for k,v in existing.items() if k!='id'})[:24]!=existing.get('id') or existing.get('id')!=path.parent.name:continue
            if identity(existing['designs'],existing['conditions'])==target_identity:return existing
    plan={'provenance':{'source':'import-revalidated','original_id':str(bundle.get('id',''))[:80]},'original_plan':bundle.get('plan',{})}
    if len(json.dumps(plan,allow_nan=False))>30000:raise ValueError('导入来源说明过大')
    return finish(name,accepted,conditions,plan,{'requested':len(rows),'accepted':len(accepted),'duplicates':duplicates,'rejected':[],'shortfall':0,'method':'import with full revalidation'},output)
