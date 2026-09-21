"""Build a portable workbench from explicitly selected source directories."""
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parents[1]

def package():
    target = ROOT / 'dist/aeroblade.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    allowed = {'.py', '.mjs', '.js', '.css', '.html', '.md', '.sh', '.json', '.txt'}
    files = [p for folder in ('bridge', 'web', 'docs', 'evaluation')
             for p in (ROOT / folder).rglob('*')
             if p.is_file() and not p.is_symlink()
             and not {'__pycache__','.vercel'}&set(p.parts) and p.suffix in allowed]
    files.append(ROOT / 'README.md')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(ROOT))
    temporary.replace(target)
    return target

if __name__ == '__main__':
    print(package())
