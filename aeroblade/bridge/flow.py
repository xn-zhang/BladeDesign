"""Bounded read-only XY cell preview of completed ASCII OpenFOAM cases.
Cell polygons come from an empty boundary; values remain cell-centred.
No interpolation across solids and no projected 3D substitute.
"""
import math,pathlib,re
MAX_CELLS=60000

def read_ascii(path):
    path=pathlib.Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('所需场文件不可用，请下载原始结果检查')
    if path.stat().st_size>64_000_000:raise ValueError('场文件超过网页预览限制，请下载 VTK')
    text=path.read_text(encoding='utf-8')
    text=re.sub(r'/\*.*?\*/','',text,flags=re.S);text=re.sub(r'//[^\n]*','',text)
    if not re.search(r'\bformat\s+ascii\s*;',text):raise ValueError('当前预览仅支持 ASCII OpenFOAM 场，请下载 VTK')
    return text

def mesh_list(path):
    text=re.sub(r'FoamFile\s*\{[^{}]*\}','',read_ascii(path))
    m=re.fullmatch(r'\s*(\d+)\s*\((.*)\)\s*',text,re.S)
    if not m:raise ValueError('网格列表格式无法预览')
    return int(m[1]),m[2]

def indices(path):
    n,body=mesh_list(path);values=[int(v) for v in body.split()]
    if len(values)!=n or any(v<0 for v in values):raise ValueError('网格索引无效')
    return values

def field(path,count,components):
    text=read_ascii(path);dims=re.search(r'\bdimensions\s*\[([^]]+)\]',text)
    if not dims:raise ValueError('场单位缺失')
    dimensions=tuple(float(v) for v in dims[1].split())
    m=re.search(r'\binternalField\s+nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*\((.*?)\)\s*;',text,re.S)
    if m:
        if int(m[2])!=count or (m[1]=='vector')!=(components==3):raise ValueError('场与网格单元数量不匹配')
        values=[float(v) for v in m[3].replace('(',' ').replace(')',' ').split()]
    else:
        m=re.search(r'\binternalField\s+uniform\s+([^;]+);',text)
        if not m:raise ValueError('无法读取单元内部场')
        values=[float(v) for v in m[1].replace('(',' ').replace(')',' ').split()]
        if len(values)!=components:raise ValueError('场分量数量错误')
        values*=count
    if len(values)!=count*components or not all(math.isfinite(v) for v in values):raise ValueError('场包含无效数值，不能生成云图')
    return values,dimensions

def load_flow(case):
    case=pathlib.Path(case);mesh=case/'constant/polyMesh'
    _,body=mesh_list(mesh/'boundary')
    blocks=re.findall(r'([\w.-]+)\s*\{([^{}]+)\}',body)
    empty=[(name,b) for name,b in blocks if re.search(r'\btype\s+empty;',b)]
    if len(empty)!=2:raise ValueError('当前流场面板仅支持 XY 平面二维算例；三维结果请下载 VTK')
    times=[p for p in case.iterdir() if p.is_dir() and not p.is_symlink() and re.fullmatch(r'\d+(?:\.\d+)?(?:[eE][-+]?\d+)?',p.name) and math.isfinite(float(p.name)) and float(p.name)>0]
    if not times:raise ValueError('尚无可预览的已写入场数据')
    latest=max(times,key=lambda p:float(p.name))
    owner=indices(mesh/'owner');neighbour=indices(mesh/'neighbour')
    count=max(owner+neighbour,default=-1)+1
    if not 0<count<=MAX_CELLS:raise ValueError('单元数超过网页预览限制，请下载 VTK')
    n,body=mesh_list(mesh/'points');points=[]
    for row in re.findall(r'\(([^()]+)\)',body):
        xyz=[float(v) for v in row.split()]
        if len(xyz)!=3 or not all(math.isfinite(v) for v in xyz):raise ValueError('网格坐标无效')
        points.append(xyz)
    if len(points)!=n:raise ValueError('网格点数量不匹配')
    n,body=mesh_list(mesh/'faces');faces=[]
    for size,entries in re.findall(r'(\d+)\s*\(([^()]*)\)',body):
        ids=[int(v) for v in entries.split()]
        if len(ids)!=int(size) or len(ids)<3 or any(v<0 or v>=len(points) for v in ids):raise ValueError('网格面索引无效')
        faces.append(ids)
    if len(faces)!=n or len(owner)!=n:raise ValueError('网格面数量不匹配')
    b=empty[0][1];start=re.search(r'\bstartFace\s+(\d+)',b);size=re.search(r'\bnFaces\s+(\d+)',b)
    if not start or not size or int(size[1])!=count:raise ValueError('二维单元与截面面片数量不匹配')
    begin=int(start[1]);end=begin+count
    if end>len(faces):raise ValueError('截面面片索引无效')
    cell_ids=owner[begin:end]
    if set(cell_ids)!=set(range(count)):raise ValueError('截面并未覆盖每个实际单元')
    selected=faces[begin:end];used=sorted({v for face in selected for v in face});zs=[points[v][2] for v in used]
    if max(zs)-min(zs)>1e-8:raise ValueError('当前预览仅支持 XY 平面二维算例')
    mapping={old:new for new,old in enumerate(used)};xy=[points[v][:2] for v in used]
    cells=[[mapping[v] for v in f] for f in selected]
    u,dim=field(latest/'U',count,3)
    if dim!=(0,1,-1,0,0,0,0):raise ValueError('速度单位不支持')
    speed=[math.hypot(*u[i*3:i*3+3]) for i in cell_ids]
    p,dim=field(latest/'p',count,1)
    if dim==(1,-1,-2,0,0,0,0):label,unit='静压','Pa'
    elif dim==(0,2,-2,0,0,0,0):label,unit='运动压力','m²/s²'
    else:raise ValueError('压力单位不支持')
    def values(label,unit,data):return dict(label=label,unit=unit,values=data,min=min(data),max=max(data))
    fields=dict(speed=values('速度大小','m/s',speed),p=values(label,unit,[p[i] for i in cell_ids]))
    if (latest/'T').exists():
        t,dim=field(latest/'T',count,1)
        if dim!=(0,0,0,1,0,0,0):raise ValueError('温度单位不支持')
        fields['T']=values('温度','K',[t[i] for i in cell_ids])
    return dict(schema='aeroblade-flow-v1',time=latest.name,coordinate_units='m',plane='XY',cell_count=count,
        source='OpenFOAM internalField + empty-patch cell polygons',points=xy,cells=cells,cell_ids=cell_ids,fields=fields,
        bounds=[[min(p[i] for p in xy) for i in range(2)],[max(p[i] for p in xy) for i in range(2)]])
# end
