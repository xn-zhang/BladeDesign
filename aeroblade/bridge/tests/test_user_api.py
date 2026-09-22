import unittest,json,urllib.request,http.cookiejar,urllib.error,threading,tempfile,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from session_store import StateStore
from server import make_server
from types import SimpleNamespace
class UserAPITests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=StateStore(pathlib.Path(self.tmp.name)/'state.sqlite3');self.s.create_admin('admin','test-password-123')
  self.http=make_server('127.0.0.1',0,SimpleNamespace(health=lambda:{'ready':True}),'',set(),state=self.s);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.http.server_port}'
  self.clients={n:urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) for n in ('admin','alice','bob')};self.csrf={}
 def tearDown(self):
  self.http.shutdown();self.http.server_close()
  if hasattr(self.http,'user_services'):self.http.user_services.close()
  self.s.close();self.tmp.cleanup()
 def req(self,who,path,data=None):
  h={'Origin':self.base,'X-CSRF-Token':self.csrf.get(who,'')}
  if data is not None:h['Content-Type']='application/json'
  request=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=h)
  try:
   with self.clients[who].open(request) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def test_registration_roles_and_isolated_config(self):
  code,data=self.req('admin','/api/session/login',{'username':'admin','password':'test-password-123'});self.assertEqual(code,200);self.csrf['admin']=data['csrf']
  for name in ('alice','bob'):
   status,inv=self.req('admin','/api/admin/invites',{});self.assertEqual(status,200)
   code,data=self.req(name,'/api/session/register',{'username':name,'password':'test-password-123','invite':inv['code']});self.assertEqual(code,200);self.assertEqual(data['role'],'user');self.csrf[name]=data['csrf']
  self.assertEqual(self.req('alice','/api/admin/invites',{})[0],403)
  cfg={'provider':'general','base_url':'https://model.example/v1','model':'alice-model','api_key':'alice-only-key'}
  self.assertEqual(self.req('alice','/api/design-assistant/config',cfg)[0],200)
  self.assertFalse(self.req('bob','/api/design-assistant/config')[1]['providers']['general']['configured'])
  self.assertEqual(self.req('alice','/api/design-assistant/config',{**cfg,'base_url':'http://127.0.0.1:8787'})[0],400)
  self.assertEqual(self.req('alice','/api/jobs')[0],403)
  self.assertFalse(self.req('alice','/api/batches')[1]['cfd_ready'])
  self.assertTrue(self.req('alice','/api/health')[1]['model_only'])
  payload={'schema':'aeroblade-saved-conversation-v1','messages':[],'provider':'demo','candidate':None,'draft':'hello'}
  status,item=self.req('alice','/api/personal/conversations',{'name':'mine','payload':payload});self.assertEqual(status,200)
  self.assertEqual(self.req('bob','/api/personal/conversations/'+item['id'])[0],404)
  self.assertEqual(self.req('bob','/api/personal/conversations')[1]['items'],[])
  users=self.req('admin','/api/admin/users')[1]['users'];uid=next(u['id'] for u in users if u['username']=='alice')
  self.assertEqual(self.req('admin','/api/admin/users/'+uid+'/status',{'disabled':True})[0],200)
  self.assertEqual(self.req('alice','/api/design-assistant/config')[0],401)
if __name__=='__main__':unittest.main()
