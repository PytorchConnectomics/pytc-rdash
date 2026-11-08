import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from dashboard.app import inspection as probe
from dashboard.app.config import Settings, load_roots, roots_for


class InspectionTests(unittest.TestCase):
    def setUp(self):
        probe._cache.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.file = self.root / 'metric.json'
        self.file.write_bytes(b'{"nerl": 0.612}')

    def read(self, paths, roots=None, **kwargs):
        return probe.read_files('', [str(p) for p in paths], roots or [str(self.root)], **kwargs)[0]

    def test_ssh_argv_reuses_a_board_owned_connection(self):
        argv = probe._argv('cajal')
        opts = dict(argv[i + 1].split('=', 1) for i, a in enumerate(argv) if a == '-o')
        self.assertEqual(opts['ControlMaster'], 'auto')
        self.assertEqual(opts['ControlPath'], '~/.ssh/cm-rdash-%C')
        self.assertEqual(opts['ControlPersist'], '35m')
        self.assertEqual(opts['BatchMode'], 'yes')
        self.assertLess(argv.index('ControlMaster=auto'), argv.index('cajal'))
        self.assertNotIn('ControlMaster=auto', probe._argv(''))

    def test_job_times_reduce_to_phase_start_and_end(self):
        t = lambda state, start="", end="": dict(state=state, start=start, end=end)
        self.assertEqual(probe.job_times("RUNNING", {"1": t("RUNNING", "2026-09-29T10:00:00")}),
                         dict(phase="in progress", start="2026-09-29T10:00:00", end=""))
        self.assertEqual(probe.job_times("PENDING", {"1": t("PENDING")})["phase"], "in progress")
        done = probe.job_times("FAILED", {"1": t("FAILED", "2026-09-29T10:00:00", "2026-09-29T10:05:00")})
        self.assertEqual(done, dict(phase="done", start="2026-09-29T10:00:00", end="2026-09-29T10:05:00"))
        array = {"1_0": t("COMPLETED", "2026-09-29T10:00:00", "2026-09-29T10:02:00"),
                 "1_1": t("COMPLETED", "2026-09-29T10:01:00", "2026-09-29T10:09:00")}
        self.assertEqual(probe.job_times("COMPLETED", array)["end"], "2026-09-29T10:09:00")
        self.assertEqual(probe.job_times("unknown", {})["phase"], "unknown")
        self.assertEqual(probe.clean_time("Unknown"), "")

    def test_default_and_configured_roots(self):
        project = self.root / 'projects/alpha'
        (project / 'results').mkdir(parents=True)
        (self.root / 'projects/config').mkdir()
        alias = self.root / 'alias'
        alias.symlink_to(self.root)
        config = self.root / 'projects/config/rdash-roots.yaml'
        config.write_text('local:\n  - ' + str(alias) + '\n')
        settings = Settings(self.root, self.root / 'cache', 0, stat_local=True,
                            result_roots=load_roots(self.root / "projects/config"))
        self.assertEqual(settings.result_roots, (('local', str(self.root)),))
        out = project / 'results/m.json'
        out.write_text('{}')
        roots = roots_for(settings, 'alpha', '')
        self.assertEqual(self.read([out], roots)[str(out)]['state'], 'present')
        self.assertEqual(self.read([self.file], roots)[str(self.file)]['state'], 'present')
        config.unlink()
        self.assertEqual(load_roots(self.root / "projects/config"), ())
        config.write_text('local: [/]')
        with self.assertRaises(ValueError):
            load_roots(self.root / "projects/config")

    def test_outside_prefix_and_symlinks(self):
        allowed = self.root / 'data'
        allowed.mkdir()
        sibling = self.root / 'data-other'
        sibling.mkdir()
        outside = sibling / 'metric.json'
        outside.write_text('{}')
        (allowed / 'final').symlink_to(outside)
        (allowed / 'intermediate').symlink_to(sibling)
        paths = [outside, allowed / 'final', allowed / 'intermediate/metric.json']
        rows = self.read(paths, [str(allowed)])
        self.assertEqual([rows[str(p)]['reason'] for p in paths],
                         ['outside declared roots', 'symlink_in_path', 'symlink_in_path'])
        self.assertEqual(probe.observe_paths('', [str(outside)])[0][str(outside)]['state'], 'present')
        allowed.rmdir() if not list(allowed.iterdir()) else None
        missing_root = self.root / 'lost'
        self.assertEqual(self.read([missing_root / 'x'], [str(missing_root)])[str(missing_root / 'x')]['reason'], 'root_unavailable')

    def test_directory_replaced_mid_walk_cannot_escape(self):
        inside = self.root / 'inside'
        inside.mkdir()
        (inside / 'metric.json').write_bytes(b'inside')
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'metric.json').write_bytes(b'outside')
        reached, replaced = threading.Event(), threading.Event()
        original = os.open
        def opening(name, flags, **kwargs):
            fd = original(name, flags, **kwargs)
            if name == 'inside':
                reached.set()
                self.assertTrue(replaced.wait(2))
            return fd
        def replace():
            self.assertTrue(reached.wait(2))
            inside.rename(self.root / 'old')
            inside.symlink_to(outside)
            replaced.set()
        thread = threading.Thread(target=replace)
        thread.start()
        with mock.patch.object(probe.os, 'open', side_effect=opening):
            row, data = probe.read_one(str(inside / 'metric.json'), [str(self.root)])
        thread.join(2)
        self.assertEqual(row['state'], 'present')
        self.assertEqual(data, b'inside')

    def test_special_files_are_classified_before_open(self):
        fifo = self.root / 'fifo'
        os.mkfifo(str(fifo))
        sockpath = self.root / 'socket'
        # This sandbox may forbid even UNIX socket binds; simulate its lstat type
        # below in addition to testing a real FIFO and directory.
        real_open = os.open
        for path in (fifo, self.root):
            # Use the parent as the root so the directory is the final component.
            with mock.patch.object(probe.os, 'open', wraps=real_open) as opening:
                start = time.monotonic()
                row, _ = probe.read_one(str(path), [str(self.root.parent)])
                self.assertLess(time.monotonic() - start, .5)
                self.assertEqual(row['reason'], 'not_regular')
                self.assertFalse(any(call.args[0] == path.name for call in opening.call_args_list))
        import stat
        for mode in (stat.S_IFSOCK, stat.S_IFCHR):
            real_stat = os.stat
            def lstat(name, **kwargs):
                if name == self.file.name:
                    return mock.Mock(st_mode=mode)
                return real_stat(name, **kwargs)
            with mock.patch.object(probe.os, 'stat', side_effect=lstat), mock.patch.object(probe.os, 'open', wraps=real_open) as opening:
                self.assertEqual(probe.read_one(str(self.file), [str(self.root)])[0]['reason'], 'not_regular')
                self.assertFalse(any(call.args[0] == self.file.name for call in opening.call_args_list))

    def test_content_limits_and_partial_records(self):
        self.assertEqual(probe.MAX_CONTENT_FILE, 1024 * 1024)
        self.assertEqual(probe.MAX_CONTENT_OUTPUT, 4 * 1024 * 1024)
        self.assertEqual(probe.MAX_OUTPUT, 256 * 1024)
        large = self.root / 'large.json'
        large.write_bytes(b'x' * 1153434)
        rows = self.read([large, self.file])
        self.assertEqual(rows[str(large)]['state'], 'unreadable')
        self.assertEqual(rows[str(large)]['reason'], 'too_large')
        self.assertEqual(rows[str(self.file)]['data'], self.file.read_bytes())
        paths = []
        for i in range(5):
            path = self.root / ('large%d.json' % i)
            path.write_bytes(b'x' * 1048576)
            paths.append(str(path))
        single, status = probe.read_files('', paths[:1], [str(self.root)])
        self.assertEqual(status, 'ok')
        self.assertEqual(single[paths[0]]['data'], b'x' * 1048576)
        rows, status = probe.read_files('', paths, [str(self.root)])
        self.assertEqual(status, 'overflow')
        self.assertEqual([rows[p]['state'] for p in paths], ['present'] * 3 + ['unknown'] * 2)
        for path in paths[:3]:
            self.assertEqual(rows[path]['data'], b'x' * 1048576)
        for path in paths[3:]:
            self.assertNotIn('data', rows[path])
        wire = b'{"i":0,"state":"present","size":2,"mtime":1,"len":2}\n{}\n{"i":1,"state":"present","len":10}\nx'
        parsed = probe.parse_content(wire, 2)
        self.assertEqual(parsed[0]['data'], b'{}')
        self.assertEqual(parsed[1]['state'], 'unknown')

    def test_local_deadline_and_failure_isolation(self):
        metadata = probe.cached('', 'metadata', [str(self.file)])
        start = time.monotonic()
        with mock.patch.object(probe, 'PROGRAM', 'import time; time.sleep(10)'):
            rows, status = probe.observe_paths('', [str(self.file)], timeout=.03)
            self.assertEqual(status, 'timeout')
            self.assertEqual(rows[str(self.file)]['state'], 'unknown')
            failed = probe.cached('', 'content', [str(self.file)], [str(self.root)], timeout=.03)
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(failed[str(self.file)]['state'], 'unknown')
        self.assertEqual(probe.cached('', 'metadata', [str(self.file)]), metadata)

    def test_cleanup_grace_is_bounded_and_later_call_reaps(self):
        real = subprocess.Popen
        children = []
        def spawn(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            original_poll = child.poll
            child.poll = mock.Mock(return_value=None)
            child.wait = mock.Mock(side_effect=subprocess.TimeoutExpired('stub', 2))
            child.original_poll = original_poll
            return child
        with mock.patch.object(probe.subprocess, 'Popen', side_effect=spawn):
            start = time.monotonic()
            probe._exchange([sys.executable, '-B', '-c', 'import time; time.sleep(10)'], b'', timeout=.02)
            self.assertLess(time.monotonic() - start, .5)
        child = children[0]
        self.assertIn(child, probe._reapers)
        child.wait.assert_called_with(timeout=2)
        child.poll = child.original_poll
        deadline = time.monotonic() + 2
        while child.poll() is None and time.monotonic() < deadline:
            time.sleep(.001)
        probe._exchange([sys.executable, '-B', '-c', 'pass'], b'')
        self.assertNotIn(child, probe._reapers)

    def test_cache_identity_expiry_failure_and_generations(self):
        def channel(host, channel, items, **kwargs):
            return [dict(state='present') for _ in items], 'ok'
        with mock.patch.object(probe, '_channel', side_effect=channel) as exchange:
            probe.cached('bc', 'content', ['x'], ['/a'])
            probe.cached('bc', 'content', ['x'], ['/a'])
            self.assertEqual(exchange.call_count, 1)
            probe.cached('bc', 'content', ['x'], ['/b'])
            probe.cached('bc', 'metadata', ['x'], ['/b'])
            self.assertEqual(exchange.call_count, 3)
            with mock.patch.object(probe, 'CACHE_TTL', 0):
                exchange.side_effect = lambda *a, **k: ([probe.unknown('failed')], 'failed')
                self.assertEqual(probe.cached('bc', 'content', ['x'], ['/a'])['x']['state'], 'unknown')
        for newer, older in [('unknown', 'present'), ('present', 'unknown')]:
            probe._cache.clear()
            ready, done = threading.Event(), threading.Event()
            def late():
                ready.set()
                done.wait(2)
                probe._publish('bc', 'metadata', {'x': dict(state=older)}, (), 1)
            thread = threading.Thread(target=late)
            thread.start()
            self.assertTrue(ready.wait(2))
            probe._publish('bc', 'metadata', {'x': dict(state=newer)}, (), 2)
            done.set()
            thread.join(2)
            self.assertEqual(probe._cache[('bc','metadata','x',probe.policy_digest(()))]['value']['state'], newer)

    def test_host_lock_covers_collection_dispatch_publication(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def channel(host, channel, items, **kwargs):
            calls.append(list(items))
            entered.set()
            self.assertTrue(release.wait(2))
            return [dict(state='absent') for _ in items], 'ok'
        with mock.patch.object(probe, '_channel', side_effect=channel):
            a = threading.Thread(target=probe.cached, args=('bc', 'metadata', ['a']))
            b = threading.Thread(target=probe.cached, args=('bc', 'metadata', ['a', 'b']))
            a.start()
            self.assertTrue(entered.wait(2))
            b.start()
            self.assertEqual(calls, [['a']])
            release.set()
            a.join(2); b.join(2)
            self.assertEqual(calls, [['a'], ['b']])

    def test_metadata_flip_after_ttl(self):
        self.file.unlink()
        with mock.patch.object(probe, 'CACHE_TTL', 0):
            self.assertEqual(probe.cached('', 'metadata', [str(self.file)])[str(self.file)]['state'], 'absent')
            self.file.write_text('{}')
            self.assertEqual(probe.cached('', 'metadata', [str(self.file)])[str(self.file)]['state'], 'present')

    def test_root_alias_resolution_and_vanishing_policy(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root)
        self.assertEqual(probe.resolve_roots('', [str(alias)]), (str(self.root),))
        config = self.root / 'projects/config/rdash-roots.yaml'
        config.parent.mkdir(parents=True)
        config.write_text('bc:\n  - /alias\n')
        with mock.patch.object(probe, 'resolve_roots', return_value=('/resolved',)) as resolve:
            self.assertEqual(load_roots(self.root / "projects/config", ssh_hosts=('bc',)), (('bc','/resolved'),))
            resolve.assert_called_once_with('bc', ['/alias'])
        with mock.patch.object(probe, 'resolve_roots', return_value=None):
            self.assertEqual(load_roots(self.root / "projects/config", ssh_hosts=('bc',)), (('bc',None),))
        # Resolve once, then remove the resolved root; do not silently omit it.
        directory = self.root / 'vanishing'
        directory.mkdir()
        pinned = probe.resolve_roots('', [str(directory)])
        directory.rmdir()
        self.assertEqual(self.read([directory / 'file'], pinned)[str(directory / 'file')]['reason'], 'root_unavailable')

    def test_fixed_worker_definitions_are_shared(self):
        namespace = {'__name__':'fixture'}
        exec(probe.PROGRAM, namespace)
        with mock.patch.object(probe, '_run', return_value='500_0|COMPLETED\n500_1|FAILED\n500_1.extern|COMPLETED\n'):
            expected = probe.scheduler([500])
        namespace['_run'] = lambda command: '500_0|COMPLETED\n500_1|FAILED\n500_1.extern|COMPLETED\n'
        self.assertEqual(namespace['scheduler']([500]), expected)

    def test_frontend_live_order_snapshot_and_text_safety(self):
        import shutil
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed only for this optional DOM fixture test')
        script = Path(__file__).resolve().parents[1] / 'app/static/app.js'
        javascript = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.value = ''; }
  set textContent(value) { this.children = []; this.text = String(value); }
  get textContent() { return (this.text || '') + this.children.map(c => c.textContent).join(''); }
  set innerHTML(value) { throw Error('Unsafe HTML insertion'); }
  append(...values) { for (const v of values) this.children.push(...(v.tag === 'fragment' ? v.children : [v])); }
  replaceChildren() { this.children = []; this.text = ''; }
  setAttribute(name, value) { (this.attributes ||= {})[name] = String(value); }
  getAttribute(name) { return (this.attributes || {})[name] ?? null; }
}
const nodes = new Map();
const document = {getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id); },
  createElement: tag => new Element(tag), createDocumentFragment: () => new Element('fragment'),
  hidden: false, addEventListener() {},
  createTextNode(value) { const n = new Element('text'); n.textContent = value; return n; }};
const context = vm.createContext({document, console, Date});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8').split('(async () => {')[0], context);
vm.runInContext(String.raw`showBody({body: '## Objective\n<img src=x onerror=bad>\n[x](javascript:evil)\n<!-- radd-status:begin -->\nGenerated 2026-01-01 12:00 UTC\nold snapshot\n<!-- radd-status:end -->\n## Ideas and discussion\nNotes',
 results:[{name:'NERL',state:'present',value:.612,baseline:.604,delta:.008,direction:'higher',as_of:1}],
 artifacts:[{label:'blocker',path:'/x',state:'absent'}]});`, context);
const body = nodes.get('body');
const headings = body.children.filter(c => /^h[1-6]$/.test(c.tag)).map(c => c.textContent);
assert(headings.indexOf('Result vs. contract') < headings.indexOf('Contract'));
assert(headings.indexOf('Contract') < headings.indexOf('Live artifacts'));
assert(headings.indexOf('Live artifacts') < headings.indexOf('Ideas and discussion'));
const details = body.children.find(c => c.tag === 'details');
assert(details && !details.open);
assert(details.children[0].textContent.includes('minutes old'));
assert(!body.children.filter(c => c !== details).some(c => c.textContent.includes('old snapshot')));
function all(n) { return [n, ...n.children.flatMap(all)]; }
assert(!all(body).some(c => c.tag === 'img' || c.tag === 'a'));
assert(all(body).some(c => c.className === 'delta-favorable'));
console.log('DOM fixture: ordered live sections, collapsed dated snapshot, safe text, delta color OK');
'''
        done = subprocess.run([node, '-e', javascript, str(script)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('delta color OK', done.stdout)

    def test_frozen_msi_card_declarations_batch_and_refresh(self):
        # Frozen declaration-only fixtures read on 2026-09-16, never refreshed
        # from the concurrently edited real cards during tests.
        fences = ['```probe-status\n{\n  "schema_version": 1,\n  "host": "bc",\n  "artifacts": {\n    "eb2 val affinity": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/liconn_final_banis_plus_tube/20260728_032436/test_step=00200000/val/raw_x1_ch0-1-2.h5",\n    "eb2 200k checkpoint": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/liconn_final_banis_plus_tube/20260728_032436/checkpoints/step=00200000.ckpt",\n    "eb8 200k checkpoint": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/liconn_final_banis_plus_tube_4gpu/20260910_060545/checkpoints/step=00200000.ckpt",\n    "eb8 val affinity": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/liconn_final_banis_plus_tube_4gpu/20260910_060545/test_step=00200000/val/raw_x1_ch0-1-2.h5",\n    "eb8 val decode + score": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_ist_eb8/abiss",\n    "eb2 vs eb8 GT-free comparison": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_moe/compare_mip1_eb8",\n    "eb8 ExPID96 18x decode": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_moe/eb8/ExPID96_S1_40XW002_18x/ExPID96_S1_40XW002_18x_seg_abiss_mt0600.h5",\n    "eb8 ExPID99 18x decode (1Byqvupl)": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_moe/eb8/ExPID99_18x_2_cerebellum_1Byqvupl/mt_sweep.json",\n    "eb8 ExPID99 18x decode (1m2f9z4J)": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_moe/eb8/ExPID99_18x_2_cerebellum_1m2f9z4J/mt_sweep.json",\n    "per-model mt sweep (eb2)": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_ist/mt_sweep/eb2_slab_sweep.json",\n    "per-model mt sweep (eb8)": "/projects/weilab/weidf/lib/pytorch_connectomics/outputs/neuron_liconn_ist/mt_sweep/eb8_slab_sweep.json"\n  },\n  "jobs": [3013750, 3013760, 3013899, 3014044, 3014277]\n}\n```\n', '```probe-status\n{\n  "schema_version": 1,\n  "host": "bc",\n  "artifacts": {\n    "metrics_module": "/projects/weilab/weidf/lib/pytorch_connectomics/connectomics/metrics/unsupervised",\n    "pytc_checkout": "/projects/weilab/weidf/lib/pytorch_connectomics"\n  },\n  "jobs": []\n}\n```\n']
        (self.root / 'projects/msi_liconn_deploy').mkdir(parents=True)
        settings = Settings(self.root, self.root / 'cache', 0, host_alias='bc')
        records = [dict(body=body) for body in fences]
        calls = []
        state = ['absent']
        def channel(host, channel, items, **kwargs):
            calls.append((host, channel, list(items)))
            if channel == 'jobs':
                return [dict(tasks={}, reduced='unknown') for _ in items], 'ok'
            return [dict(state=state[0], kind='file', size=3, mtime=1) for _ in items], 'ok'
        with mock.patch.object(probe, '_channel', side_effect=channel), mock.patch.object(probe, 'CACHE_TTL', 0):
            probe.annotate_status(records, settings, 'msi_liconn_deploy')
            blocker = next(a for a in records[0]['artifacts'] if a['label'] == 'eb8 val affinity')
            self.assertEqual(blocker['state'], 'absent')
            self.assertEqual([c[1] for c in calls], ['jobs', 'metadata'])
            self.assertEqual(len(calls[1][2]), 13)
            self.assertEqual(records[1]['jobs'], [])
            state[0] = 'present'
            probe.annotate_status(records, settings, 'msi_liconn_deploy')
            self.assertEqual(next(a for a in records[0]['artifacts'] if a['label'] == 'eb8 val affinity')['state'], 'present')
        self.assertEqual([r['body'] for r in records], fences)
