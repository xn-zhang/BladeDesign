"""Verify the portable archive layout and public source boundary."""
from pathlib import Path
import zipfile
root = Path(__file__).resolve().parents[1]
with zipfile.ZipFile(root / 'aeroblade/dist/aeroblade.zip') as archive:
    names = set(archive.namelist())
    assert archive.testzip() is None
    assert {'README.md', 'web/index.html', 'web/geometry.js', 'bridge/server.py',
            'bridge/start-local.sh', 'docs/CASCADE.md'} <= names
    assert all(Path(n).parts[0] in {'README.md', 'web', 'bridge', 'docs', 'evaluation'} for n in names)
    assert not any('api-token' in n or set(Path(n).parts) & {'__pycache__', '.vercel', 'private', 'jobs', 'runtime', 'ai-data'} or Path(n).suffix in {'.sqlite3', '.db', '.env', '.key', '.pem'} for n in names)
    assert {'web/session-state.js', 'web/account-admin.js', 'web/personal-workspace.js', 'bridge/personal_store.py', 'evaluation/worker.py'} <= names
print('Portable archive layout verified')
