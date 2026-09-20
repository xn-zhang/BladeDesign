import copy,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from evaluation.batch_data import generate,import_designs,validate_plan

ROOT=pathlib.Path(__file__).resolve().parents[2]
P=json.loads((ROOT/'templates/pritchard-cascade-2d/recommended-request.json').read_text(encoding='utf-8'))['parameters']
C={'inletTotalPressure':100200,'inletTotalTemperature':300,'outletStaticPressure':100000,'iterations':3000}
PLAN={'name':'测试参数包','baseline':P,'bounds':{'radius':[139,149]},'count':5,'seed':42,'conditions':[C,{**C,'inletTotalPressure':100300}]}

class BatchDataTests(unittest.TestCase):
    def test_reproducible_unique_geometries_and_frozen_baseline(self):
        a=generate(copy.deepcopy(PLAN));b=generate(copy.deepcopy(PLAN))
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(a['designs']),5)
        self.assertEqual(a['designs'][0]['parameters'],P);self.assertEqual(len({d['geometry_hash'] for d in a['designs']}),5)
        self.assertEqual(a['case_count'],10);self.assertEqual(a['units'],{'length':'mm','angle':'deg'})
    def test_import_recomputes_geometry_and_deduplicates(self):
        a=generate(copy.deepcopy(PLAN));a['designs'][1]['geometry_hash']='forged';a['designs'].append(copy.deepcopy(a['designs'][0]));b=import_designs(a)
        self.assertEqual(len(b['designs']),5);self.assertNotIn('forged',{d['geometry_hash'] for d in b['designs']})
        a['designs'][0]['parameters']['throat']=0
        with self.assertRaises(ValueError):import_designs(a)
    def test_bounds_and_conditions_rejected_before_sampling(self):
        for update in [{'bounds':{'height':[50,70]}},{'bounds':{'radius':[150,160]}},{'count':10000},{'conditions':[{**C,'outletStaticPressure':99999}]},{'conditions':[C,C]}]:
            with self.subTest(update=update),self.assertRaises(ValueError):validate_plan({**copy.deepcopy(PLAN),**update})
    def test_finite_retry_cap_for_infeasible_combinations(self):
        from unittest.mock import patch
        from evaluation import batch_data
        with patch.object(batch_data,'geometry_many',return_value=[{'error':'fixture invalid'}]*30):
            with self.assertRaisesRegex(ValueError,'基准'):generate(copy.deepcopy(PLAN))
    def test_export_import_reuses_validated_package_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=generate(copy.deepcopy(PLAN),tmp);imported=import_designs(copy.deepcopy(original),tmp);again=import_designs(copy.deepcopy(imported),tmp)
            self.assertEqual(imported['id'],original['id']);self.assertEqual(again['id'],original['id'])

if __name__=='__main__':unittest.main()
