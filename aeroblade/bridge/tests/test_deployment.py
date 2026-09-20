import json
from pathlib import Path
import runpy
import tempfile
import unittest

build=runpy.run_path(str(Path(__file__).resolve().parents[3]/'scripts'/'build_vercel.py'))['build']

class DeploymentTests(unittest.TestCase):
    def test_only_public_web_files_and_proxy_are_built(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);web=root/'aeroblade'/'web';web.mkdir(parents=True)
            (web/'index.html').write_text('<html>Test</html>');(web/'app.js').write_text('test()')
            (web/'.env').write_text('PRIVATE=fixture');(root/'private.key').write_text('fixture')
            output=build(root,'https://backend.example')
            self.assertEqual({p.name for p in (output/'static').iterdir()},{'index.html','app.js'})
            config=json.loads((output/'config.json').read_text())
            self.assertEqual(config['routes'][0]['dest'],'https://backend.example/api/$1')
            build(root,'https://backend.example') # A second build safely replaces generated output only.
            self.assertTrue((root/'private.key').exists())
    def test_backend_must_be_explicit_https_and_has_no_credentials(self):
        for url in ('','http://backend.example','https://key@backend.example','https://backend.example?key=secret'):
            with self.assertRaises(ValueError):build(Path.cwd(),url)

if __name__=='__main__':unittest.main()
