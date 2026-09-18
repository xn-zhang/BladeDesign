"""Process fixtures validate orchestration only. They are NOT OpenFOAM/CFD validation."""
import unittest,tempfile,pathlib,sys,os,time,json
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import core
from test_core import template,PARAMS
class PipelineTests(unittest.TestCase):
    def exercise(self,mesh_ok=True,wait_solver=False,cancel=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);tpl=root/'templates'/'fixture';tpl.mkdir(parents=True);template(tpl);bins=root/'bin';bins.mkdir()
            script='''#!/usr/bin/env python3
import pathlib,sys,time
name=pathlib.Path(sys.argv[0]).name
print('fixture command '+name,flush=True)
if name=='checkMesh': print(MESH_TEXT,flush=True)
if name=='rhoSimpleFoam':
 print('Time = 1\\nGAMG: Solving for p, Initial residual = 0.01, Final residual = 0.0001, No Iterations 2',flush=True)
 WAIT
 print('End',flush=True)
'''.replace('MESH_TEXT',repr('Mesh OK.' if mesh_ok else 'Failed 1 mesh checks.')).replace(' WAIT',' time.sleep(20)' if wait_solver else ' pass')
            for name in ['blockMesh','snappyHexMesh','checkMesh','rhoSimpleFoam','foamToVTK']:
                path=bins/name;path.write_text(script);path.chmod(0o755)
            with patch.dict(os.environ,{'PATH':str(bins)+os.pathsep+os.environ['PATH']}):
                m=core.Manager(root/'jobs',root/'templates',timeout=30)
                try:
                    j=m.submit({'schema':'aeroblade-cfd-v1','template_id':'test-cascade','parameters':PARAMS,'conditions':{'pt':200000,'po':100000,'iterations':500}})
                    deadline=time.time()+8
                    while time.time()<deadline:
                        result=m.get(j['id'])
                        if cancel and result['stage']=='rhoSimpleFoam':m.cancel(j['id']);cancel=False
                        if result['status'] in core.TERMINAL:break
                        time.sleep(.05)
                    result=m.detail(j['id'])
                    if result['status'] not in core.TERMINAL:m.cancel(j['id']);self.fail('Task did not terminate')
                    return result
                finally:m.pool.shutdown(wait=True)
    def test_process_success_is_not_reported_as_convergence(self):
        r=self.exercise();self.assertEqual(r['status'],'completed');self.assertEqual(r['convergence'],'not_confirmed');self.assertTrue(r['artifact_ready']);self.assertEqual(r['residuals'][0]['initial'],.01)
    def test_bad_mesh_blocks_solver_even_when_check_exits_zero(self):
        r=self.exercise(mesh_ok=False);self.assertEqual(r['status'],'failed');self.assertEqual(r['stage'],'checkMesh');self.assertNotIn('fixture command rhoSimpleFoam',r['log_tail']);self.assertFalse(r['artifact_ready'])
    def test_cancellation_terminates_running_process(self):
        r=self.exercise(wait_solver=True,cancel=True);self.assertEqual(r['status'],'cancelled');self.assertFalse(r['artifact_ready'])
if __name__=='__main__':unittest.main()
