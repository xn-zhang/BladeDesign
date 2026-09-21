"""Repository-root entry point; web deployments use the same self-contained builder."""
import os
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
build=runpy.run_path(str(ROOT/'aeroblade/web/scripts/build_vercel.py'))['build']

if __name__=='__main__':
    print(build(ROOT,os.environ.get('AEROBLADE_BACKEND_URL','')))
