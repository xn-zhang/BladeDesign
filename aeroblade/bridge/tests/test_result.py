import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from validate_result import audit
class ResultTests(unittest.TestCase):
    def test_normal_exit_is_not_cfd_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=pathlib.Path(tmp);(d/'case').mkdir()
            (d/'job.json').write_text(json.dumps(dict(id='fixture',solver='rhoSimpleFoam',status='completed')))
            (d/'run.log').write_text('--- checkMesh ---\nMesh OK.\n--- rhoSimpleFoam ---\nTime = 1\nEnd\n')
            result=audit(d)
            self.assertTrue(result['checks']['solver_end'])
            self.assertFalse(result['workflow_verified'])
            self.assertFalse(result['checks']['solver_reported_convergence'])
            self.assertFalse(result['checks']['fields_finite'])
            self.assertFalse(result['checks']['mass_balance_below_01_percent'])
    def test_zero_flow_and_partial_residuals_are_not_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=pathlib.Path(tmp);(d/'case').mkdir()
            (d/'job.json').write_text(json.dumps(dict(id='fixture',solver='rhoSimpleFoam',status='completed')))
            (d/'run.log').write_text('--- checkMesh ---\nMesh OK.\n--- rhoSimpleFoam ---\nTime = 1\nGAMG: Solving for p, Initial residual = 1e-7, Final residual = 1e-10\nsum(inlet) of phi = 0\nsum(outlet) of phi = 0\nSIMPLE solution converged in 1 iterations\nEnd\n')
            result=audit(d)
            self.assertFalse(result['checks']['mass_balance_below_01_percent'])
            self.assertFalse(result['checks']['residuals_below_1e_minus5'])
