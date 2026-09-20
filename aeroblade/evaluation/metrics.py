"""Six versioned cold-cascade metrics from outward fluid boundary face vectors."""
import math
import numpy as np

METRICS=('loss_coefficient','outlet_angle_deg','turning_angle_deg','mass_flow_per_span','pressure_force_x_coefficient','pressure_force_y_coefficient')
UNITS=('', 'deg','deg','kg/(s·m)','','')
LABELS=('总压损失系数','出口流角','流动转折角','单位展宽质量流量','轴向压力载荷系数','周向压力载荷系数')
VERSION='cold-cascade-boundary-v1'

def wrap_angle(value):return (value+180)%360-180

def extract(patches,span,chord,conditions,thermo):
    if span<=0 or chord<=0:raise ValueError('网格厚度/弦长必须为正')
    pref=conditions['outletStaticPressure'];dp=conditions['inletTotalPressure']-pref
    if pref<=0 or dp<=0:raise ValueError('参考压力及总静压差必须为正')
    rgas=thermo['Rgas'];gamma=thermo['gamma'];summary={};warnings=[];flux_errors=[]
    for name,sign in [('inlet',-1),('outlet',1)]:
        patch=patches[name];p=np.asarray(patch['p']);t=np.asarray(patch['T']);u=np.asarray(patch['U']);sf=np.asarray(patch['Sf'])
        if not len(p) or t.shape!=p.shape or u.shape!=(len(p),3) or sf.shape!=u.shape:raise ValueError('边界场维度不匹配')
        if not all(np.isfinite(a).all() for a in (p,t,u,sf)) or np.any(p<=0) or np.any(t<=0):raise ValueError('边界压力/温度/速度无效')
        flux=p/(rgas*t)*np.einsum('ij,ij->i',u,sf);w=sign*flux
        positive=w[w>0].sum();reverse=-w[w<0].sum()
        if positive<=1e-15:raise ValueError('边界主流量接近零')
        if reverse/positive>.001:raise ValueError('边界回流比例超过0.1%')
        if reverse:warnings.append(name+' 含微量回流，加权时只取正向通量')
        weight=np.maximum(w,0)/positive
        p0=p*(1+(gamma-1)*np.sum(u*u,axis=1)/(2*gamma*rgas*t))**(gamma/(gamma-1))
        average_u=np.sum(u*weight[:,None],axis=0)
        if np.linalg.norm(average_u[:2])<1e-10:raise ValueError('平均主流速度接近零')
        summary[name]={'p':float(p@weight),'p0':float(p0@weight),'angle':math.degrees(math.atan2(average_u[1],average_u[0])),'mass':float(flux.sum()),'reverse_fraction':float(reverse/positive)}
        if 'phi' in patch:
            phi=np.asarray(patch['phi'])
            if phi.shape!=flux.shape or not np.isfinite(phi).all():raise ValueError('phi边界场无效')
            flux_errors.append(float(np.sum(np.abs(phi-flux))/max(np.sum(np.abs(phi)),1e-15)))
    inlet,outlet=summary['inlet'],summary['outlet'];denom=inlet['p0']-outlet['p']
    if denom<max(1e-8*pref,1e-6):raise ValueError('损失归一化分母太小')
    blade=patches.get('blade');force=[None,None]
    if blade is not None:
        sf=np.asarray(blade['Sf']);p=np.asarray(blade['p'])
        if len(p)==0 or sf.shape!=(len(p),3) or not np.isfinite(p).all() or np.any(p<=0):raise ValueError('叶片壁面压力无效')
        if np.linalg.norm(sf[:,:2].sum(axis=0))>1e-7*span*chord:raise ValueError('叶片壁面法向不闭合')
        force=(((p-pref)[:,None]*sf).sum(axis=0)/(span*chord*dp))[:2].tolist()
    values=[(inlet['p0']-outlet['p0'])/denom,outlet['angle'],wrap_angle(outlet['angle']-inlet['angle']),outlet['mass']/span,*force]
    if values[0]<0:warnings.append('总压损失为负，需复核边界、离散误差和适用工况')
    balance=abs(inlet['mass']+outlet['mass'])/max(abs(inlet['mass']),1e-15)
    return {'version':VERSION,'values':dict(zip(METRICS,values)),'valid':all(v is not None and math.isfinite(v) for v in values),
            'boundary':summary,'relative_mass_imbalance':balance,'phi_reconstruction_relative_error':max(flux_errors,default=None),'warnings':warnings}
