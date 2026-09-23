import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from deployment_origin import validate_public_origin

class DeploymentOriginTests(unittest.TestCase):
    def test_lan_and_https(self):
        for origin in ('http://192.168.1.20:8787', 'http://10.0.0.8', 'http://172.16.0.1', 'http://172.31.255.254', 'http://127.0.0.1:8787', 'https://app.example'):
            self.assertEqual(validate_public_origin(origin), origin)
    def test_invalid_and_public_http(self):
        for origin in ('http://8.8.8.8', 'http://172.32.0.1', 'http://app.example', 'http://192.168.1.2/path', 'http://user@192.168.1.2', 'http://192.168.1.2?x=1', 'http://192.168.1.2#x', 'http://192.168.1.2:99999', 'ftp://192.168.1.2', 'https://app.example:bad'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                validate_public_origin(origin)
