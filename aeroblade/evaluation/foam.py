"""Read-only ASCII OpenFOAM extraction for stationary single-layer XY cascades."""
import pathlib,re
import numpy as np
from scipy.spatial import cKDTree
from bridge.flow import read_ascii,mesh_list,indices,field

def block(text,name):
    match=re.search(r'\b'+re.escape(name)+r'\s*\{',text)
    if not match:raise ValueError('缺少字典块 '+name)
    start=match.end();depth=1
    for i in range(start,len(text)):
        depth+=(text[i]=='{')-(text[i]=='}')
        if depth==0:return text[start:i]
    raise ValueError('字典未闭合 '+name)

def value(text,key,count,components):
    m=re.search(r'\b'+key+r'\s+nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*\((.*?)\)\s*;',text,re.S)
    if m:
        if int(m[2])!=count or (m[1]=='vector')!=(components==3):raise ValueError('边界场长度/类型不匹配')
        values=[float(x) for x in m[3].replace('(',' ').replace(')',' ').split()]
    else:
        m=re.search(r'\b'+key+r'\s+uniform\s+([^;]+);',text)
        if not m:return None
        values=[float(x) for x in m[1].replace('(',' ').replace(')',' ').split()]
        if len(values)!=components:raise ValueError('边界场分量错误')
        values*=count
    a=np.asarray(values,dtype=float)
    if len(a)!=count*components or not np.isfinite(a).all():raise ValueError('边界场数据无效')
    return a.reshape(count,components) if components==3 else a

def safe_tree(root):
    root=pathlib.Path(root)
    if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):raise ValueError('不读取含符号链接的算例')
    return root

def read_mesh(case):
    mesh=case/'constant'/'polyMesh';n,body=mesh_list(mesh/'points')
    pts=np.array([[float(x) for x in row.split()] for row in re.findall(r'\(([^()]+)\)',body)])
    if pts.shape!=(n,3) or not np.isfinite(pts).all():raise ValueError('网格点无效')
    nf,body=mesh_list(mesh/'faces');faces=[]
    for size,row in re.findall(r'(\d+)\s*\(([^()]*)\)',body):
        ids=[int(x) for x in row.split()]
        if len(ids)!=int(size) or len(ids)<3 or min(ids)<0 or max(ids)>=n:raise ValueError('网格面无效')
        faces.append(ids)
    own=np.asarray(indices(mesh/'owner'));nei=np.asarray(indices(mesh/'neighbour'))
    if len(faces)!=nf or len(own)!=nf or len(nei)>nf:raise ValueError('网格拓扑长度不匹配')
    cells=int(max(own.max(),nei.max() if len(nei) else -1))+1
    if not 0<cells<=100000:raise ValueError('当前支持1–100000个二维单元')
    sf=np.empty((nf,3));centres=np.empty((nf,3))
    for count in sorted({len(f) for f in faces}):
        selected=np.array([i for i,f in enumerate(faces) if len(f)==count]);v=pts[np.asarray([faces[i] for i in selected])]
        c=v.mean(axis=1);nxt=np.roll(v,-1,axis=1);areas=np.cross(v-c[:,None,:],nxt-c[:,None,:])/2
        a=areas.sum(axis=1);norm=np.linalg.norm(a,axis=1)
        if np.any(norm<1e-20):raise ValueError('零面积网格面')
        weight=np.einsum('ijk,ik->ij',areas,a/norm[:,None]);fc=np.sum((v+nxt+c[:,None,:])/3*weight[:,:,None],axis=1)/norm[:,None]
        sf[selected]=a;centres[selected]=fc
    contribution=np.einsum('ij,ij->i',sf,centres)/3;vol=np.zeros(cells);closure=np.zeros((cells,3))
    np.add.at(vol,own,contribution);np.add.at(closure,own,sf)
    np.add.at(vol,nei,-contribution[:len(nei)]);np.add.at(closure,nei,-sf[:len(nei)])
    if not np.isfinite(vol).all() or np.any(vol<=1e-20):raise ValueError('网格存在非正有向体积')
    if np.max(np.linalg.norm(closure,axis=1))>1e-8*np.max(np.linalg.norm(sf,axis=1)):raise ValueError('单元面法向未闭合')
    count,body=mesh_list(mesh/'boundary');patches={};cursor=len(nei)
    for name,text in re.findall(r'([\w.-]+)\s*\{([^{}]*)\}',body):
        start=int(re.search(r'\bstartFace\s+(\d+)',text)[1]);size=int(re.search(r'\bnFaces\s+(\d+)',text)[1])
        if start!=cursor or start+size>nf:raise ValueError('边界面范围不连续')
        cursor+=size;patches[name]={'start':start,'size':size,'type':re.search(r'\btype\s+(\w+)',text)[1],'text':text}
    if len(patches)!=count or cursor!=nf:raise ValueError('边界字典未覆盖边界面')
    planes=[p for p in patches.values() if p['type']=='empty']
    if len(planes)!=2:raise ValueError('只支持两个empty面的单层二维XY叶栅')
    z=[]
    for p in planes:
        owners=own[p['start']:p['start']+p['size']]
        if len(owners)!=cells or set(owners)!=set(range(cells)):raise ValueError('empty边界未一一覆盖单元')
        used={idx for f in faces[p['start']:p['start']+p['size']] for idx in f};zz=pts[list(used),2]
        if np.ptp(zz)>1e-9:raise ValueError('empty边界不是XY平面')
        z.append(float(zz.mean()))
    span=abs(z[1]-z[0])
    if span<=1e-12:raise ValueError('实际网格展宽为零')
    low=patches.get('cyclicLow');high=patches.get('cyclicHigh')
    if not low or not high or low['type']!='cyclic' or high['type']!='cyclic' or low['size']!=high['size'] or not low['size']:raise ValueError('周期边界缺失')
    for p,other in [(low,'cyclicHigh'),(high,'cyclicLow')]:
        if not re.search(r'neighbourPatch\s+'+other+r'\s*;',p['text']):raise ValueError('周期邻居不匹配')
    sep=re.search(r'separationVector\s*\(([^)]+)\)',low['text'])
    if not sep:raise ValueError('周期平移量缺失')
    delta=np.array([float(v) for v in sep[1].split()]);ls=slice(low['start'],low['start']+low['size']);hs=slice(high['start'],high['start']+high['size'])
    tol=max(1e-10,1e-6*np.ptp(pts[:,0]));dist,pair=cKDTree(centres[hs]).query(centres[ls]+delta)
    if len(set(pair))!=len(pair) or np.max(dist)>tol or np.max(np.linalg.norm(sf[ls]+sf[hs][pair],axis=1))>1e-6*np.max(np.linalg.norm(sf[ls],axis=1)):raise ValueError('周期面几何配对不匹配')
    return {'owner':own,'neighbour':nei,'Sf':sf,'centres':centres,'volumes':vol,'cell_count':cells,'patches':patches,'span':span,'periodic_pair':pair}

def thermodynamics(case):
    text=read_ascii(case/'constant/thermophysicalProperties')
    for key,val in [('equationOfState','perfectGas'),('thermo','hConst'),('transport','const')]:
        if not re.search(r'\b'+key+r'\s+'+val+r'\s*;',text):raise ValueError('仅支持常比热、常黏度理想气体模板')
    scalar=lambda name:float(re.search(r'\b'+name+r'\s+([-+0-9.eE]+)\s*;',text)[1])
    mol,cp,mu=scalar('molWeight'),scalar('Cp'),scalar('mu');rgas=8314.46261815324/mol
    if not (mol>0 and cp>rgas and mu>0):raise ValueError('热物性无效')
    return {'molWeight':mol,'Cp':cp,'mu':mu,'Rgas':rgas,'gamma':cp/(cp-rgas)}

def load_case(case):
    case=safe_tree(case);mesh=read_mesh(case);n=mesh['cell_count']
    times=[p for p in case.iterdir() if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?(?:[eE][-+]?\d+)?',p.name) and np.isfinite(float(p.name)) and float(p.name)>0]
    if not times:raise ValueError('没有正时间目录')
    latest=max(times,key=lambda p:float(p.name));arrays={};texts={}
    for name,comp,dim in [('U',3,(0,1,-1,0,0,0,0)),('p',1,(1,-1,-2,0,0,0,0)),('T',1,(0,0,0,1,0,0,0))]:
        raw,units=field(latest/name,n,comp)
        if units!=dim:raise ValueError(name+'单位不符合当前合同')
        arrays[name]=np.array(raw).reshape(n,3) if comp==3 else np.array(raw);texts[name]=block(read_ascii(latest/name),'boundaryField')
    if np.any(arrays['p']<=0) or np.any(arrays['T']<=0) or np.max(np.abs(arrays['U'][:,2]))>1e-10:raise ValueError('内部场不满足二维正压正温要求')
    phi,units=field(latest/'phi',len(mesh['neighbour']),1)
    if units!=(1,0,-1,0,0,0,0):raise ValueError('phi必须为kg/s质量通量')
    texts['phi']=block(read_ascii(latest/'phi'),'boundaryField');patches={}
    for name in ('inlet','outlet','blade'):
        meta=mesh['patches'].get(name)
        if not meta or not meta['size']:raise ValueError('缺少边界 '+name)
        sl=slice(meta['start'],meta['start']+meta['size']);patch={'Sf':mesh['Sf'][sl],'centres':mesh['centres'][sl]}
        for fld,comp in [('U',3),('p',1),('T',1),('phi',1)]:
            body=block(texts[fld],name);arr=value(body,'value',meta['size'],comp)
            if arr is None:
                kind=re.search(r'\btype\s+(\w+)',body)[1]
                if kind=='zeroGradient' and fld in arrays:arr=arrays[fld][mesh['owner'][sl]]
                elif kind=='noSlip' and fld=='U':arr=np.zeros((meta['size'],3))
                else:raise ValueError(name+'/'+fld+'缺少可恢复的求解后边界值')
            patch[fld]=arr
        patches[name]=patch
    low=mesh['patches']['cyclicLow'];high=mesh['patches']['cyclicHigh']
    ql=value(block(texts['phi'],'cyclicLow'),'value',low['size'],1);qh=value(block(texts['phi'],'cyclicHigh'),'value',high['size'],1)
    if ql is None or qh is None:raise ValueError('缺少周期phi用于守恒检查')
    periodic_error=float(np.sum(np.abs(ql+qh[mesh['periodic_pair']]))/max(np.sum(np.abs(patches['inlet']['phi'])),1e-15))
    return {'time':latest.name,'mesh':mesh,'patches':patches,'thermo':thermodynamics(case),'internal':arrays,'periodic_flux_error':periodic_error}
