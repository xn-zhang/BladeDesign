import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from evaluation.foam import load_case
from evaluation.data import classify

def duct_fixture(case):
    """12 full hexahedra around a square obstacle; algebra fixture, not CFD evidence."""
    case=pathlib.Path(case);mesh=case/'constant/polyMesh';mesh.mkdir(parents=True);time=case/'10';time.mkdir()
    def write(path,text):path.write_text('FoamFile {format ascii;}\n'+text,encoding='utf-8')
    pts=[(i,j,k*.01) for k in range(2) for j in range(5) for i in range(5)]
    idx=lambda i,j,k:k*25+j*5+i
    cells=[(i,j) for j in range(4) for i in range(4) if not(1<=i<=2 and 1<=j<=2)]
    mapping={}
    for owner,(i,j) in enumerate(cells):
        faces=[('spanLow',[(i,j,0),(i,j+1,0),(i+1,j+1,0),(i+1,j,0)]),('spanHigh',[(i,j,1),(i+1,j,1),(i+1,j+1,1),(i,j+1,1)]),
         ('inlet' if i==0 else 'blade',[(i,j,0),(i,j,1),(i,j+1,1),(i,j+1,0)]),('outlet' if i==3 else 'blade',[(i+1,j,0),(i+1,j+1,0),(i+1,j+1,1),(i+1,j,1)]),
         ('cyclicLow' if j==0 else 'blade',[(i,j,0),(i+1,j,0),(i+1,j,1),(i,j,1)]),('cyclicHigh' if j==3 else 'blade',[(i,j+1,0),(i,j+1,1),(i+1,j+1,1),(i+1,j+1,0)])]
        for patch,coords in faces:
            face=[idx(*q) for q in coords];key=tuple(sorted(face))
            if key in mapping:mapping[key]['neighbour']=owner
            else:mapping[key]={'face':face,'owner':owner,'patch':patch}
    internal=[f for f in mapping.values() if 'neighbour' in f];names=['inlet','outlet','spanLow','spanHigh','blade','cyclicLow','cyclicHigh']
    grouped={name:[f for f in mapping.values() if 'neighbour' not in f and f['patch']==name] for name in names}
    faces=internal+sum([grouped[n] for n in names],[])
    listing=lambda values:f'{len(values)}\n(\n'+'\n'.join(map(str,values))+'\n)'
    write(mesh/'points',listing(['(%s %s %s)'%p for p in pts]));write(mesh/'faces',listing(['4('+' '.join(map(str,f['face']))+')' for f in faces]))
    write(mesh/'owner',listing([f['owner'] for f in faces]));write(mesh/'neighbour',listing([f['neighbour'] for f in internal]))
    boundary=[];start=len(internal)
    for name in names:
        kind='empty' if name.startswith('span') else 'cyclic' if name.startswith('cyclic') else 'wall' if name=='blade' else 'patch'
        extra=(' neighbourPatch cyclicHigh; separationVector (0 4 0);' if name=='cyclicLow' else ' neighbourPatch cyclicLow; separationVector (0 -4 0);' if name=='cyclicHigh' else '')
        boundary.append(f'{name} {{type {kind}; nFaces {len(grouped[name])}; startFace {start};{extra}}}');start+=len(grouped[name])
    write(mesh/'boundary',listing(boundary))
    write(case/'constant/thermophysicalProperties','thermoType {equationOfState perfectGas; thermo hConst; transport const;} mixture {specie {molWeight 28.96;} thermodynamics {Cp 1004.5;} transport {mu 1.8e-5;}}')
    for name,dims,inside in [('p','1 -1 -2 0 0 0 0','100000'),('T','0 0 0 1 0 0 0','300'),('U','0 1 -1 0 0 0 0','(10 0 0)'),('phi','1 0 -1 0 0 0 0','0')]:
        b=[]
        for patch in names:
            if patch.startswith('span'):body='type empty;'
            elif patch=='blade':body='type noSlip;' if name=='U' else 'type calculated; value uniform 0;' if name=='phi' else 'type zeroGradient;'
            elif name=='phi':body='type calculated; value uniform '+str((-1 if patch=='inlet' else 1 if patch=='outlet' else 0)*100000/(8314.46261815324/28.96)/300*.1)+';'
            else:body=('type totalPressure; p0 uniform 100200;' if patch=='inlet' and name=='p' else 'type fixedValue;')+' value uniform '+inside+';'
            b.append(patch+' {'+body+'}')
        write(time/name,f'dimensions [{dims}]; internalField uniform {inside}; boundaryField {{'+''.join(b)+'}')
    return case

class DataTests(unittest.TestCase):
    def test_full_topology_boundary_values_and_oriented_volumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=load_case(duct_fixture(tmp));self.assertEqual(r['mesh']['cell_count'],12)
            np.testing.assert_allclose(r['mesh']['volumes'],.01)
            self.assertAlmostEqual(r['mesh']['span'],.01)
            np.testing.assert_allclose(r['patches']['inlet']['p'],100000) # not p0=100200
            self.assertLess(r['periodic_flux_error'],1e-12)
    def test_reject_missing_actual_boundary_value_and_wrong_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=duct_fixture(tmp);p=root/'10/p';original=p.read_text();p.write_text(original.replace('p0 uniform 100200; value uniform 100000;','p0 uniform 100200;'))
            with self.assertRaisesRegex(ValueError,'边界值'):load_case(root)
            p.write_text(original.replace('[1 -1 -2 0 0 0 0]','[0 2 -2 0 0 0 0]'))
            with self.assertRaisesRegex(ValueError,'单位'):load_case(root)
    def test_unknown_quality_is_not_passed(self):
        self.assertEqual(classify({})['tier'],'rejected')

if __name__=='__main__':unittest.main()
