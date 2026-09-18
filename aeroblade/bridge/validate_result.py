"""Audit a completed real bridge job; never treats End alone as convergence."""
import argparse,json,math,pathlib,re
from core import parse_residuals
NUM=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
def audit(folder):
    folder=pathlib.Path(folder);j=json.loads((folder/'job.json').read_text());text=(folder/'run.log').read_text(errors='replace')
    case=folder/'case';mesh=text.split('--- checkMesh ---')[-1].split('\n--- ')[0]
    solver=text.split('--- '+j['solver']+' ---')[-1].split('\n--- ')[0]
    rows=parse_residuals(solver);last=max((r['iteration'] for r in rows),default=0);res={}
    for r in rows:
        if r['iteration']==last:res[r['field']]=max(res.get(r['field'],0),r['initial'])
    flows={}
    for patch in ['inlet','outlet']:
        values=re.findall(r'sum\('+patch+r'\) of phi = ('+NUM+')',solver)
        if values:flows[patch]=float(values[-1])
    balance=abs(sum(flows.values()))/max(abs(flows.get('inlet',0)),1e-30) if len(flows)==2 else None
    times=[p for p in case.iterdir() if p.is_dir() and re.fullmatch(NUM,p.name) and float(p.name)>0]
    latest=max(times,key=lambda p:float(p.name)) if times else None
    fields={};spanwise_velocity=None
    if latest:
        for name in ['p','T','U','k','omega']:
            path=latest/name
            if not path.exists():continue
            s=path.read_text();m=re.search(r'internalField\s+nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*\((.*?)\)\s*;',s,re.S)
            if m:
                values=[float(x) for x in re.findall(NUM,m[3])];n=int(m[2])*(3 if m[1]=='vector' else 1)
                if len(values)!=n:raise ValueError('Invalid field length: '+name)
            else:
                m=re.search(r'internalField\s+uniform\s+([^;]+);',s)
                values=[float(x) for x in re.findall(NUM,m[1])] if m else []
            if name=='U' and values:spanwise_velocity=max(abs(v) for v in values[2::3])
            fields[name]=dict(min=min(values) if values else None,max=max(values) if values else None,finite=bool(values) and all(math.isfinite(v) for v in values))
    dm=re.search(r'Mesh has (\d+) solution',mesh);dimensions=int(dm[1]) if dm else 3
    required={'Ux','Uy','p','h','k','omega'}|({'Uz'} if dimensions==3 else set())
    boundary=case/'constant/polyMesh/boundary';periodic=False
    if boundary.exists():
        blocks=dict(re.findall(r'(\w+)\s*\{([^{}]+)\}',boundary.read_text()))
        for low,high in [('cyclicLow','cyclicHigh'),('periodicLow','periodicHigh')]:
            if low in blocks and high in blocks:
                a,b=blocks[low],blocks[high];na=re.search(r'nFaces\s+(\d+)',a);nb=re.search(r'nFaces\s+(\d+)',b)
                periodic=all(re.search(r'type\s+cyclic;',v) for v in [a,b]) and re.search(r'neighbourPatch\s+'+high+r';',a) is not None and re.search(r'neighbourPatch\s+'+low+r';',b) is not None and bool(na and nb and int(na[1])>0 and na[1]==nb[1])
                break
    checks=dict(periodic_pair_valid=periodic and 'Coupled point location match' in mesh,
      planar_velocity_valid=dimensions!=2 or (spanwise_velocity is not None and spanwise_velocity<1e-10),completed=j['status']=='completed',mesh_quality_passed='Mesh OK.' in mesh and 'Failed ' not in mesh,
      solver_end=bool(re.search(r'^End\s*$',solver,re.M)),solver_reported_convergence=bool(re.search(r'converged in',solver,re.I)),
      residuals_below_1e_minus5=required<=set(res) and all(0<=v<1e-5 for v in res.values()),mass_balance_below_01_percent=balance is not None and balance<.001 and flows['inlet']<0<flows['outlet'],
      fields_finite=all(name in fields and fields[name]['finite'] for name in ['p','T','U','k','omega']),
      pressure_temperature_positive=all(name in fields and fields[name]['min'] is not None and fields[name]['min']>0 for name in ['p','T']),
      vtk_exported=bool(list((case/'VTK').rglob('*.vtu'))),archive_present=(folder/'results.zip').is_file())
    metric=lambda pattern: float(re.search(pattern,mesh)[1]) if re.search(pattern,mesh) else None
    result=dict(solution_dimensions=dimensions,max_abs_spanwise_velocity=spanwise_velocity,job_id=j['id'],solver=j['solver'],last_solved_iteration=last,latest_written_time=latest.name if latest else None,
      checks=checks,workflow_verified=all(checks.values()),mesh=dict(cells=metric(r'cells:\s*(\d+)'),max_non_orthogonality=metric(r'non-orthogonality Max:\s*('+NUM+')'),max_skewness=metric(r'Max skewness =\s*('+NUM+')')),
      final_initial_residuals=res,mass_flow_kg_s=flows,relative_mass_imbalance=balance,field_ranges=fields,
      limitations=['Cold stationary RANS workflow test; no experimental validation or grid independence.',
      'First-order upwind and no prism layers; losses and efficiency are not validated.',
      'Strict allGeometry convexity diagnostics are reported separately; the gate uses topology and explicit meshQuality thresholds.'])
    strict=folder/'strict-checkMesh.log'
    if strict.exists():
        diagnostic=strict.read_text(errors='replace')
        count=re.search(r'Concave cells.*?number of cells:\s*(\d+)',diagnostic)
        result['strict_geometry_diagnostic']={'passed':'Mesh OK.' in diagnostic and 'Failed ' not in diagnostic,'concave_cells':int(count[1]) if count else 0,'log':strict.name}
    yplus=re.findall(r'patch blade y\+ : min = ('+NUM+r'), max = ('+NUM+r'), average = ('+NUM+r')',solver)
    if yplus:result['blade_y_plus']=dict(zip(['min','max','average'],map(float,yplus[-1])))
    (folder/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job',type=pathlib.Path);a=p.parse_args();result=audit(a.job)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['workflow_verified'] else 2)
# end
