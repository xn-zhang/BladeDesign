import unittest,tempfile,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from session_store import StateStore,AuthError
from personal_store import PersonalStore
class PersonalTests(unittest.TestCase):
 def setUp(self):
  self.s=StateStore();self.s.create_admin('admin','test-password-123');self.a=self.s.admin_id();self.b=self.s.register('bob','test-password-123',self.s.create_invite(self.a)['code'],'test')['id'];self.p=PersonalStore(self.s)
 def tearDown(self):self.s.close()
 def test_owner_and_quota(self):
  payload={'schema':'aeroblade-saved-conversation-v1','messages':[{'role':'user','content':'hello'}],'provider':'demo','candidate':None,'draft':''}
  item=self.p.save(self.a,'conversations','first',payload)
  self.assertEqual(self.p.list(self.b,'conversations'),[])
  for op in [lambda:self.p.get(self.b,'conversations',item['id']),lambda:self.p.delete(self.b,'conversations',item['id']),lambda:self.p.rename(self.b,'conversations',item['id'],'changed'),lambda:self.p.save(self.b,'conversations','overwrite',payload,item['id'])]:
   with self.assertRaises(KeyError):op()
  self.assertEqual(self.p.get(self.a,'conversations',item['id'])['payload'],payload)
  for i in range(49):self.p.save(self.a,'conversations',str(i),payload)
  with self.assertRaises(ValueError):self.p.save(self.a,'conversations','full',payload)
  self.p.rename(self.a,'conversations',item['id'],'renamed')
 def test_invalid_payload(self):
  with self.assertRaises(ValueError):self.p.save(self.a,'conversations','secret',{'api_key':'secret'})
  with self.assertRaises(ValueError):self.p.save(self.a,'designs','bad',{'schema':'aeroblade-saved-design-v1','parameters':{},'conditions':{},'notes':''})
if __name__=='__main__':unittest.main()
