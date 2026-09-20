import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from optimization import candidate_parameters,rank_candidates,validate_config

class OptimizationTests(unittest.TestCase):
    def test_doe_reproducible_integer_and_baseline(self):
        p={'radius':150,'bladeCount':50};bounds={'radius':[140,160],'bladeCount':[48,52]}
        a=candidate_parameters(p,bounds,8,42);self.assertEqual(a,candidate_parameters(p,bounds,8,42));self.assertEqual(a[0],p)
        self.assertTrue(all(140<=r['radius']<=160 and type(r['bladeCount'])==int for r in a))
    def test_pareto_uses_only_feasible_cfd(self):
        rows=[{'status':'verified','values':{'loss_coefficient':x,'mass_flow_per_span':y}} for x,y in [(1,2),(2,1),(3,3)]]
        rows.append({'status':'predicted','values':{'loss_coefficient':0,'mass_flow_per_span':5}})
        cfg={'objectives':[{'metric':'loss_coefficient','direction':'min'},{'metric':'mass_flow_per_span','direction':'max'}],'constraints':[{'metric':'mass_flow_per_span','op':'>=','value':1.5}]}
        rank_candidates(rows,cfg);self.assertEqual([r.get('pareto',False) for r in rows],[True,False,True,False]);self.assertFalse(rows[1]['feasible'])
    def test_budget_and_unsafe_bounds_rejected(self):
        base={'parameters':{'radius':150},'conditions':{},'bounds':{'radius':[140,160]},'budget':3,'mode':'cfd','objectives':[{'metric':'loss_coefficient','direction':'min'}],'constraints':[]}
        with self.assertRaises(ValueError):validate_config({**base,'budget':10000})
        with self.assertRaises(ValueError):validate_config({**base,'bounds':{'height':[20,100]}})

if __name__=='__main__':unittest.main()
