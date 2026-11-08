import errno
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dashboard.app import inspection as probe


class ProbeTests(unittest.TestCase):
    def setUp(self):
        # Remote calls here go through a mocked _exchange; skip the real reachability check.
        patcher = mock.patch.object(probe, 'reachable', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_remote_roots_unresolved_at_load_recover_on_use(self):
        from dashboard.app import config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'projects/config').mkdir(parents=True)
            (root / 'projects/config/rdash-roots.yaml').write_text('bc:\n  - /data/runs\n')
            with mock.patch.object(probe, 'resolve_roots', return_value=None):
                settings = config.Settings(root, root / 'cache', 0, ssh_hosts=('bc',),
                                           result_roots=config.load_roots(root / "projects/config", '', ('bc',)))
                self.assertEqual(config.roots_for(settings, 'p', 'bc'), (None,))
            with mock.patch.object(probe, 'resolve_roots', return_value=('/real/runs',)) as resolve:
                self.assertEqual(config.roots_for(settings, 'p', 'bc'), ('/real/runs',))
                self.assertEqual(config.roots_for(settings, 'p', 'bc'), ('/real/runs',))
            resolve.assert_called_once_with('bc', ('/data/runs',))

    def test_unreachable_host_fails_fast_and_keeps_last_observation(self):
        probe._cache.clear()
        self.addCleanup(probe._cache.clear)
        row = dict(state='present', kind='file', size=1, mtime=1.0)
        with mock.patch.object(probe, '_exchange', return_value=(json.dumps(dict(i=0, **row)).encode() + b'\n', 'ok')):
            self.assertEqual(probe.cached('bc', 'metadata', ['/a'])['/a'], row)
        with mock.patch.object(probe, 'reachable', return_value=False), \
                mock.patch.object(probe, '_exchange') as exchange, mock.patch.object(probe, 'CACHE_TTL', 0):
            observed = probe.cached('bc', 'metadata', ['/a', '/b'])
            jobs = probe.cached('bc', 'jobs', ['7'])
        exchange.assert_not_called()
        self.assertEqual(observed['/a'], dict(row, stale=True))
        self.assertEqual(observed['/b'], dict(state='unknown', reason='host_unreachable'))
        self.assertEqual(jobs['7'], dict(tasks={}, reduced='unknown', reason='host_unreachable'))

    def test_real_classifier_and_adversarial_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['ordinary', 'a b', "a'b", 'a"b', '$(id)', '`id`', 'a;b', 'a|b', 'a\\b', '*', '-leading']
            paths = []
            for name in names:
                p = root / name
                p.write_text('abc')
                paths.append(str(p))
            (root / 'dir').mkdir()
            (root / 'dangling').symlink_to(root / 'absent')
            (root / 'link').symlink_to(root / 'ordinary')
            paths += [str(root / x) for x in ['dir', 'dangling', 'link', 'absent', 'ordinary/child', 'x' * 400]]
            rows = probe.probe_local(paths)
            self.assertEqual([r['state'] for r in rows], ['present'] * (len(names) + 3) + ['absent', 'absent', 'unknown'])
            self.assertEqual(rows[-1]['reason'], 'ENAMETOOLONG')
            self.assertEqual(rows[-5]['kind'], 'symlink')
            self.assertEqual(rows[-4]['kind'], 'symlink')
            namespace = {'__name__': 'test'}
            exec(probe.PROGRAM, namespace)
            def exchange(argv, payload, **kwargs):
                output = io.StringIO()
                namespace['probe'](io.StringIO(json.dumps(json.loads(payload)["items"])), output)
                self.assertIn('StrictHostKeyChecking=yes', argv)
                self.assertNotIn('accept-new', ' '.join(argv))
                for path in paths:
                    self.assertNotIn(path, ' '.join(argv))
                return output.getvalue().encode(), "ok"
            with mock.patch.object(probe, '_exchange', side_effect=exchange):
                self.assertEqual(probe.probe_remote('bc', paths), rows)

    def test_real_permission_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'private'
            root.mkdir()
            (root / 'file').write_text('x')
            root.chmod(0)
            try:
                row = probe.probe_local([str(root / 'file')])[0]
                if os.geteuid() == 0:
                    self.skipTest('root bypasses directory permissions')
                self.assertEqual(row, dict(state='unknown', reason='EACCES'))
            finally:
                root.chmod(0o700)

    def test_other_errno_is_unknown(self):
        code = probe.PROGRAM.replace('value = os.lstat(path)', 'raise OSError(errno.EIO, \"injected\")')
        with mock.patch.object(probe, 'PROGRAM', code):
            self.assertEqual(probe.probe_local(['/x']), [dict(state='unknown', reason='EIO')])

    def test_ordered_chunking_and_invalid_alias(self):
        paths = ['/path/' + str(i) for i in range(600)]
        batches = []
        def exchange(argv, payload, **kwargs):
            batch = json.loads(payload)["items"]
            batches.append(batch)
            return '\n'.join(json.dumps(dict(i=i, state='absent')) for i in range(len(batch))).encode(), 'ok'
        with mock.patch.object(probe, '_exchange', side_effect=exchange):
            rows = probe.probe_remote('bc', paths)
            self.assertEqual([len(b) for b in batches], [250, 250, 100])
            self.assertEqual(sum(batches, []), paths)
            self.assertEqual(len(rows), 600)
            probe.probe_remote('-bad', ['/x'])
            self.assertEqual(len(batches), 3)

    def test_response_validation(self):
        raw = '\n'.join([json.dumps(r) for r in [
            dict(i=0, state='absent'), dict(i=0, state='present'),
            dict(i=2, state='present', kind='file', size=-1, mtime=0),
            dict(i=3, state='absent'), dict(i=999, state='absent'), [], dict(i=True, state='absent')]])
        rows = probe.parse_output(raw + '\n{bad', 5)
        self.assertEqual([r['state'] for r in rows], ['unknown', 'unknown', 'unknown', 'absent', 'unknown'])
        self.assertEqual(probe.parse_output(b'\xff', 1)[0]['state'], 'unknown')
        self.assertEqual(probe.parse_output(b'', 1)[0]['state'], 'unknown')

    def test_pipe_bounds_cleanup_and_failures_without_network(self):
        original = subprocess.Popen
        children = []
        def launch(code):
            def create(*args, **kwargs):
                child = original([sys.executable, '-B', '-c', code], **kwargs)
                children.append(child)
                return child
            return create
        cases = [("import sys; sys.stdout.write('x'*300000)", 2),
                 ("import time; time.sleep(2)", .03),
                 ("raise SystemExit(1)", 2)]
        for code, timeout in cases:
            with mock.patch.object(probe.subprocess, 'Popen', side_effect=launch(code)), mock.patch.object(probe, 'STAT_TIMEOUT', timeout):
                self.assertEqual(probe._exchange(['fake'], b'[]')[1],
                                 'overflow' if '300000' in code else 'timeout' if 'sleep' in code else 'failed')
            self.assertIsNotNone(children[-1].poll())
            self.assertTrue(all(p.closed for p in (children[-1].stdin, children[-1].stdout, children[-1].stderr)))
        with mock.patch.object(probe.subprocess, 'Popen', side_effect=launch("import sys; sys.stdin.read(); sys.stderr.write('x'*300000); print('ok')")):
            self.assertEqual(probe._exchange(['fake'], b'x' * 200000), (b'ok\n', 'ok'))
