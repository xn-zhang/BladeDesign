"""Build public static files and a same-origin API proxy, with no server secrets."""
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit


def build(root, backend):
    root=Path(root).resolve()
    url=urlsplit(backend or '')
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Set AEROBLADE_BACKEND_URL to the HTTPS backend URL without credentials, query or fragment')
    url.port
    output=root/'.vercel'/'output'
    if output.is_symlink() or output.resolve()!=root/'.vercel'/'output':
        raise ValueError('Build output must stay inside the project .vercel/output directory')
    if output.exists():shutil.rmtree(output)
    static=output/'static';static.mkdir(parents=True)
    for source in (root/'aeroblade'/'web').iterdir():
        if source.is_file() and not source.is_symlink() and source.suffix in ('.html','.js','.css'):
            shutil.copyfile(source,static/source.name)
    config={'version':3,'routes':[
        {'src':'/api/(.*)','dest':backend.rstrip('/')+'/api/$1','headers':{'Cache-Control':'no-store'}},
        {'handle':'filesystem'},
    ]}
    (output/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    return output


if __name__=='__main__':
    print(build(Path(__file__).resolve().parents[1],os.environ.get('AEROBLADE_BACKEND_URL','')))
