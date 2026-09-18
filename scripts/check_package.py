"""Verify the portable archive layout and public source boundary."""
from pathlib import Path
import zipfile
root = Path(__file__).resolve().parents[1]
with zipfile.ZipFile(root / 'aeroblade/dist/aeroblade.zip') as archive:
    names = set(archive.namelist())
    assert archive.testzip() is None
    assert {'README.md', 'web/index.html', 'web/geometry.js', 'bridge/server.py',
            'bridge/start-local.sh', 'docs/CASCADE.md'} <= names
    assert all(Path(n).parts[0] in {'README.md', 'web', 'bridge', 'docs'} for n in names)
    assert not any('api-token' in n or '__pycache__' in n for n in names)
print('Portable archive layout verified')
