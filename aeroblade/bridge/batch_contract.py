"""Shared, dependency-free contract for cold 2D cascade production batches."""
import copy,math,json
try:from .pritchard_model import RANGES,validate_parameters
except ImportError:from pritchard_model import RANGES,validate_parameters

SCHEMA='aeroblade-design-batch-v1'
TEMPLATE='pritchard-cascade-2d'
CONDITIONS={'inletTotalPressure':(100100,100500),'inletTotalTemperature':(290,310),'outletStaticPressure':(100000,100000),'iterations':(100,5000)}
def finite(v):return type(v) in (int,float) and math.isfinite(v)
def validate_conditions(rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=10:raise ValueError('工况数量须为1–10')
    out=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)-set(CONDITIONS)-{'id'} or set(CONDITIONS)-set(row):raise ValueError('工况字段不完整')
        c={k:row[k] for k in CONDITIONS}
        for k,(lo,hi) in CONDITIONS.items():
            if not finite(c[k]) or not lo<=c[k]<=hi:raise ValueError(f'{k}须在{lo}–{hi}范围内（二维冷态模板）')
        if type(c['iterations'])!=int:raise ValueError('迭代上限须为整数')
        key=tuple(c[k] for k in CONDITIONS if k!='iterations')
        if key in seen:raise ValueError('工况重复；仅改变迭代次数不增加物理工况')
        seen.add(key);out.append(c)
    return out

def validate_plan(plan):
    allowed={'name','baseline','bounds','count','seed','conditions','provenance'}
    if not isinstance(plan,dict) or set(plan)-allowed:raise ValueError('批量方案字段无效')
    p=copy.deepcopy(plan)
    if not isinstance(p.get('name'),str) or not p['name'].strip() or len(p['name'])>80:raise ValueError('批次名称须为1–80字')
    if not isinstance(p.get('baseline'),dict):raise ValueError('缺少基准参数')
    p['baseline']=validate_parameters(p['baseline']);bounds=p.get('bounds')
    if not isinstance(bounds,dict) or not 1<=len(bounds)<=6:raise ValueError('请选择1–6个变化变量')
    for key,b in bounds.items():
        if key not in RANGES or key=='height' or not isinstance(b,list) or len(b)!=2 or not all(finite(v) for v in b):raise ValueError('变量范围无效：'+key)
        lo,hi=RANGES[key]
        if not lo<=b[0]<b[1]<=hi or not b[0]<=p['baseline'][key]<=b[1]:raise ValueError('范围须包含基准值并满足软件边界：'+key)
        if key=='bladeCount' and any(v!=int(v) for v in b):raise ValueError('叶片数上下界须为整数')
    if type(p.get('count'))!=int or not 1<=p['count']<=300:raise ValueError('几何数量须为1–300（含基准）')
    if type(p.get('seed'))!=int or not 0<=p['seed']<2**31:raise ValueError('随机种子须为0–2147483647整数')
    p['conditions']=validate_conditions(p.get('conditions'))
    if p['count']*len(p['conditions'])>1000:raise ValueError('单批最多1000个几何与工况组合')
    provenance=p.get('provenance',{'source':'manual'})
    if not isinstance(provenance,dict) or len(json.dumps(provenance,allow_nan=False))>24000:raise ValueError('来源说明过大或无效')
    p['provenance']=provenance
    return p
