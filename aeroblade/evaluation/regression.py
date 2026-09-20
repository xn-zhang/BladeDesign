"""Grouped scalar regression. Artifacts contain JSON arrays, never executable pickle."""
import json,pathlib,platform,time,uuid
import numpy as np
from .data import geometry,physical,digest,file_hash,write_json,ROOT
from .metrics import METRICS,UNITS,VERSION

ANGLES=('inletAngle','outletAngle','inletHalfWedge','unguidedTurning')
FEATURES=['axial_chord_m','tangential_over_axial','pitch_over_axial','throat_over_pitch','leading_over_axial','trailing_over_axial']+[a+'_'+f for a in ANGLES for f in ('sin','cos')]+['pressure_ratio','inlet_temperature_K','inlet_pressure_Pa','Rgas','gamma','mu','Re_reference']

def features(parameters,conditions,thermo,geo=None):
    p=parameters;c=physical(conditions);g=geo or geometry(p);cx=p['axialChord'];pitch=g['pitch']
    R=thermo['Rgas'];gamma=thermo['gamma'];mu=thermo['mu'];T=c['inletTotalTemperature'];p0=c['inletTotalPressure']
    speed=(2*thermo['Cp']*T*(1-(c['outletStaticPressure']/p0)**((gamma-1)/gamma)))**.5
    row=[cx*.001,p['tangentialChord']/cx,pitch/cx,p['throat']/pitch,p['leadingRadius']/cx,p['trailingRadius']/cx]
    for a in ANGLES:row.extend([np.sin(np.deg2rad(p[a])),np.cos(np.deg2rad(p[a]))])
    row.extend([p0/c['outletStaticPressure'],T,p0,R,gamma,mu,p0/(R*T)*speed*cx*.001/mu])
    if not np.isfinite(row).all():raise ValueError('特征包含非有限值')
    return row

def split_groups(rows,seed):
    groups=sorted({r['geometry_group'] for r in rows});np.random.default_rng(seed).shuffle(groups)
    n=len(groups)
    if n<3:raise ValueError('至少需要3组独立几何才能隔离训练和验证')
    nt=max(1,round(n*.15)) if n>=15 else 0;nv=max(1,round(n*.15))
    selected={'train':set(groups[:n-nt-nv]),'validation':set(groups[n-nt-nv:n-nt]),'test':set(groups[n-nt:]) if nt else set()}
    return {k:[i for i,r in enumerate(rows) if r['geometry_group'] in values] for k,values in selected.items()}

def standardize(x):
    mean=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale<1e-12,1.,scale)
    return mean,scale

def errors(actual,predicted):
    delta=predicted-actual;delta[:,1:3]=(delta[:,1:3]+180)%360-180
    return {k:{'mae':float(np.mean(abs(delta[:,i]))),'rmse':float(np.sqrt(np.mean(delta[:,i]**2))),'unit':UNITS[i]} for i,k in enumerate(METRICS)}

def domain_report(x,training,names,mean,scale):
    x=np.asarray(x);t=np.asarray(training);lo=t.min(axis=0);hi=t.max(axis=0);eps=np.maximum(abs(lo),abs(hi))*1e-7+1e-10
    outside=[name for i,name in enumerate(names) if x[i]<lo[i]-eps[i] or x[i]>hi[i]+eps[i]]
    distance=float(np.min(np.linalg.norm((t-x)/np.asarray(scale),axis=1)))
    return {'in_domain':not outside,'outside_features':outside,'nearest_training_distance':distance,'note':'范围与距离是外推提示，不是经校准的置信区间'}

def infer_arrays(artifact,x):
    x=(np.asarray(x)-artifact['x_mean'])/artifact['x_scale'];weights=artifact['weights'];kind=artifact['algorithm']
    if kind=='ridge':y=x@np.array(weights['coef']).T+weights['intercept']
    elif kind=='extra_trees':
        results=[]
        for tree in weights:
            v=[]
            for row in x:
                i=0
                while tree['left'][i]!=-1:i=tree['left'][i] if row[tree['feature'][i]]<=tree['threshold'][i] else tree['right'][i]
                v.append(tree['value'][i])
            results.append(v)
        y=np.mean(results,axis=0)
    else:
        y=x
        for i,layer in enumerate(weights):
            y=y@np.array(layer['weight']).T+layer['bias']
            if i<len(weights)-1:y=y/(1+np.exp(-np.clip(y,-700,700)))
    y=y*np.array(artifact['y_scale'])+np.array(artifact['y_mean']);y[:,1:3]=(y[:,1:3]+180)%360-180
    return y

def train(manifest,root,algorithm='ridge',seed=42):
    if algorithm not in ('ridge','extra_trees','mlp'):raise ValueError('未知回归算法')
    if type(seed)!=int or not 0<=seed<2**31:raise ValueError('seed超出范围')
    root=pathlib.Path(root);raw=pathlib.Path(manifest).read_bytes();data=json.loads(raw)
    if data['metric_version']!=VERSION:raise ValueError('指标版本不一致，请重新扫描')
    rows=[r for r in data['accepted'] if r['training_eligible']]
    contexts={(r['template_hash'],r['thermo_hash']) for r in rows}
    if len(contexts)!=1:raise ValueError('训练数据必须使用相同模板和热物性；请分开建立数据目录')
    for r in rows:
        evidence=pathlib.Path(manifest).parent/'samples'/(r['sample_id']+'.npz')
        if file_hash(evidence)!=r['evidence_hash']:raise ValueError('数据证据摘要不一致')
    split=split_groups(rows,seed);x=np.array([features(r['parameters'],r['conditions'],r['thermo'],r) for r in rows]);y=np.array([[r['metrics']['values'][k] for k in METRICS] for r in rows]);tr=split['train'];va=split['validation']
    # Unwrap angular targets around training-only circular mean.
    for i in (1,2):
        center=np.rad2deg(np.arctan2(np.sin(np.deg2rad(y[tr,i])).mean(),np.cos(np.deg2rad(y[tr,i])).mean()))
        y[:,i]=center+(y[:,i]-center+180)%360-180
    xm,xs=standardize(x[tr]);ym,ys=standardize(y[tr]);xx=(x-xm)/xs;yy=(y-ym)/ys
    import sklearn
    chosen=None;score=float('inf');hyper={};runtime={'python':platform.python_version(),'numpy':np.__version__,'sklearn':sklearn.__version__}
    if algorithm=='ridge':
        from sklearn.linear_model import Ridge
        for alpha in (.1,1.,10.,100.):
            model=Ridge(alpha=alpha).fit(xx[tr],yy[tr]);s=float(np.mean((model.predict(xx[va])-yy[va])**2))
            if s<score:score=s;chosen={'coef':model.coef_.tolist(),'intercept':model.intercept_.tolist()};hyper={'alpha':alpha}
    elif algorithm=='extra_trees':
        from sklearn.ensemble import ExtraTreesRegressor
        for leaf in (1,2,4):
            model=ExtraTreesRegressor(n_estimators=128,min_samples_leaf=leaf,random_state=seed,n_jobs=1).fit(xx[tr],yy[tr]);s=float(np.mean((model.predict(xx[va])-yy[va])**2))
            if s<score:
                score=s;chosen=[{'left':t.tree_.children_left.tolist(),'right':t.tree_.children_right.tolist(),'feature':t.tree_.feature.tolist(),'threshold':t.tree_.threshold.tolist(),'value':t.tree_.value[:,:,0].tolist()} for t in model.estimators_];hyper={'trees':128,'min_samples_leaf':leaf}
    else:
        import torch
        torch.set_num_threads(1);torch.manual_seed(seed);runtime['torch']=torch.__version__
        net=torch.nn.Sequential(torch.nn.Linear(len(FEATURES),64),torch.nn.SiLU(),torch.nn.Linear(64,64),torch.nn.SiLU(),torch.nn.Linear(64,6));optimizer=torch.optim.Adam(net.parameters(),lr=.003,weight_decay=.0001)
        tx=torch.tensor(xx,dtype=torch.float32);ty=torch.tensor(yy,dtype=torch.float32);stale=0
        for epoch in range(300):
            optimizer.zero_grad();loss=((net(tx[tr])-ty[tr])**2).mean();loss.backward();optimizer.step()
            with torch.no_grad():s=float(((net(tx[va])-ty[va])**2).mean())
            if s<score-1e-8:
                score=s;stale=0;chosen=[{'weight':layer.weight.detach().numpy().tolist(),'bias':layer.bias.detach().numpy().tolist()} for layer in net if isinstance(layer,torch.nn.Linear)];hyper={'hidden':[64,64],'epoch':epoch+1,'early_stop_patience':30}
            else:stale+=1
            if stale>=30:break
    if chosen is None:raise ValueError('训练未产生有限权重')
    artifact={'algorithm':algorithm,'weights':chosen,'x_mean':xm.tolist(),'x_scale':xs.tolist(),'y_mean':ym.tolist(),'y_scale':ys.tolist()}
    predicted=infer_arrays(artifact,x);mid=uuid.uuid4().hex[:24]
    card={'schema':'aeroblade-scalar-model-v1','model_id':mid,'created_at':time.time(),'algorithm':algorithm,'hyperparameters':hyper,'seed':seed,'experimental':len({r['geometry_group'] for r in rows})<15,'dataset_id':data['dataset_id'],'dataset_hash':file_hash(manifest),'metric_version':VERSION,'features':FEATURES,'metrics':list(METRICS),'units':list(UNITS),'template_hash':rows[0]['template_hash'],'thermo_hash':rows[0]['thermo_hash'],'template_id':rows[0]['template_id'],'thermo':rows[0]['thermo'],'runtime':runtime,'code_hash':code_hash(),'split':{k:[rows[i]['sample_id'] for i in ids] for k,ids in split.items()},'split_geometry_groups':{k:sorted({rows[i]['geometry_group'] for i in ids}) for k,ids in split.items()},'scores':{k:errors(y[ids].copy(),predicted[ids]) if ids else None for k,ids in split.items()},'training_features':x[tr].tolist(),'feature_limits':dict(zip(FEATURES,np.stack([x[tr].min(0),x[tr].max(0)],1).tolist())),'reference_parameters':rows[tr[0]]['parameters'],'reference_conditions':rows[tr[0]]['conditions'],'sample_count':len(rows),'geometry_groups':len({r['geometry_group'] for r in rows}),'quality':'workflow'}
    target=root/'models'/mid;write_json(target/'weights.json',artifact);card['weights_hash']=file_hash(target/'weights.json');write_json(target/'card.json',card)
    write_json(target/'integrity.json',{'card_hash':file_hash(target/'card.json')})
    return card

def code_hash():return digest({p.relative_to(ROOT).as_posix():file_hash(p) for p in [ROOT/'evaluation/regression.py',ROOT/'evaluation/metrics.py',ROOT/'evaluation/data.py',ROOT/'evaluation/foam.py',ROOT/'web/geometry.js',ROOT/'web/pritchard.js']})

def predict(model_dir,parameters,conditions):
    model_dir=pathlib.Path(model_dir);card=json.loads((model_dir/'card.json').read_text(encoding='utf-8'));integrity=json.loads((model_dir/'integrity.json').read_text(encoding='utf-8'))
    if file_hash(model_dir/'card.json')!=integrity['card_hash'] or file_hash(model_dir/'weights.json')!=card['weights_hash']:raise ValueError('模型文件摘要不一致')
    if card['code_hash']!=code_hash() or card['metric_version']!=VERSION:raise ValueError('模型计算版本已变更，请重新训练')
    artifact=json.loads((model_dir/'weights.json').read_text(encoding='utf-8'));geo=geometry(parameters);conditions=physical(conditions);x=features(parameters,conditions,card['thermo'],geo)
    result=infer_arrays(artifact,[x])[0]
    return {'source':'AI','model_id':card['model_id'],'experimental':card['experimental'],'parameters':parameters,'conditions':conditions,**geo,'condition_hash':digest(conditions),'template_hash':card['template_hash'],'thermo_hash':card['thermo_hash'],'metric_version':VERSION,'values':dict(zip(METRICS,result.tolist())),'domain':domain_report(x,card['training_features'],FEATURES,artifact['x_mean'],artifact['x_scale']),'model_card_hash':integrity['card_hash']}
