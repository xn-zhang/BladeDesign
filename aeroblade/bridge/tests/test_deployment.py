import json
from pathlib import Path
import runpy
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

build=runpy.run_path(str(Path(__file__).resolve().parents[3]/'scripts'/'build_vercel.py'))['build']

class DeploymentTests(unittest.TestCase):
    def test_portable_package_excludes_nested_vercel_build_outputs(self):
        repo=Path(__file__).resolve().parents[3]
        package=runpy.run_path(str(repo/'aeroblade/bridge/package.py'))['package']
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);web=root/'web';generated=web/'.vercel/output/static';generated.mkdir(parents=True)
            (root/'README.md').write_text('fixture');(web/'index.html').write_text('source');(generated/'index.html').write_text('generated')
            with patch.dict(package.__globals__,{'ROOT':root}):archive=package()
            with zipfile.ZipFile(archive) as z:self.assertEqual(set(z.namelist()),{'README.md','web/index.html'})
    def test_web_root_build_needs_no_files_outside_selected_directory(self):
        repo=Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as folder:
            web=Path(folder)/'web';web.mkdir();(web/'scripts').mkdir()
            (web/'index.html').write_text('<html>standalone</html>');(web/'app.js').write_text('test()')
            shutil.copyfile(repo/'aeroblade/web/scripts/build_vercel.py',web/'scripts/build_vercel.py')
            config=json.loads((repo/'aeroblade/web/vercel.json').read_text())
            self.assertEqual(config['buildCommand'],'python3 scripts/build_vercel.py')
            result=subprocess.run([sys.executable,'scripts/build_vercel.py'],cwd=web,env={**os.environ,'AEROBLADE_BACKEND_URL':'https://backend.example'},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            output=web/'.vercel/output';self.assertTrue((output/'static/index.html').is_file())
            self.assertEqual(json.loads((output/'config.json').read_text())['routes'][0]['dest'],'https://backend.example/api/$1')
            self.assertFalse((output/'static/scripts').exists());self.assertFalse((web.parent/'.vercel').exists())
    def test_repo_root_entrypoint_keeps_output_at_repo_root(self):
        repo=Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'scripts').mkdir();web=root/'aeroblade/web';(web/'scripts').mkdir(parents=True)
            (web/'index.html').write_text('<html>root</html>')
            shutil.copyfile(repo/'scripts/build_vercel.py',root/'scripts/build_vercel.py')
            shutil.copyfile(repo/'aeroblade/web/scripts/build_vercel.py',web/'scripts/build_vercel.py')
            result=subprocess.run([sys.executable,'scripts/build_vercel.py'],cwd=root,env={**os.environ,'AEROBLADE_BACKEND_URL':'https://backend.example'},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertTrue((root/'.vercel/output/static/index.html').is_file());self.assertFalse((web/'.vercel').exists())
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
