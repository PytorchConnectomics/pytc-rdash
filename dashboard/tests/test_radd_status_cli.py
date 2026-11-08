import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from dashboard.app import inspection

SCRIPT = Path(__file__).resolve().parents[2] / 'skills/radd-hypo/radd_status.py'
spec = importlib.util.spec_from_file_location('radd_status_cli', str(SCRIPT))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CliTests(unittest.TestCase):
    def test_empty_input_no_process_timeout_and_failed_reachability(self):
        host = cli.Host(timeout=.025)
        with mock.patch.object(inspection.subprocess, 'Popen') as launch:
            self.assertEqual(host.stat([]), {})
            self.assertEqual(host.jobs([]), {})
            launch.assert_not_called()
        with mock.patch.object(inspection, 'observe_paths', return_value=({'/x': dict(state='unknown')}, 'failed')) as observe:
            self.assertEqual(host.stat(['/x']), {'/x':'unknown'})
            observe.assert_called_once_with('', ['/x'], timeout=.025)
            self.assertFalse(host.reachable)
        with mock.patch.object(inspection, 'probe_jobs', return_value=({1: dict(tasks={}, reduced='unknown')}, 'failed')) as jobs:
            self.assertEqual(host.jobs([1]), {1:'unknown'})
            jobs.assert_called_once_with('', [1], timeout=.025)
            self.assertFalse(host.reachable)
        with mock.patch.object(inspection, 'PROGRAM', 'import time; time.sleep(10)'):
            start = time.monotonic()
            self.assertEqual(host.stat(['/x']), {'/x':'unknown'})
            self.assertLess(time.monotonic() - start, 1)
            self.assertFalse(host.reachable)

    def test_cli_different_cwd_write_and_json_and_shared_fixture_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            card = root / 'projects/fixture/cards/card.md'
            card.parent.mkdir(parents=True)
            file = root / 'data'
            file.write_bytes(b'123')
            missing = root / 'absent'
            # Fake scheduler executables live only in a temporary fixture directory.
            bindir = root / 'bin'
            bindir.mkdir()
            for command, output in [('squeue', '42_0|RUNNING|1:02|2026-09-29T10:00:00|node\n42_1|PENDING||N/A|Resources\n'),
                                    ('sacct', '41|FAILED|2:00|2026-09-29T09:00:00|2026-09-29T09:02:00\n41.extern|COMPLETED|2:00|2026-09-29T09:00:00|2026-09-29T09:02:00\n')]:
                path = bindir / command
                path.write_text('#!' + sys.executable + '\nprint(' + repr(output) + ')\n')
                path.chmod(0o700)
            body = 'before\n```probe-status\n' + json.dumps(dict(schema_version=1, jobs=[41,42],
                artifacts={'file':str(file), 'absent':str(missing)})) + '\n```\n' + cli.BEGIN + '\nold snapshot\n' + cli.END + '\nafter\n'
            card.write_text(body)
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ.get('PATH',''), PYTHONDONTWRITEBYTECODE='1')
            argv = [sys.executable, '-B', str(SCRIPT), 'fixture', '--repo-root', str(root), '--task', 'cards/card.md']
            done = subprocess.run(argv + ['--write'], cwd='/', env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout, 'wrote status into projects/fixture/cards/card.md\n')
            after = card.read_text()
            self.assertEqual(after.split(cli.BEGIN)[0], body.split(cli.BEGIN)[0])
            self.assertEqual(after.split(cli.END)[1], body.split(cli.END)[1])
            self.assertNotIn('old snapshot', after)
            done = subprocess.run(argv + ['--json'], cwd='/', env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads(done.stdout)
            with mock.patch.dict(os.environ, env):
                paths, transport = inspection.observe_paths('', [str(file), str(missing)])
                jobs, transport = inspection.probe_jobs('', [41,42])
                adapter = cli.Host()
                self.assertEqual(adapter.jobs([41,42]), {int(k):v for k,v in report['jobs'].items()})
                self.assertEqual(adapter.stat([str(file)])[str(file)][0], paths[str(file)]['size'])
            self.assertTrue(report['reachable'])
            self.assertEqual(paths[str(missing)]['state'], 'absent')
            self.assertEqual(report['artifacts']['absent']['state'], '**absent**')
            self.assertEqual(jobs[41]['reduced'], 'FAILED')
            self.assertEqual(jobs[42]['reduced'], 'RUNNING')
            self.assertEqual(report['jobs']['41'], 'FAILED (2:00)')
            self.assertEqual(report['jobs']['42'], '0: RUNNING (1:02) node; 1: PENDING Resources')

    def test_kind_localtime_and_array_format(self):
        rows = {kind: dict(state='present', kind=kind, size=3, mtime=0) for kind in ('file','dir','symlink','other')}
        with mock.patch.object(inspection, 'observe_paths', return_value=(rows,'ok')):
            observed = cli.Host().stat(list(rows))
        self.assertEqual([row[2] for row in observed.values()], ['regular file','directory','symbolic link','other'])
        self.assertEqual(observed['file'][1], time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(0)))
        self.assertEqual(cli.Host._match({'1_0':'COMPLETED','1_1':'COMPLETED'},1), 'COMPLETED [2 array tasks]')
