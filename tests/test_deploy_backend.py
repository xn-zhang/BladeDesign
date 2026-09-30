"""Linux-only deployment tests; never touch the running service or real database."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'scripts/deploy_backend.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeployTests(unittest.TestCase):
    def archive(self, extra=None):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            for name in ('aeroblade/bridge/server.py', 'aeroblade/bridge/package.py', 'aeroblade/web/index.html'):
                member = tarfile.TarInfo(name)
                member.size = 2
                archive.addfile(member, io.BytesIO(b'ok'))
            if extra:
                archive.addfile(extra, io.BytesIO(b''))
        data = stream.getvalue()
        return io.BytesIO(data), hashlib.sha256(data).hexdigest()

    def test_command_rejects_shell_and_invalid_revision(self):
        good = 'deploy ' + 'a' * 40 + ' ' + 'b' * 64
        self.assertEqual(deploy.parse_command(good), ('a' * 40, 'b' * 64))
        for value in ('', good + '; id', good + '\n', 'deploy main ' + 'b' * 64):
            with self.assertRaises(ValueError):
                deploy.parse_command(value)

    def test_safe_archive(self):
        with tempfile.TemporaryDirectory() as root:
            stream, checksum = self.archive()
            deploy.unpack(stream, Path(root), checksum)
            self.assertEqual((Path(root) / 'aeroblade/bridge/server.py').read_text(), 'ok')

    def test_rejects_paths_links_and_duplicates_before_writing(self):
        items = [tarfile.TarInfo(n) for n in ('../escape', '/absolute', 'x/../../escape', '.git/config', 'aeroblade/bridge/server.py')]
        link = tarfile.TarInfo('link')
        link.type = tarfile.SYMTYPE
        link.linkname = '/etc'
        items.append(link)
        for item in items:
            with self.subTest(name=item.name), tempfile.TemporaryDirectory() as root:
                stream, checksum = self.archive(item)
                with self.assertRaises(ValueError):
                    deploy.unpack(stream, Path(root), checksum)
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_checksum_and_expansion_limit(self):
        with tempfile.TemporaryDirectory() as root:
            stream, checksum = self.archive()
            with self.assertRaises(ValueError):
                deploy.unpack(stream, Path(root), '0' * 64)
            stream.seek(0)
            with patch.object(deploy, 'MAX_EXPANDED', 1), self.assertRaises(ValueError):
                deploy.unpack(stream, Path(root), checksum)

    def activation(self, root, checks, previous=None, copy_error=None):
        override = Path(root) / 'override.conf'
        if previous is not None:
            override.write_bytes(previous)
        with (patch.object(deploy, 'OVERRIDE', override),
              patch.object(deploy.shutil, 'copy2'),
              patch.object(deploy.shutil, 'copytree', side_effect=copy_error),
              patch.object(deploy, 'run') as run,
              patch.object(deploy, 'healthy', side_effect=checks)):
            try:
                deploy.activate(Path('/opt/aeroblade-releases/' + 'a' * 40), Path(root))
            except (RuntimeError, OSError):
                pass
            return override, [call.args for call in run.call_args_list]

    def test_successful_switch(self):
        with tempfile.TemporaryDirectory() as root:
            override, calls = self.activation(root, [True])
            self.assertIn('a' * 40, override.read_text())
            self.assertIn(('systemctl', 'start', deploy.SERVICE), calls)
            self.assertNotIn(('systemctl', 'restart', deploy.SERVICE), calls)

    def test_failed_health_restores_previous_override(self):
        with tempfile.TemporaryDirectory() as root:
            override, calls = self.activation(root, [False, True], b'previous')
            self.assertEqual(override.read_bytes(), b'previous')
            self.assertIn(('systemctl', 'restart', deploy.SERVICE), calls)

    def test_first_deploy_failure_removes_override(self):
        with tempfile.TemporaryDirectory() as root:
            override, calls = self.activation(root, [False, True])
            self.assertFalse(override.exists())
            self.assertIn(('systemctl', 'restart', deploy.SERVICE), calls)

    def test_backup_failure_restarts_previous_service(self):
        with tempfile.TemporaryDirectory() as root:
            override, calls = self.activation(root, [True], b'previous', OSError('disk full'))
            self.assertEqual(override.read_bytes(), b'previous')
            self.assertIn(('systemctl', 'restart', deploy.SERVICE), calls)


if __name__ == '__main__':
    unittest.main()
