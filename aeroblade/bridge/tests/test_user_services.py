import unittest,tempfile,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from session_store import StateStore
from design_assistant import ModelService
from user_services import UserServices
class ServicesTests(unittest.TestCase):
 def test_owned_directories_models_and_reenable(self):
  with tempfile.TemporaryDirectory() as d:
   state=StateStore(pathlib.Path(d)/'state.sqlite3');state.create_admin('admin','fixture-password-123')
   admin=state.admin_id();registry=UserServices(state,ModelService(environ={},store=state))
   try:
    ids=[]
    for name in ('alice','bob'):
     u=state.register(name,'fixture-password-123',state.create_invite(admin)['code'],'test');ids.append(u['id'])
    a=registry.for_user({'user_id':ids[0]},compute=True);b=registry.for_user({'user_id':ids[1]},compute=True)
    self.assertNotEqual(a['evaluation'].root,b['evaluation'].root);self.assertIsNone(a['evaluation'].manager)
    a['models'].configure({'provider':'general','base_url':'https://model.example/v1','model':'only-a','api_key':'only-a-key'})
    self.assertFalse(b['models'].describe()['providers']['general']['configured'])
    with self.assertRaises(KeyError):b['evaluation'].get('a'*32)
    state.set_disabled(admin,ids[0],True);registry.disable(ids[0]);state.set_disabled(admin,ids[0],False)
    restored=registry.for_user({'user_id':ids[0]});self.assertTrue(restored['models'].describe()['providers']['general']['configured'])
   finally:registry.close();state.close()
if __name__=='__main__':unittest.main()
