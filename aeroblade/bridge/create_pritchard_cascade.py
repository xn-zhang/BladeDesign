"""Create a Pritchard section cascade with geometry-derived pitch and domain."""
import argparse,json,math,pathlib,re
from create_cascade import create as create_legacy
ROOT=pathlib.Path(__file__).resolve().parents[1]
REFERENCE=dict(model='pritchard-1985',radius=139.7,bladeCount=51,axialChord=27.9908,tangentialChord=15.0114,
               leadingRadius=.7874,trailingRadius=.4064,inletAngle=35,outletAngle=-57,inletHalfWedge=9,unguidedTurning=6.5,height=60)
REFERENCE['throat']=2*math.pi*REFERENCE['radius']/REFERENCE['bladeCount']*math.cos(math.radians(57))-2*REFERENCE['trailingRadius']
def create(target):
    target=pathlib.Path(target);create_legacy(target)
    p=target/'system/blockMeshDict';s=p.read_text();s=re.sub(r'vertices\s*\(.*?\);', '''vertices (
({{PC_XLO}} {{PC_YLL}} -0.005) ({{PC_XHI}} {{PC_YHL}} -0.005)
({{PC_XHI}} {{PC_YHH}} -0.005) ({{PC_XLO}} {{PC_YLH}} -0.005)
({{PC_XLO}} {{PC_YLL}} 0.005) ({{PC_XHI}} {{PC_YHL}} 0.005)
({{PC_XHI}} {{PC_YHH}} 0.005) ({{PC_XLO}} {{PC_YLH}} 0.005));''',s,flags=re.S)
    s=s.replace('(80 30 5)','(180 24 5)').replace('(0 0.06 0)','(0 {{PC_PITCH}} 0)').replace('(0 -0.06 0)','(0 {{PC_NEG_PITCH}} 0)');p.write_text(s)
    p=target/'system/createPatchDict';p.write_text(p.read_text().replace('(0 0.06 0)','(0 {{PC_PITCH}} 0)').replace('(0 -0.06 0)','(0 {{PC_NEG_PITCH}} 0)'))
    p=target/'system/snappyHexMeshDict';p.write_text(p.read_text().replace('(-0.05 0 0)','({{PC_SEED_X}} {{PC_SEED_Y}} 0)').replace('level (2 3)','level (3 3)').replace('nSmoothPatch 3; tolerance 2;','nSmoothPatch 5; tolerance 1;'))
    p=target/'aeroblade-template.json';m=json.loads(p.read_text());m.update(id='pritchard-cascade-2d',name='Pritchard 1985 · 二维叶栅',geometry_model='pritchard-1985',
      description='几何来源：论文图19；周期节距随R/N自动更新，斜置计算域随Cx/Ct更新。OpenCFD v2512 / SST / 无棱柱层；新几何须重新验证收敛与网格质量。',
      geometry_bounds_m=[[-.06,-.12,-.08],[.06,.12,.08]],parameter_bounds={},recommended_parameters=REFERENCE)
    p.write_text(json.dumps(m,ensure_ascii=False,indent=2))
    request=dict(schema='aeroblade-cfd-v1',template_id=m['id'],parameters=REFERENCE,conditions={i['key']:i['default'] for i in m['inputs']})
    (target/'recommended-request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2));return request
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=pathlib.Path,default=ROOT/'templates/pritchard-cascade-2d');args=parser.parse_args();create(args.target);print(args.target)
