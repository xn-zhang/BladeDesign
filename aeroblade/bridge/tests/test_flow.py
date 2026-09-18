import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from flow import load_flow

def fixture(root):
    mesh=root/'constant/polyMesh';mesh.mkdir(parents=True);time=root/'10';time.mkdir()
    def write(path,body):path.write_text('FoamFile {version 2.0; format ascii;}\n'+body)
    coords=[(0,0),(1,0),(2,0),(0,1),(1,1),(2,1)]
    pts=[(x,y,z) for z in (0,.01) for x,y in coords]
    write(mesh/'points','12\n(\n'+'\n'.join('(%s %s %s)'%p for p in pts)+'\n)')
    write(mesh/'faces','4\n(\n4(0 1 4 3)\n4(1 2 5 4)\n4(6 9 10 7)\n4(7 10 11 8)\n)')
    write(mesh/'owner','4\n(0 1 0 1)');write(mesh/'neighbour','0\n()')
    write(mesh/'boundary','2\n(front {type empty; nFaces 2; startFace 0;} back {type empty; nFaces 2; startFace 2;})')
    write(time/'p','dimensions [1 -1 -2 0 0 0 0]; internalField nonuniform List<scalar> 2 (100 110); boundaryField {}')
    write(time/'U','dimensions [0 1 -1 0 0 0 0]; internalField nonuniform List<vector> 2 ((3 4 0) (0 0 0)); boundaryField {}')
    write(time/'T','dimensions [0 0 0 1 0 0 0]; internalField uniform 300; boundaryField {}')
    return root
class FlowTests(unittest.TestCase):
    def test_cell_geometry_and_actual_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=load_flow(fixture(pathlib.Path(tmp)))
            self.assertEqual(d['time'],'10');self.assertEqual(d['cell_ids'],[0,1])
            self.assertEqual(d['fields']['speed']['values'],[5.,0.])
            self.assertEqual(d['fields']['p']['values'],[100.,110.])
            self.assertEqual(d['fields']['T']['values'],[300.,300.])
            self.assertEqual(d['fields']['p']['unit'],'Pa')
            self.assertEqual(len(d['cells']),2)
    def test_rejects_nonfinite_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=fixture(pathlib.Path(tmp));p=root/'10/p';p.write_text(p.read_text().replace('(100 110)','(nan 110)'))
            with self.assertRaises(ValueError):load_flow(root)
    def test_does_not_project_three_dimensional_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=fixture(pathlib.Path(tmp));p=root/'constant/polyMesh/boundary';p.write_text(p.read_text().replace('type empty','type symmetryPlane'))
            with self.assertRaisesRegex(ValueError,'二维'):load_flow(root)
    def test_pressure_units_follow_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=fixture(pathlib.Path(tmp));p=root/'10/p';p.write_text(p.read_text().replace('[1 -1 -2 0 0 0 0]','[0 2 -2 0 0 0 0]'))
            self.assertEqual(load_flow(root)['fields']['p']['unit'],'m²/s²')
# end
