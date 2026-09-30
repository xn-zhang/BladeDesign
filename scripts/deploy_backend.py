#!/usr/bin/python3
"""Root-owned forced-command deployer. Install, do not run from uploaded code."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
RELEASES = Path('/opt/aeroblade-releases')
BACKUPS = Path('/var/backups/aeroblade-ci')
OVERRIDE = Path('/etc/systemd/system/aeroblade.service.d/90-ci-release.conf')
DATA = Path('/var/lib/aeroblade')
SERVICE = 'aeroblade.service'


def parse_command(command):
    match = re.fullmatch(r'deploy ([0-9a-f]{40}) ([0-9a-f]{64})', command)
    if not match:
        raise ValueError('Expected: deploy <40-character commit SHA> <SHA256>')
    return match.groups()


def unpack(stream, target, checksum):
    blob = stream.read(MAX_ARCHIVE + 1)
    if len(blob) > MAX_ARCHIVE or hashlib.sha256(blob).hexdigest() != checksum:
        raise ValueError('Archive size or checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) > 20000 or sum(m.size for m in members) > MAX_EXPANDED:
            raise ValueError('Archive expansion limit exceeded')
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or not path.parts or '..' in path.parts
                    or '\\' in member.name or path.parts[0] in ('.git', '.release-sha256')
                    or path in seen or not (member.isdir() or member.isfile())):
                raise ValueError('Unsafe archive member')
            seen.add(path)
        for member in members:
            dest = target.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                dest.chmod(0o755)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, dest.open('xb') as output:
                    shutil.copyfileobj(source, output)
                dest.chmod(0o644)
    for name in ('aeroblade/bridge/server.py', 'aeroblade/bridge/package.py', 'aeroblade/web/index.html'):
        if not (target / name).is_file():
            raise ValueError('Incomplete backend release')


def run(*args):
    subprocess.run(args, check=True, timeout=120)


def healthy(attempts=30):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8787/api/session', timeout=2) as response:
                data = json.load(response)
                if response.status == 200 and data.get('setup_required') is False and 'authenticated' in data:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def override_text(release):
    return ('[Service]\nWorkingDirectory=' + str(release) + '\nExecStart=\n'
            'ExecStart=/usr/bin/python3 ' + str(release / 'aeroblade/bridge/server.py')
            + ' --model-only --host 127.0.0.1 --port 8787 --jobs /var/lib/aeroblade/jobs\n')


def activate(release, backup):
    previous = OVERRIDE.read_bytes() if OVERRIDE.exists() else None
    if previous is not None:
        (backup / 'previous-override.conf').write_bytes(previous)
    shutil.copy2('/etc/systemd/system/aeroblade.service', backup / 'aeroblade.service')
    switched = False
    try:
        # From this point any failure must restart the previous service.
        switched = True
        run('systemctl', 'stop', SERVICE)
        shutil.copytree(DATA, backup / 'data', copy_function=shutil.copy2)
        OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
        temp = OVERRIDE.with_suffix('.tmp')
        temp.write_text(override_text(release))
        temp.chmod(0o644)
        os.replace(temp, OVERRIDE)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', SERVICE)
        if not healthy():
            raise RuntimeError('New release failed session health check')
        run('systemctl', 'is-active', '--quiet', SERVICE)
    except BaseException:
        if switched:
            if previous is None:
                OVERRIDE.unlink(missing_ok=True)
            else:
                OVERRIDE.write_bytes(previous)
            run('systemctl', 'daemon-reload')
            run('systemctl', 'restart', SERVICE)
            if not healthy():
                print('ROLLBACK NEEDS ATTENTION: previous code also failed health check', flush=True)
            print('Previous service configuration restored. Database backup: ' + str(backup), flush=True)
        raise


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise ValueError('Must be invoked through the restricted deployment wrapper')
    sha, checksum = parse_command(sys.argv[1])
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(InterruptedError('Deployment interrupted')))
    os.umask(0o022)
    with open('/run/lock/aeroblade-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        RELEASES.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.incoming-', dir=RELEASES) as staging:
            stage = Path(staging)
            stage.chmod(0o755)
            unpack(sys.stdin.buffer, stage, checksum)
            release = RELEASES / sha
            if release.exists():
                if (release / '.release-sha256').read_text() != checksum:
                    raise ValueError('Existing release has a different archive')
            else:
                shutil.copytree(stage, release)
                (release / '.release-sha256').write_text(checksum)
            # Build uploaded code only as the unprivileged application account.
            dist = release / 'aeroblade/dist'
            dist.mkdir(exist_ok=True)
            shutil.chown(dist, user='aeroblade', group='aeroblade')
            run('runuser', '-u', 'aeroblade', '--', '/usr/bin/python3', str(release / 'aeroblade/bridge/package.py'))
            BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S-'), dir=BACKUPS))
            activate(release, backup)
            print(json.dumps({'deployed': sha, 'backup': str(backup), 'health': 'ok'}), flush=True)


if __name__ == '__main__':
    main()
