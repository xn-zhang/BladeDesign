"""Run behind an owner-managed HTTPS reverse proxy. Python 3.10+, no pip dependencies."""
import signal
import argparse, hmac, http.server, json, mimetypes, os, pathlib, re, shutil, urllib.parse
from core import Manager, ROOT, QueueFullError

MAX_BODY=200_000

def make_server(host,port,manager,token,origins):
    if len(token)<24:raise ValueError('AEROBLADE_API_TOKEN must contain at least 24 characters')
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version='AeroBladeBridge/1'
        def setup(self):super().setup();self.connection.settimeout(20)
        def log_message(self,format,*args):pass
        def common(self):
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            origin=self.headers.get('Origin')
            if origin in origins:self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')
        def send_json(self,data,status=200):
            body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode();self.send_response(status);self.common();self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def authorized(self):
            origin=self.headers.get('Origin')
            if origin and origin not in origins:self.send_json({'error':'Origin is not allowed'},403);return False
            actual=self.headers.get('Authorization','')
            if not hmac.compare_digest(actual,'Bearer '+token):self.send_json({'error':'Invalid API token'},401);return False
            return True
        def do_OPTIONS(self):
            if self.headers.get('Origin') not in origins:self.send_json({'error':'Origin is not allowed'},403);return
            self.send_response(204);self.common();self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type');self.send_header('Content-Length','0');self.end_headers()
        def body(self):
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Content-Type must be application/json')
            raw=self.headers.get('Content-Length','')
            if not raw.isdigit() or not 0<int(raw)<=MAX_BODY:raise ValueError('Invalid request body length')
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
                allow={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js','/geometry.js':'geometry.js','/pritchard.js':'pritchard.js','/legacy-geometry.js':'legacy-geometry.js','/cfd.js':'cfd.js','/cfd.css':'cfd.css','/workspace.css':'workspace.css','/flow-view.js':'flow-view.js','/ai.js':'ai.js','/ai.css':'ai.css','/openfoam-bridge.zip':'openfoam-bridge.zip'}
                if path not in allow:raise KeyError('Not found')
                self.send_file(ROOT/('dist' if path=='/openfoam-bridge.zip' else 'web')/allow[path]);return
            if not self.authorized():return
            if self.command=='GET' and path=='/api/health':self.send_json(manager.health());return
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
            except (ValueError,TypeError) as e:self.send_json({'error':str(e)[:1000]},400)
            except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
            except Exception:self.send_json({'error':'Internal bridge error; inspect server configuration'},500)
        do_GET=handle_request
        do_POST=handle_request
    return http.server.ThreadingHTTPServer((host,port),Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8787);parser.add_argument('--templates',type=pathlib.Path,default=ROOT/'templates');parser.add_argument('--jobs',type=pathlib.Path,default=ROOT/'jobs');parser.add_argument('--timeout',type=int,default=7200);parser.add_argument('--max-parallel',type=int,default=2);parser.add_argument('--max-pending',type=int,default=16);parser.add_argument('--case-threads',type=int,default=1);args=parser.parse_args()
    if args.timeout<60 or args.timeout>172800:parser.error('--timeout must be 60–172800 seconds')
    token=os.environ.get('AEROBLADE_API_TOKEN','')
    if len(token)<24:parser.error('Set AEROBLADE_API_TOKEN to a random token of at least 24 characters')
    origins={s.strip().rstrip('/') for s in os.environ.get('AEROBLADE_ALLOWED_ORIGINS','').split(',') if s.strip()}
    origins.update({'http://127.0.0.1:'+str(args.port),'http://localhost:'+str(args.port)})
    from package import package
    if not (ROOT/'dist/openfoam-bridge.zip').is_file():package()
    try:manager=Manager(args.jobs,args.templates,args.timeout,max_parallel=args.max_parallel,max_pending=args.max_pending,case_threads=args.case_threads)
    except ValueError as e:parser.error(str(e))
    http=make_server(args.host,args.port,manager,token,origins)
    print('AeroBlade bridge listening on '+args.host+':'+str(args.port),flush=True)
    print(json.dumps(manager.health(),ensure_ascii=False),flush=True)
    def stop(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        http.server_close();manager.shutdown()
if __name__=='__main__':main()
