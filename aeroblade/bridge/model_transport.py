"""Public HTTPS transport: validated DNS addresses are pinned to the TLS socket."""
import http.client,ipaddress,socket,ssl,urllib.parse,urllib.error

def validate_public_url(value):
    u=urllib.parse.urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username is not None or u.password is not None or u.query or u.fragment:raise ValueError('普通账号仅支持无凭据的公网 HTTPS 模型地址')
    port=u.port or 443
    try:ip=ipaddress.ip_address(u.hostname)
    except ValueError:ip=None
    if (ip is not None and not ip.is_global) or u.hostname.lower()=='localhost':raise ValueError('模型地址不能访问本机或私有网络')
    return u,port

def resolve_public(host,port):
    addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('模型域名不能指向私有或保留地址')
    return addresses

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,host,port,*,addresses,timeout):
        super().__init__(host,port,timeout=timeout,context=ssl.create_default_context());self.addresses=addresses
    def connect(self):
        last=None
        for family,kind,proto,_,address in self.addresses:
            raw=socket.socket(family,kind,proto)
            try:
                raw.settimeout(self.timeout);raw.connect(address)
                self.sock=self._context.wrap_socket(raw,server_hostname=self.host);return
            except OSError as e:last=e;raw.close()
        raise last or OSError('No public address')
class Response:
    def __init__(self,response,connection):self.response=response;self.connection=connection
    def read(self,size=-1):return self.response.read(size)
    def close(self):self.response.close();self.connection.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
class PublicModelTransport:
    def validate_url(self,url):validate_public_url(url)
    def open(self,request,timeout=45):
        u,port=validate_public_url(request.full_url)
        addresses=resolve_public(u.hostname,port)
        conn=PinnedHTTPSConnection(u.hostname,port,addresses=addresses,timeout=timeout)
        try:
            headers=dict(request.header_items());headers['Host']=u.netloc;headers['Connection']='close'
            conn.request(request.get_method(),u.path or '/',body=request.data,headers=headers)
            response=conn.getresponse()
            if not 200<=response.status<300:
                status=response.status;response.close();raise urllib.error.HTTPError(request.full_url,status,'Model upstream rejected request',{},None)
            return Response(response,conn)
        except Exception:conn.close();raise
