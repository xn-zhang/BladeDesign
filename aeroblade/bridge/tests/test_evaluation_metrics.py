import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from evaluation.metrics import extract,wrap_angle

class MetricTests(unittest.TestCase):
    def fixture(self):
        return {name:{'p':[100000.,100000.],'T':[300.,300.],'U':[[10.,0,0],[10.,0,0]],'Sf':[[sign*.005,0,0]]*2} for name,sign in [('inlet',-1),('outlet',1)]}
    def calc(self,p,span=.01):return extract(p,span,1,{'inletTotalPressure':100200,'outletStaticPressure':100000},{'Rgas':287,'gamma':1.4})
    def test_straight_flow_and_actual_span_scaling(self):
        p=self.fixture();r=self.calc(p)
        self.assertAlmostEqual(r['values']['loss_coefficient'],0)
        self.assertAlmostEqual(r['values']['outlet_angle_deg'],0)
        self.assertAlmostEqual(r['values']['mass_flow_per_span'],100000/287/300*10)
        self.assertIsNone(r['values']['pressure_force_x_coefficient'])
        for patch in p.values():patch['Sf']=(2*np.asarray(patch['Sf'])).tolist()
        self.assertAlmostEqual(self.calc(p,.02)['values']['mass_flow_per_span'],r['values']['mass_flow_per_span'])
    def test_pressure_force_sign_reference_cancellation_and_phi_not_used_as_weights(self):
        p=self.fixture();p['blade']={'p':[100000.,100000.,100000.,100000.],'Sf':[[.01,0,0],[-.01,0,0],[0,.01,0],[0,-.01,0]]}
        self.assertAlmostEqual(self.calc(p)['values']['pressure_force_x_coefficient'],0)
        p['blade']['p'][0]+=200
        self.assertAlmostEqual(self.calc(p)['values']['pressure_force_x_coefficient'],1)
        before=self.calc(p)['values'];p['inlet']['phi']=[-1,-2];p['outlet']['phi']=[1,2]
        self.assertEqual(self.calc(p)['values'],before)
    def test_reject_backflow_negative_temperature_and_small_pressure_drop(self):
        p=self.fixture();p['outlet']['U'][0][0]=-10
        with self.assertRaises(ValueError):self.calc(p)
        p=self.fixture();p['inlet']['T'][0]=-1
        with self.assertRaises(ValueError):self.calc(p)
    def test_angle_wrap(self):self.assertEqual(wrap_angle(-358),2)

if __name__=='__main__':unittest.main()
