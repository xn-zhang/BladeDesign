"""Run locally, on a private HTTP LAN, or behind an HTTPS reverse proxy. Python 3.10+, no pip dependencies."""
import signal
from http.cookies import SimpleCookie, CookieError
import argparse, hmac, http.server, json, mimetypes, os, pathlib, re, shutil, urllib.parse
from core import Manager, ROOT, QueueFullError
from design_assistant import ModelService, ModelError
from session_store import StateStore, AuthError, COOKIE_NAME, SESSION_SECONDS

from deployment_origin import validate_public_origin
from user_services import UserServices
from account_routes import dispatch as account_dispatch, fields

MAX_BODY=200_000

def make_server(host,port,manager,token,origins,model_service=None,state=None,public_origin='',allow_setup=False,evaluation=None,batches=None):
    if token and len(token)<24:raise ValueError('AEROBLADE_API_TOKEN must contain at least 24 characters')
    state=state if state is not None else StateStore()
    models = model_service if model_service is not None else ModelService(store=state)
    services=UserServices(state,models,manager,evaluation,batches)
    origins=set(origins)
    if public_origin:origins.add(public_origin)
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version='AeroBladeBridge/1'
        def setup(self):super().setup();self.connection.settimeout(20)
        def log_message(self,format,*args):pass
        def common(self):
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            origin=self.headers.get('Origin')
            if origin in origins:self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')
            if origin in origins:self.send_header('Access-Control-Allow-Credentials','true')
        def session_token(self):
            try:
                cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ''
            except CookieError:return ''
        def cookie(self,value,clear=False):
            self.session_cookie=f'{COOKIE_NAME}={value}; Path=/api; HttpOnly; SameSite=Lax; Max-Age={0 if clear else SESSION_SECONDS}'+('; Secure' if public_origin.startswith('https://') else '')
        def send_json(self,data,status=200):
            body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode();self.send_response(status);self.common();self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)))
            if getattr(self,'session_cookie',None):self.send_header('Set-Cookie',self.session_cookie)
            self.end_headers();self.wfile.write(body)
        def authorized(self):
            origin=self.headers.get('Origin')
            if origin and origin not in origins:self.send_json({'error':'Origin is not allowed'},403);return False
            actual=self.headers.get('Authorization','')
            if token and hmac.compare_digest(actual.encode(),('Bearer '+token).encode()):
                path=urllib.parse.urlsplit(self.path).path
                if path not in ('/api/health','/api/scheduler','/api/jobs') and not path.startswith('/api/jobs/'):
                    self.send_json({'error':'计算令牌不能访问账号或模型配置'},403);return False
                self.principal={'user_id':state.admin_id(),'role':'admin','machine':True};return True
            session=state.session(self.session_token())
            if not session:self.send_json({'error':'请登录平台后继续','code':'login_required'},401);return False
            if self.command!='GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token','').encode(),session['csrf'].encode()):
                self.send_json({'error':'会话校验失败，请刷新页面后重试','code':'csrf_failed'},403);return False
            self.principal=session
            return True
        def do_OPTIONS(self):
            if self.headers.get('Origin') not in origins:self.send_json({'error':'Origin is not allowed'},403);return
            self.send_response(204);self.common();self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-CSRF-Token');self.send_header('Content-Length','0');self.end_headers()
        def body(self,limit=MAX_BODY):
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Content-Type must be application/json')
            raw=self.headers.get('Content-Length','')
            if not raw.isdigit() or not 0<int(raw)<=limit:raise ValueError('Invalid request body length')
            return json.loads(self.rfile.read(int(raw)),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
        def send_file(self,path,name=None):
            if not path.is_file():raise KeyError('File unavailable')
            self.send_response(200);self.common();self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream');self.send_header('Content-Length',str(path.stat().st_size))
            if name:self.send_header('Content-Disposition','attachment; filename="'+name+'"')
            self.end_headers()
            with path.open('rb') as f:shutil.copyfileobj(f,self.wfile,1024*256)
        def dispatch(self):
            path=urllib.parse.urlsplit(self.path).path
            if not path.startswith('/api/'):
                if self.command!='GET':self.send_json({'error':'Not found'},404);return
                # Only deployable public assets; never serve bridge source, jobs or templates.
                allow={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js','/geometry.js':'geometry.js','/pritchard.js':'pritchard.js','/legacy-geometry.js':'legacy-geometry.js','/cfd.js':'cfd.js','/cfd.css':'cfd.css','/workspace.css':'workspace.css','/flow-view.js':'flow-view.js','/ai.js':'ai.js','/ai.css':'ai.css','/aeroblade.zip':'aeroblade.zip'}
                for name in ('design-assistant.js','design-assistant-client.js','design-assistant.css','model-settings.js','model-settings.css'):
                    allow['/'+name]=name
                for name in ('deployment-origin.js','session.js','session.css','session-state.js','account-admin.js','personal-workspace.js','personal-workspace.css','evaluation.js','evaluation.css','batch.js','batch-state.js','batch.css'):allow['/'+name]=name
                if path not in allow:raise KeyError('Not found')
                self.send_file(ROOT/('dist' if path=='/aeroblade.zip' else 'web')/allow[path]);return
            if path in ('/api/session','/api/session/login','/api/session/setup','/api/session/logout','/api/session/register'):
                origin=self.headers.get('Origin')
                if (origin and origin not in origins) or (self.command=='POST' and origin not in origins):
                    self.send_json({'error':'Origin is not allowed'},403);return
                session=state.session(self.session_token())
                local_hosts={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
                setup_allowed=allow_setup and not public_origin and self.client_address[0] in ('127.0.0.1','::1') and self.headers.get('Host') in local_hosts
                if self.command=='GET' and path=='/api/session':
                    self.send_json({'authenticated':bool(session),**(session or {'username':None,'user_id':None,'role':None,'csrf':None}),'setup_required':not state.initialized(),'setup_allowed':setup_allowed});return
                if self.command=='POST' and path in ('/api/session/login','/api/session/setup','/api/session/register'):
                    data=self.body()
                    fields(data,('username','password','invite') if path.endswith('/register') else ('username','password'))
                    if path.endswith('/register'):state.register(data['username'],data['password'],data['invite'],self.client_address[0])
                    if path.endswith('/setup'):
                        if not setup_allowed or origin not in {'http://'+name for name in local_hosts}:raise AuthError('请在服务器启动环境中初始化管理员账号',403)
                        state.create_admin(data['username'],data['password'])
                    key,session=state.login(data['username'],data['password'],self.client_address[0])
                    self.cookie(key);self.send_json({'authenticated':True,**session});return
                if self.command=='POST' and path.endswith('/logout'):
                    if not self.authorized():return
                    state.logout(self.session_token());self.cookie('',clear=True);self.send_json({'authenticated':False});return
                raise KeyError('Not found')
            if not self.authorized():return
            principal=self.principal
            if not principal.get('machine'):
                if account_dispatch(self,path,principal,state,services):return
                owned=services.for_user(principal,compute=path.startswith(('/api/evaluation/','/api/batches')))
            else:owned={'models':None,'evaluation':None,'batches':None}
            user_models=owned['models'];user_evaluation=owned['evaluation'];user_batches=owned['batches']
            if principal['role']!='admin' and (path.startswith('/api/jobs') or path=='/api/scheduler'):
                raise AuthError('共享 CFD 计算仅管理员可用',403)
            if path.startswith('/api/batches'):
                if user_batches is None:raise ValueError('批次服务未启动，请使用新版完整bridge')
                if self.command=='GET' and path=='/api/batches/designs':self.send_json({'designs':user_batches.designs()});return
                design_match=re.fullmatch(r'/api/batches/designs/([a-f0-9]{24})',path)
                if self.command=='GET' and design_match:self.send_json(user_batches.design(design_match[1]));return
                if path=='/api/batches':
                    if self.command=='GET':self.send_json({'batches':user_batches.list(),'cfd_ready':bool(user_batches.manager and user_batches.manager.health().get('ready'))});return
                    if self.command=='POST':
                        data=self.body()
                        if not isinstance(data,dict) or set(data)!={'design_batch_id'}:raise ValueError('只接受已校验参数包编号')
                        self.send_json(user_batches.create(data['design_batch_id']),201);return
                match=re.fullmatch(r'/api/batches/([a-f0-9]{32})(?:/(start|pause|resume|cancel|retry))?',path)
                if match:
                    bid,action=match.groups()
                    if self.command=='GET' and action is None:self.send_json(user_batches.get(bid));return
                    if self.command=='POST' and action:self.send_json(user_batches.control(bid,action,self.body()));return
                raise KeyError('Not found')
            if path.startswith('/api/evaluation/'):
                if user_evaluation is None:self.send_json({'error':'当前部署未启动评估计算服务，请使用新版Python bridge'},503);return
                endpoint=path.removeprefix('/api/evaluation/')
                if self.command=='GET' and endpoint=='capabilities':self.send_json(user_evaluation.capabilities());return
                if self.command=='GET' and endpoint in ('datasets','models','tasks'):self.send_json({endpoint:user_evaluation.catalog(endpoint)});return
                if self.command=='POST' and endpoint in ('dataset','train','predict','analyze','evaluate','optimize','batch_generate','batch_import'):self.send_json(user_evaluation.submit(endpoint,self.body(2_500_000 if endpoint=='batch_import' else MAX_BODY)),202);return
                match=re.fullmatch(r'tasks/([a-f0-9]{32})(?:/(cancel|pause|resume))?',endpoint)
                if match:
                    tid,action=match.groups()
                    if self.command=='GET' and action is None:self.send_json(user_evaluation.get(tid));return
                    if self.command=='POST' and action:
                        if self.body()!={}:raise ValueError('控制操作不接受附加字段')
                        self.send_json(user_evaluation.control(tid,action));return
                raise KeyError('Not found')
            if path=='/api/design-assistant/config':
                if self.command=='GET':self.send_json(user_models.describe());return
                if self.command=='POST':self.send_json(user_models.configure(self.body()));return
            if self.command=='POST' and path=='/api/design-assistant/test':self.send_json(user_models.test(self.body()));return
            if self.command=='POST' and path=='/api/design-assistant/clear':
                data=self.body()
                if not isinstance(data,dict) or set(data)!={'provider'}:raise ValueError('只允许指定 provider')
                self.send_json(user_models.clear(data['provider']));return
            if self.command=='POST' and path=='/api/design-assistant/chat':self.send_json(user_models.chat(self.body(2_500_000)));return
            if self.command=='POST' and path=='/api/design-assistant/batch-plan':self.send_json(user_models.batch_plan(self.body()));return
            if self.command=='GET' and path=='/api/health':self.send_json(manager.health() if manager is not None and principal['role']=='admin' else {'api':'aeroblade-model-v1','ready':True,'model_only':True});return
            if manager is None:self.send_json({'error':'此后端仅提供模型服务，请连接独立 CFD 计算服务'},503);return
            if path=='/api/scheduler':
                if self.command=='GET':self.send_json(manager.scheduler());return
                if self.command=='POST':
                    data=self.body()
                    if not isinstance(data,dict) or set(data)!={'max_parallel'}:raise ValueError('只允许设置 max_parallel')
                    self.send_json(manager.configure(data['max_parallel']));return
            if path=='/api/jobs':
                if self.command=='GET':self.send_json({'jobs':manager.list(),'scheduler':manager.scheduler()});return
                if self.command=='POST':self.send_json(manager.submit(self.body()),202);return
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(cancel|artifacts|flow))?',path)
            if match:
                id,action=match.groups()
                if self.command=='GET' and action is None:self.send_json(manager.detail(id));return
                if self.command=='POST' and action=='cancel':self.send_json(manager.cancel(id));return
                if self.command=='GET' and action=='flow':
                    if manager.get(id)['status']!='completed':raise ValueError('任务尚未完成，完成后显示真实流场')
                    from flow import load_flow
                    data=load_flow(manager.root/id/'case');data['job_id']=id
                    self.send_json(data);return
                if self.command=='GET' and action=='artifacts':
                    if manager.get(id)['status']!='completed':raise ValueError('Results are not ready')
                    self.send_file(manager.root/id/'results.zip','aeroblade-'+id[:8]+'-results.zip');return
            raise KeyError('Not found')
        def handle_request(self):
            try:self.dispatch()
            except KeyError:self.send_json({'error':'Not found'},404)
            except QueueFullError as e:self.send_json({'error':str(e)},429)
            except ModelError as e:self.send_json({'error':str(e)},e.status)
            except AuthError as e:self.send_json({'error':str(e)},e.status)
            except (ValueError,TypeError) as e:self.send_json({'error':str(e)[:1000]},400)
            except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
            except Exception:self.send_json({'error':'Internal bridge error; inspect server configuration'},500)
        do_GET=handle_request
        do_POST=handle_request
    httpd=http.server.ThreadingHTTPServer((host,port),Handler)
    if host in ('127.0.0.1','localhost','::1'):
        origins.update({'http://127.0.0.1:'+str(httpd.server_port),'http://localhost:'+str(httpd.server_port)})
    original_close=httpd.server_close
    def close_server():
        original_close();services.close()
    httpd.server_close=close_server
    httpd.user_services=services
    httpd.state_store=state
    return httpd

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8787);parser.add_argument('--templates',type=pathlib.Path,default=ROOT/'templates');parser.add_argument('--jobs',type=pathlib.Path,default=ROOT/'jobs');parser.add_argument('--timeout',type=int,default=7200);parser.add_argument('--max-parallel',type=int,default=2);parser.add_argument('--max-pending',type=int,default=16);parser.add_argument('--case-threads',type=int,default=1)
    parser.add_argument('--data-dir',type=pathlib.Path,default=pathlib.Path(os.environ.get('AEROBLADE_DATA_DIR',str(ROOT/'private'))))
    parser.add_argument('--model-only',action='store_true',help='Run login and model services without a CFD manager')
    parser.add_argument('--evaluation-dir',type=pathlib.Path,default=pathlib.Path(os.environ.get('AEROBLADE_EVALUATION_DIR',str(ROOT/'ai-data'))))
    args=parser.parse_args()
    if args.timeout<60 or args.timeout>172800:parser.error('--timeout must be 60–172800 seconds')
    token=os.environ.get('AEROBLADE_API_TOKEN','')
    if token and len(token)<24:parser.error('AEROBLADE_API_TOKEN must contain at least 24 characters when configured')
    public_origin=os.environ.get('AEROBLADE_PUBLIC_ORIGIN','').rstrip('/')
    if public_origin:
        try:validate_public_origin(public_origin)
        except ValueError as e:parser.error(str(e))
    if args.host not in ('127.0.0.1','localhost','::1') and not public_origin:parser.error('Set AEROBLADE_PUBLIC_ORIGIN to the browser origin (HTTPS or private-IP HTTP) for remote deployment')
    state=StateStore(args.data_dir/'state.sqlite3')
    if not state.initialized() and os.environ.get('AEROBLADE_ADMIN_PASSWORD'):
        try:state.create_admin(os.environ.get('AEROBLADE_ADMIN_USERNAME','admin'),os.environ['AEROBLADE_ADMIN_PASSWORD'])
        except AuthError as e:parser.error(str(e))
    if (public_origin or args.host not in ('127.0.0.1','localhost','::1')) and not state.initialized():parser.error('Initialize AEROBLADE_ADMIN_USERNAME and AEROBLADE_ADMIN_PASSWORD before remote deployment')
    origins={s.strip().rstrip('/') for s in os.environ.get('AEROBLADE_ALLOWED_ORIGINS','').split(',') if s.strip()}
    origins.update({'http://127.0.0.1:'+str(args.port),'http://localhost:'+str(args.port)})
    from package import package
    if not (ROOT/'dist/aeroblade.zip').is_file():package()
    try:manager=None if args.model_only else Manager(args.jobs,args.templates,args.timeout,max_parallel=args.max_parallel,max_pending=args.max_pending,case_threads=args.case_threads)
    except ValueError as e:parser.error(str(e))
    from evaluation_service import EvaluationService
    evaluation=EvaluationService(args.evaluation_dir,args.jobs,manager)
    from batch_service import BatchService
    batches=BatchService(args.evaluation_dir,manager);evaluation.batch_service=batches
    http=make_server(args.host,args.port,manager,token,origins,state=state,public_origin=public_origin,allow_setup=not public_origin and args.host in ('127.0.0.1','localhost','::1'),evaluation=evaluation,batches=batches)
    print('AeroBlade bridge listening on '+args.host+':'+str(args.port),flush=True)
    print('Authentication: browser session; model configuration: private persistent database',flush=True)
    if manager is not None:print(json.dumps(manager.health(),ensure_ascii=False),flush=True)
    def stop(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        http.server_close()
        batches.shutdown()
        evaluation.shutdown()
        if manager is not None:manager.shutdown()
        state.close()
if __name__=='__main__':main()
