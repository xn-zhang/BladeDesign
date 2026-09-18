import unittest,tempfile,pathlib,sys,json,math
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import core
from create_pritchard_cascade import create,REFERENCE
from create_cascade import create as create_legacy,PARAMETERS
from pritchard_model import mesh_tokens,validate_parameters
class PritchardTests(unittest.TestCase):
    def test_model_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);create(root/'new');create_legacy(root/'old')
            new=core.load_template(root/'new');old=core.load_template(root/'old')
            with self.assertRaisesRegex(ValueError,'模型'):core.validate_template_design(old,REFERENCE)
            with self.assertRaisesRegex(ValueError,'模型'):core.validate_template_design(new,PARAMETERS)
    def test_real_shared_engine_stl_and_pitch_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);request=create(root/'template');tpl=core.load_template(root/'template')
            request['parameters']={**REFERENCE,'radius':REFERENCE['radius']*1.01}
            report=core.prepare_case(tpl,request,root/'case')
            self.assertEqual(report['geometry_model'],'pritchard-1985')
            pitch=2*math.pi*request['parameters']['radius']/REFERENCE['bladeCount']*.001
            self.assertAlmostEqual(report['pitch_m'],pitch)
            for name in ['system/blockMeshDict','system/createPatchDict','system/snappyHexMeshDict']:
                s=(root/'case'/name).read_text();self.assertNotIn('{{',s)
            self.assertIn(format(pitch,'.15g'),(root/'case/system/createPatchDict').read_text())
            payload=json.loads((root/'case/aeroblade-request.json').read_text());self.assertEqual(payload['geometry_model'],'pritchard-1985')
            self.assertGreater(report['volume_m3'],0)
    def test_strict_fields_and_integer_blade_count(self):
        for change in [{'bladeCount':50.5},{'radius':float('nan')},{'chord':40},{'model':'other'}]:
            with self.assertRaises(ValueError):validate_parameters({**REFERENCE,**change})
if __name__=='__main__':unittest.main()
