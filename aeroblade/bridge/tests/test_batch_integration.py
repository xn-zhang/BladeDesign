import copy,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]));sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from design_assistant import ModelService,ModelError
from evaluation.data import export_dataset
from test_batch_data import PLAN

class BatchIntegrationTests(unittest.TestCase):
    def test_llm_suggestion_cannot_change_baseline_or_supply_performance_labels(self):
        service=ModelService({});service.configure({'provider':'general','base_url':'http://127.0.0.1:9999/v1','model':'fixture-model','auth':'none'})
        suggestion={k:copy.deepcopy(PLAN[k]) for k in ('bounds','count','seed','conditions')};suggestion.update(rationale=['explicit test fixture assumption'],warnings=['requires CFD'])
        reply={'schema':'aeroblade-batch-plan-reply-v1','message':'fixture only','suggestion':suggestion}
        with patch.object(service,'_complete',return_value=json.dumps(reply)):
            result=service.batch_plan({'provider':'general','instruction':'fixture request','plan':PLAN});self.assertEqual(result['plan']['baseline'],PLAN['baseline']);self.assertEqual(result['plan']['provenance']['model'],'fixture-model')
        reply['suggestion']['efficiency']=.99
        with patch.object(service,'_complete',return_value=json.dumps(reply)),self.assertRaises(ModelError):service.batch_plan({'provider':'general','instruction':'fixture request','plan':PLAN})
    def test_batch_dataset_excludes_unrelated_jobs_and_keeps_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);jobs=root/'jobs';unrelated=jobs/('b'*32);unrelated.mkdir(parents=True);(unrelated/'job.json').write_text('{}')
            jid='a'*32;selection={'batch_id':'c'*32,'cases':[{'job_id':jid,'id':'d'*24,'geometry_id':'g0001','condition_id':'c01'}],'unselected_cases':[{'id':'e'*24,'status':'pending'}]}
            record={'job_id':jid,'sample_id':'f'*24,'duplicate_group':'unique','geometry_group':'shape','created_at':1,'metrics':{'values':{}},'quality':'workflow'}
            with patch('evaluation.data.evaluate_job',return_value=(record,{'fixture':np.array([1.])})) as evaluate:
                result=export_dataset(jobs,root/'output',selection)
            self.assertEqual(evaluate.call_args.args[0],jobs/jid);self.assertEqual(evaluate.call_count,1);self.assertEqual(result['accepted'][0]['batch_id'],'c'*32);self.assertEqual(result['selection'],selection)
    def test_missing_selected_job_is_reported_instead_of_silently_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            selection={'batch_id':'c'*32,'cases':[{'job_id':'a'*32,'id':'d'*24,'geometry_id':'g0001','condition_id':'c01'}],'unselected_cases':[]}
            result=export_dataset(pathlib.Path(tmp)/'missing',pathlib.Path(tmp)/'output',selection);self.assertEqual(len(result['rejected']),1);self.assertEqual(result['summary']['accepted'],0)

if __name__=='__main__':unittest.main()
