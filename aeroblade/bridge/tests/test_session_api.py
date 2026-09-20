import http.cookiejar
import json
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from server import make_server
from session_store import StateStore


class SessionAPITests(unittest.TestCase):
    def setUp(self):
        self.store=StateStore()
        self.http=make_server('127.0.0.1',0,None,'',set(),state=self.store,allow_setup=True)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def tearDown(self):self.http.shutdown();self.http.server_close();self.store.close()
    def request(self,path,data=None,csrf='',origin=None):
        headers={'Origin':origin or self.base}
        if csrf:headers['X-CSRF-Token']=csrf
        if data is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with self.client.open(req) as r:return r.status,dict(r.headers),json.load(r)
        except urllib.error.HTTPError as e:
            with e:return e.code,dict(e.headers),json.load(e)
    def setup_account(self):
        return self.request('/api/session/setup',{'username':'admin','password':'fixture-password-123'})
    def test_first_setup_cookie_config_csrf_logout(self):
        self.assertEqual(self.request('/api/design-assistant/config')[0],401)
        self.assertTrue(self.request('/api/session')[2]['setup_required'])
        code,headers,data=self.setup_account();self.assertEqual(code,200)
        self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Lax',headers['Set-Cookie'])
        self.assertTrue(self.request('/api/session')[2]['authenticated'])
        self.assertEqual(self.request('/api/design-assistant/config')[0],200)
        cfg={'provider':'general','base_url':'http://127.0.0.1:1234/v1','model':'fixture','auth':'none'}
        self.assertEqual(self.request('/api/design-assistant/config',cfg)[0],403)
        self.assertEqual(self.request('/api/design-assistant/config',cfg,csrf=data['csrf'])[0],200)
        self.assertEqual(self.request('/api/session/logout',{},csrf=data['csrf'])[0],200)
        self.assertEqual(self.request('/api/design-assistant/config')[0],401)
    def test_wrong_origin_and_missing_password_rejected(self):
        self.assertEqual(self.request('/api/session/setup',{'username':'admin','password':'fixture-password-123'},origin='https://evil.example')[0],403)
        self.assertEqual(self.request('/api/session/login',{'username':'admin','password':'wrong'})[0],401)
    def test_model_only_health_and_no_compute_manager(self):
        self.setup_account()
        self.assertTrue(self.request('/api/health')[2]['model_only'])
        self.assertEqual(self.request('/api/jobs')[0],503)
    def test_public_deployment_disallows_setup_and_sets_secure_cookie(self):
        self.http.shutdown();self.http.server_close()
        self.store.create_admin('admin','fixture-password-123')
        self.http=make_server('127.0.0.1',0,None,'',set(),state=self.store,public_origin='https://app.example',allow_setup=True)
        threading.Thread(target=self.http.serve_forever,daemon=True).start();self.base=f'http://127.0.0.1:{self.http.server_port}'
        self.assertEqual(self.request('/api/session/setup',{'username':'admin','password':'fixture-password-123'},origin='https://app.example')[0],403)
        code,headers,_=self.request('/api/session/login',{'username':'admin','password':'fixture-password-123'},origin='https://app.example')
        self.assertEqual(code,200);self.assertIn('; Secure',headers['Set-Cookie'])

if __name__=='__main__':unittest.main()
