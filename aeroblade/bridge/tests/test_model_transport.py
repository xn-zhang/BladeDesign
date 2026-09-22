import unittest,sys,pathlib,socket
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from model_transport import resolve_public,PublicModelTransport
class TransportTests(unittest.TestCase):
 def test_private_addresses(self):
  for ip in ('127.0.0.1','10.1.1.1','169.254.169.254','::1','::ffff:127.0.0.1'):
   with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]):
    with self.assertRaises(ValueError):resolve_public('model.example',443)
 def test_pin_resolution_and_tls_host(self):
  import urllib.request
  with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]),patch('model_transport.PinnedHTTPSConnection') as conn:
   conn.return_value.getresponse.return_value.status=200
   PublicModelTransport().open(urllib.request.Request('https://model.example/v1',data=b'{}'),timeout=5)
   self.assertEqual(conn.call_args.args[:2],('model.example',443));self.assertEqual(conn.call_args.kwargs['addresses'][0][4][0],'8.8.8.8')
 def test_redirect_rejected(self):
  import urllib.request,urllib.error
  with patch('model_transport.resolve_public',return_value=[]),patch('model_transport.PinnedHTTPSConnection') as conn:
   conn.return_value.getresponse.return_value.status=302
   with self.assertRaises(urllib.error.HTTPError):PublicModelTransport().open(urllib.request.Request('https://model.example'))
 def test_actual_connection_pins_socket_and_checks_original_tls_name(self):
  from model_transport import PinnedHTTPSConnection
  from unittest.mock import MagicMock
  address=(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))
  context=MagicMock();raw=MagicMock()
  with patch('model_transport.ssl.create_default_context',return_value=context),patch('socket.socket',return_value=raw),patch('socket.getaddrinfo',side_effect=AssertionError('must not resolve twice')):
   connection=PinnedHTTPSConnection('model.example',443,addresses=[address],timeout=5);connection.connect()
   raw.connect.assert_called_once_with(('8.8.8.8',443));context.wrap_socket.assert_called_once_with(raw,server_hostname='model.example')
if __name__=='__main__':unittest.main()
