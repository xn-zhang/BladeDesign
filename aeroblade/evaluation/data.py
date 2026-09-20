"""Immutable scalar datasets and read-only CFD evidence extraction."""
import hashlib,json,pathlib,re,subprocess,tempfile,os,time
import numpy as np
from .foam import load_case,safe_tree
from .metrics import extract,METRICS,VERSION
from bridge.validate_result import audit

ROOT=pathlib.Path(__file__).resolve().parents[1]
REQUIRED=('completed','mesh_quality_passed','solver_end','solver_reported_convergence','residuals_below_1e_minus5',
          'mass_balance_below_01_percent','fields_finite','pressure_temperature_positive','periodic_pair_valid','planar_velocity_valid')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def write_json(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+os.urandom(4).hex()+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');os.replace(tmp,path)
def geometry(parameters):
    result=subprocess.run(['node',str(ROOT/'bridge/evaluation-geometry.mjs')],input=json.dumps(parameters),text=True,encoding='utf-8',capture_output=True,timeout=30)
    if result.returncode:raise ValueError('几何不可行：'+result.stderr[-600:])
    return json.loads(result.stdout)
def physical(conditions):
    out={k:conditions[k] for k in ('inletTotalPressure','inletTotalTemperature','outletStaticPressure')}
    if any(type(v) not in (int,float) or not np.isfinite(v) or v<=0 for v in out.values()) or out['inletTotalPressure']<=out['outletStaticPressure']:raise ValueError('物理工况无效')
    return out
def classify(checks):
    reasons=[key for key in REQUIRED if checks.get(key) is not True]
    return {'tier':'rejected' if reasons else 'workflow','reasons':reasons}
def snapshot_hashes(folder):
    paths=[folder/'job.json',folder/'run.log',folder/'request.json']
    paths += [p for area in ('constant','system','0') for p in (folder/'case'/area).rglob('*') if p.is_file() and p.suffix not in ('.stl','.gz')]
    paths += [p for p in (folder/'case').glob('*/*') if p.is_file() and p.name in ('p','U','T','phi','k','omega')]
    if (folder/'strict-checkMesh.log').exists():paths.append(folder/'strict-checkMesh.log')
    for p in paths:
        if p.is_symlink() or not p.resolve().is_relative_to(folder.resolve()):raise ValueError('源文件路径不可信')
    return {str(p.relative_to(folder)).replace('\\','/'):file_hash(p) for p in sorted(set(paths))}

def verify_request(folder,job):
    request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
    if request.get('parameters')!=job.get('parameters') or request.get('conditions')!=job.get('conditions'):raise ValueError('job与原始提交快照不一致')
def evaluate_job(folder):
    folder=pathlib.Path(folder)
    if folder.is_symlink() or (folder/'case').is_symlink():raise ValueError('不读取符号链接任务')
    j=json.loads((folder/'job.json').read_text(encoding='utf-8'))
    if j.get('template_id')!='pritchard-cascade-2d' or j.get('parameters',{}).get('model')!='pritchard-1985':raise ValueError('仅支持二维Pritchard叶栅模板')
    if j.get('status')!='completed':raise ValueError('CFD任务未完成')
    safe_tree(folder/'case');verify_request(folder,j)
    before=snapshot_hashes(folder);report=audit(folder,write=False);quality=classify(report['checks'])
    if quality['reasons']:raise ValueError('CFD质量未通过：'+', '.join(quality['reasons']))
    case=load_case(folder/'case')
    from bridge.flow import field
    for name,dim in [('k',(0,2,-2,0,0,0,0)),('omega',(0,0,-1,0,0,0,0))]:
        arr,units=field(folder/'case'/case['time']/name,case['mesh']['cell_count'],1)
        if units!=dim or min(arr)<0:raise ValueError('湍流场单位、长度或数值无效：'+name)
    if float(case['time'])!=float(report['last_solved_iteration']):raise ValueError('写入场时间与最后求解迭代不一致')
    params=j['parameters'];conditions=physical(j['conditions']);geo=geometry(params)
    result=extract(case['patches'],case['mesh']['span'],params['axialChord']*.001,conditions,case['thermo'])
    if not result['valid']:raise ValueError('六项指标不完整')
    if result['relative_mass_imbalance']>=.001:raise ValueError('重构质量不平衡超过0.1%')
    if result['phi_reconstruction_relative_error'] is None or result['phi_reconstruction_relative_error']>=.001:raise ValueError('phi与重构质量通量差异超过0.1%')
    if case['periodic_flux_error']>=.001:raise ValueError('周期通量配对误差超过0.1%')
    after=snapshot_hashes(folder)
    if before!=after:raise ValueError('读取期间CFD源文件发生变化')
    template=folder/'case/aeroblade-template.json'
    if not template.is_file():raise ValueError('缺少算例模板合同')
    template_parts={'contract':file_hash(template)}
    for name in ('fvSchemes','fvSolution'):
        p=folder/'case/system'/name
        if p.exists():template_parts[name]=file_hash(p)
    for relative in ('constant/turbulenceProperties','constant/thermophysicalProperties','0/k','0/omega'):
        p=folder/'case'/relative
        if not p.is_file():raise ValueError('缺少模板物理设置：'+relative)
        template_parts[relative]=file_hash(p)
    mesh_hash=digest({k:v for k,v in before.items() if 'polyMesh/' in k})
    record={'job_id':j['id'],'parameters':params,'conditions':conditions,'thermo':case['thermo'],**geo,
      'condition_hash':digest(conditions),'mesh_hash':mesh_hash,'template_hash':digest(template_parts),'template_id':j['template_id'],
      'thermo_hash':digest(case['thermo']),'source_hash':digest(before),'source_files':before,'time':case['time'],
      'quality':quality['tier'],'strict_geometry':report.get('strict_geometry_diagnostic',{'passed':None}),
      'metrics':result,'audit':report,'actual_span_m':case['mesh']['span'],'cell_count':case['mesh']['cell_count'],
      'created_at':j.get('ended_at',j.get('updated_at',0)),'source':'OpenFOAM'}
    record['sample_id']=digest({k:record[k] for k in ('job_id','source_hash','geometry_hash','condition_hash','template_hash')})[:24]
    record['duplicate_group']=digest([geo['geometry_hash'],record['condition_hash'],record['template_hash'],record['thermo_hash']])
    evidence={'volumes':case['mesh']['volumes'],**{'internal_'+k:v for k,v in case['internal'].items()}}
    for name,patch in case['patches'].items():
        for key,array in patch.items():evidence[name+'_'+key]=array
    return record,evidence

def export_dataset(jobs,output,selection=None):
    jobs=pathlib.Path(jobs);output=pathlib.Path(output);accepted=[];rejected=[];arrays={}
    selected={c['job_id']:c for c in selection['cases']} if selection is not None else None
    if selected is not None and any(not re.fullmatch('[a-f0-9]{32}',key) for key in selected):raise ValueError('批次任务标识无效')
    paths=[jobs/key/'job.json' for key in sorted(selected)] if selected is not None else sorted(jobs.glob('*/job.json'))
    for path in paths:
        job_id=path.parent.name
        if not re.fullmatch('[a-f0-9]{32}',job_id):continue
        try:
            record,evidence=evaluate_job(path.parent);accepted.append(record);arrays[record['sample_id']]=evidence
            if selection is not None:record.update(batch_id=selection['batch_id'],batch_case_id=selected[job_id]['id'],geometry_id=selected[job_id]['geometry_id'],condition_id=selected[job_id]['condition_id'])
        except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.SubprocessError) as exc:
            rejected.append({'job_id':job_id,'reason':str(exc)[:1200]})
    chosen={}
    for record in sorted(accepted,key=lambda r:(r['created_at'],r['sample_id'])):chosen[record['duplicate_group']]=record['sample_id']
    for record in accepted:record['training_eligible']=chosen[record['duplicate_group']]==record['sample_id']
    identity={'accepted':accepted,'rejected':rejected,'metric_version':VERSION}
    if selection is not None:identity['selection']=selection
    dataset_id=digest(identity)[:24]
    manifest={'schema':'aeroblade-evaluation-dataset-v1','dataset_id':dataset_id,'created_at':time.time(),'metric_version':VERSION,'metrics':list(METRICS),
      'accepted':accepted,'rejected':rejected,'summary':{'accepted':len(accepted),'rejected':len(rejected),'training_samples':sum(r['training_eligible'] for r in accepted),'geometry_groups':len({r['geometry_group'] for r in accepted}),'engineering_samples':0}}
    if selection is not None:manifest['selection']=selection
    target=output/'datasets'/dataset_id
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.dataset-',dir=target.parent) as temp:
            stage=pathlib.Path(temp);(stage/'samples').mkdir()
            for sid,data in arrays.items():np.savez_compressed(stage/'samples'/(sid+'.npz'),**data)
            for r in accepted:r['evidence_hash']=file_hash(stage/'samples'/(r['sample_id']+'.npz'))
            write_json(stage/'manifest.json',manifest)
            os.rename(stage,target)
    return json.loads((target/'manifest.json').read_text(encoding='utf-8'))
