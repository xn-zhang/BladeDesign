import pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from core import Manager

class IdempotentSubmissionTests(unittest.TestCase):
    def test_key_is_durable_and_rejects_changed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);m=Manager(root/'jobs',root/'templates');m.templates['tpl']={'id':'tpl','solver':'rhoSimpleFoam'}
            payload={'schema':'aeroblade-cfd-v1','name':'训练数据批次 · 初设','template_id':'tpl','parameters':{'x':1},'conditions':{'p':2},'submission_key':'a'*64,'batch_id':'b'*32,'batch_case_id':'c'*24}
            try:
                with patch.object(m,'health',return_value={'ready':True}),patch('core.validate_template_design',return_value={'x':1}),patch('core.validate_conditions',return_value={'p':2}),patch.object(m.pool,'submit'):
                    a=m.submit(payload);b=m.submit(payload);self.assertEqual(a['id'],b['id']);self.assertEqual(len(m.jobs),1)
                    self.assertIn('训练数据批次',(root/'jobs'/a['id']/'job.json').read_text(encoding='utf-8'))
                    with self.assertRaises(ValueError):m.submit({**payload,'parameters':{'x':3}})
                m2=Manager(root/'jobs',root/'templates')
                try:self.assertEqual(m2.submit(payload)['id'],a['id'])
                finally:m2.shutdown()
            finally:m.shutdown()

if __name__=='__main__':unittest.main()
