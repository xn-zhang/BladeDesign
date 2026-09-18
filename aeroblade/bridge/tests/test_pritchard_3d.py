import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from create_pritchard_3d import create
from core import load_template,prepare_case
class ThreeDimensionalTemplateTests(unittest.TestCase):
    def test_has_real_endwalls_and_no_dimension_reduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);request=create(root/'template');tpl=load_template(root/'template')
            self.assertEqual(tpl['simulation_dimensions'],3)
            self.assertEqual(tpl['physical_span_m'],.01)
            self.assertEqual([stage[0] for stage in tpl['pipeline']],['blockMesh','snappyHexMesh','checkMesh','rhoSimpleFoam','foamToVTK'])
            block=(root/'template/system/blockMeshDict').read_text()
            self.assertNotIn('symmetryPlane',block);self.assertIn('(96 18 12)',block)
            for field,kind in [('U','noSlip'),('T','zeroGradient'),('p','zeroGradient'),('omega','omegaWallFunction'),('nut','nutkWallFunction')]:
                s=(root/'template/0'/field).read_text()
                self.assertNotIn('empty',s)
                for patch in ['spanLow','spanHigh']:
                    self.assertRegex(s,patch+r'\s*\{type '+kind+r';')
            report=prepare_case(tpl,request,root/'case')
            self.assertEqual(report['geometry_model'],'pritchard-1985')
            self.assertGreater(report['bounds_m'][1][2],.005)
            self.assertLess(report['bounds_m'][0][2],-.005)
            self.assertNotIn('{{',(root/'case/system/blockMeshDict').read_text())
    def test_refinement_changes_only_mesh_span_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=pathlib.Path(tmp);create(r/'coarse',12);create(r/'fine',24)
            self.assertEqual((r/'coarse/system/blockMeshDict').read_text().replace('(96 18 12)','(96 18 24)'),(r/'fine/system/blockMeshDict').read_text())
            self.assertEqual(json.loads((r/'coarse/recommended-request.json').read_text()),json.loads((r/'fine/recommended-request.json').read_text()))
    def test_refuses_invalid_mesh_count_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=pathlib.Path(tmp)/'template'
            for count in [0,5,49,12.5,True]:
                with self.assertRaises(ValueError):create(r,count)
            create(r)
            with self.assertRaises(FileExistsError):create(r)
if __name__=='__main__':unittest.main()
