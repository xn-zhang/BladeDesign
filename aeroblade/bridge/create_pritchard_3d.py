"""Generate a finite-span Pritchard cascade with stationary adiabatic endwalls."""
import argparse,json,pathlib,re
from create_pritchard_cascade import create as create_section_cascade
ROOT=pathlib.Path(__file__).resolve().parents[1]

def create(target,span_cells=12):
    if type(span_cells) is not int or not 8<=span_cells<=48:raise ValueError('span_cells must be 8–48')
    target=pathlib.Path(target);create_section_cascade(target)
    p=target/'system/blockMeshDict';s=p.read_text().replace('(180 24 5)',f'(96 18 {span_cells})').replace('type symmetryPlane','type wall');p.write_text(s)
    p=target/'system/snappyHexMeshDict';s=p.read_text().replace('level (3 3)','level (2 2)');p.write_text(s)
    for p in (target/'0').iterdir():
        s=p.read_text();wall=re.search(r'blade\s*\{([^{}]*)\}',s)
        if not wall:raise ValueError('Missing blade wall condition: '+p.name)
        for patch in ['spanLow','spanHigh']:
            s,n=re.subn(patch+r'\s*\{type empty;\}',patch+' {'+wall[1]+'}',s)
            if n!=1:raise ValueError('Missing span boundary: '+p.name)
        s=s.replace('cyclicLow','periodicLow').replace('cyclicHigh','periodicHigh');p.write_text(s)
    p=target/'aeroblade-template.json';m=json.loads(p.read_text());m.update(
        id='pritchard-cascade-3d',name='Pritchard · 三维端壁叶栅（探索）',simulation_dimensions=3,physical_span_m=.01,
        description='3D有限展宽10 mm / 两侧静止绝热无滑移端壁 / 周期叶栅 / 等截面Pritchard叶型。冷态SST，一阶迎风、无棱柱层；尚非扭转叶片、旋转叶排或工程精度验证。三维场请下载VTK查看。',
        pipeline=[['blockMesh'],['snappyHexMesh','-overwrite'],['checkMesh','-allTopology','-meshQuality'],['rhoSimpleFoam'],['foamToVTK','-latestTime']],
        # The STL extends beyond both physical endwalls; snappy clips the fluid domain.
        parameter_bounds={'height':[30,160]})
    p.write_text(json.dumps(m,ensure_ascii=False,indent=2))
    for filename in ['extrudeMeshDict','createPatchDict']:
        (target/'system'/filename).unlink()
    request=json.loads((target/'recommended-request.json').read_text());request['template_id']=m['id'];(target/'recommended-request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2));return request

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=pathlib.Path,default=ROOT/'templates/pritchard-cascade-3d');parser.add_argument('--span-cells',type=int,default=12);a=parser.parse_args();create(a.target,a.span_cells);print(a.target)
