import unittest,sys,pathlib,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from evaluation.regression import split_groups,standardize,errors,domain_report

class RegressionTests(unittest.TestCase):
    def test_groups_never_leak(self):
        rows=[{'geometry_group':str(i//2)} for i in range(40)]
        split=split_groups(rows,7)
        groups=[{rows[i]['geometry_group'] for i in split[k]} for k in ('train','validation','test')]
        self.assertTrue(all(groups));self.assertFalse(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
        self.assertEqual(sum(map(len,split.values())),40)
    def test_smoke_no_false_test_score(self):
        split=split_groups([{'geometry_group':str(i)} for i in range(3)],7)
        self.assertEqual([len(split[k]) for k in ('train','validation','test')],[2,1,0])
        with self.assertRaises(ValueError):split_groups([{'geometry_group':'a'}],7)
    def test_training_only_scaler_and_constant_domain(self):
        mean,scale=standardize(np.array([[1.,2.],[3.,2.]]))
        np.testing.assert_allclose(mean,[2,2]);np.testing.assert_allclose(scale,[1,1])
        report=domain_report([2,3],[[1,2],[3,2]],['a','b'],mean,scale)
        self.assertEqual(report['outside_features'],['b']);self.assertFalse(report['in_domain'])
    def test_circular_error(self):
        e=errors(np.array([[0,179,179,0,0,0]]),np.array([[0,-179,-179,0,0,0]]))
        self.assertEqual(e['outlet_angle_deg']['mae'],2)

if __name__=='__main__':unittest.main()
