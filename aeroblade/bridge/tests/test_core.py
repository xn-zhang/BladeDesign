import unittest, tempfile, json, pathlib, sys, os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import core

PARAMS={'chord':50,'thickness':16,'position':35,'inlet':48,'outlet':-42,'stagger':22,'height':90,'taper':.76,'twist':-18,'sweep':7,'lean':5}

def template(root):
    root.mkdir(exist_ok=True)
    for d in ['0','system','constant']:(root/d).mkdir(exist_ok=True)
    (root/'system/controlDict').write_text('endTime {{ITERATIONS}};')
    (root/'0/p').write_text('p0 {{PT_IN}}; p {{P_OUT}};')
    manifest={'id':'test-cascade','name':'Test cascade','solver':'rhoSimpleFoam','description':'Test fixture, not a CFD-validated case','geometry_file':'constant/triSurface/blade.stl','geometry_bounds_m':[[-.2,-.2,-.2],[.2,.2,.2]],'inputs':[{'key':'pt','label':'入口总压','unit':'Pa','min':100000,'max':1000000,'default':200000,'token':'PT_IN'},{'key':'po','label':'出口静压','unit':'Pa','min':10000,'max':1000000,'default':100000,'token':'P_OUT'},{'key':'iterations','label':'迭代上限','unit':'','min':10,'max':5000,'default':500,'token':'ITERATIONS','integer':True}],'constraints':[{'left':'pt','op':'>','right':'po'}],'pipeline':[['blockMesh'],['snappyHexMesh','-overwrite'],['checkMesh'],['rhoSimpleFoam'],['foamToVTK','-latestTime']]}
    (root/'aeroblade-template.json').write_text(json.dumps(manifest))
    return manifest

class CoreTests(unittest.TestCase):
    def test_template_design_rejects_twist_and_taper(self):
        tpl={'parameter_bounds':{'twist':[0,0],'taper':[1,1]}}
        with self.assertRaises(ValueError): core.validate_template_design(tpl,PARAMS)
        straight=dict(PARAMS,twist=0,taper=1)
        self.assertEqual(core.validate_template_design(tpl,straight),straight)
        self.assertEqual(core.validate_template_design({},PARAMS),PARAMS)
    def test_template_rejects_invalid_parameter_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp); m=template(t)
            m['parameter_bounds']={'twist':[10,-10]}
            (t/'aeroblade-template.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):core.load_template(t)
    def test_extrusion_and_periodic_patch_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp);m=template(t)
            m['pipeline']=[['blockMesh'],['snappyHexMesh','-overwrite'],['extrudeMesh'],['createPatch','-overwrite'],['checkMesh','-allTopology','-meshQuality'],['rhoSimpleFoam']]
            (t/'aeroblade-template.json').write_text(json.dumps(m))
            self.assertEqual(core.load_template(t)['pipeline'],m['pipeline'])
            m['pipeline'][3],m['pipeline'][4]=m['pipeline'][4],m['pipeline'][3]
            (t/'aeroblade-template.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):core.load_template(t)
    def test_extrusion_refuses_unmatched_source_before_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=pathlib.Path(tmp);p=case/'constant/polyMesh/boundary';p.parent.mkdir(parents=True)
            original='inlet {type patch;} low {type cyclic;} blade {type wall;}'
            p.write_text(original)
            with self.assertRaises(ValueError):core.prepare_extrusion(case)
            self.assertEqual(p.read_text(),original)
            p.write_text(original+' high {type cyclic;}')
            core.prepare_extrusion(case)
            self.assertIn('blade {type wall;}',p.read_text())
            self.assertNotIn('type cyclic;',p.read_text())
    def test_bridge_core_exists(self): self.assertTrue(hasattr(core,'load_template'),'template-aware bridge has not been implemented')
    def test_residuals_are_parsed_from_actual_log(self):
        rows=core.parse_residuals('Time = 5\nDILUPBiCGStab:  Solving for Ux, Initial residual = 0.002, Final residual = 1e-07, No Iterations 2\nGAMG:  Solving for p, Initial residual = 3E-3, Final residual = 1e-8, No Iterations 2\n')
        self.assertEqual(rows,[{'iteration':5.0,'field':'Ux','initial':.002,'final':1e-7},{'iteration':5.0,'field':'p','initial':.003,'final':1e-8}])
        self.assertEqual(core.parse_residuals('queued'),[])
    def test_prepare_uses_meters_and_freezes_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp);template(t/'template');tpl=core.load_template(t/'template');case=t/'case'
            report=core.prepare_case(tpl,{'parameters':PARAMS,'conditions':{'pt':200000,'po':100000,'iterations':500}},case)
            self.assertEqual((case/'0/p').read_text(),'p0 200000; p 100000;')
            self.assertAlmostEqual(report['bounds_m'][1][2]-report['bounds_m'][0][2],.09)
            self.assertTrue((case/'constant/triSurface/blade.stl').exists())
            self.assertEqual(json.loads((case/'aeroblade-request.json').read_text())['parameters'],PARAMS)
    def test_rejects_nonphysical_or_unknown_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp);template(t/'template');tpl=core.load_template(t/'template')
            for conditions in [{'pt':90000,'po':100000,'iterations':100},{'pt':200000,'po':100000,'iterations':100,'command':'rm'},{'pt':float('nan'),'po':100000,'iterations':100},{'pt':200000,'po':300000,'iterations':100}]:
                with self.assertRaises(ValueError):core.validate_conditions(tpl,conditions)
    def test_rejects_unsafe_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp);m=template(t);m['pipeline']=[['sh','-c','echo not-permitted']];(t/'aeroblade-template.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):core.load_template(t)
    def test_no_template_means_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=core.Manager(pathlib.Path(tmp)/'jobs',pathlib.Path(tmp)/'templates')
            self.assertFalse(manager.health()['ready'])
    def test_restart_marks_incomplete_jobs_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp);j=t/'jobs'/'0123456789abcdef0123456789abcdef';j.mkdir(parents=True)
            (j/'job.json').write_text(json.dumps({'id':j.name,'status':'running','stage':'rhoSimpleFoam'}))
            manager=core.Manager(t/'jobs',t/'templates');self.assertEqual(manager.get(j.name)['status'],'interrupted')

if __name__=='__main__':unittest.main()
