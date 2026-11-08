import itertools
import json
from dataclasses import replace
from unittest import mock
from fixtures import RepoTest
from dashboard.app import cards, inspection, results
from dashboard.app.server import enrich
from dashboard.app.config import Settings


class ResultTests(RepoTest):
    def setUp(self):
        super().setUp()
        inspection._cache.clear()
        self.settings = replace(self.settings, stat_local=True)
        self.directory = self.repo / 'projects/alpha/results'
        self.directory.mkdir()
        self.metric = self.directory / 'metric.json'
        self.metric.write_text('{"nerl":0.612}')
        self.row = dict(name='val NERL', path='results/metric.json', key='nerl', baseline=.604428, direction='higher')

    def observe(self, row=None):
        body = '```probe-status\n' + json.dumps(dict(results=[row or self.row])) + '\n```\n'
        records = [dict(body=body)]
        with mock.patch.object(inspection, 'CACHE_TTL', 0):
            results.annotate(records, self.settings, 'alpha')
        return records[0]['results'][0]

    def test_measurement_baseline_delta_asof_and_deleted_file(self):
        row = self.observe()
        self.assertEqual(row['value'], .612)
        self.assertEqual(row['baseline'], .604428)
        self.assertAlmostEqual(row['delta'], .007572)
        self.assertEqual(row['as_of'], self.metric.stat().st_mtime)
        self.metric.unlink()
        row = self.observe()
        self.assertEqual(row['state'], 'absent')
        self.assertNotIn('value', row)
        self.assertNotIn('delta', row)

    def test_invalid_metrics_and_declarations(self):
        for content, reason in [('not JSON', 'invalid_json'), ('{}', 'missing_key'),
                                ('{"nerl":true}', 'boolean_metric'),
                                ('{"nerl":NaN}', 'nonfinite_metric'),
                                ('{"nerl":Infinity}', 'nonfinite_metric'),
                                ('{"nerl":"0.6"}', 'nonnumeric_metric')]:
            self.metric.write_text(content)
            row = self.observe()
            self.assertEqual((row['state'], row['reason']), ('unreadable', reason))
            self.assertNotIn('value', row)
        for changes, reason in [(dict(path='result.csv'), 'unsupported_format'),
                                (dict(key='a.b.c.d.e.f.g.h.i'), 'key_too_deep'),
                                (dict(key='a..b'), 'empty_key_segment'),
                                (dict(key='a["x.y"]'), 'invalid_key_segment'),
                                (dict(baseline=True), 'invalid_baseline'),
                                (dict(direction='pass'), 'invalid_direction')]:
            self.assertEqual(self.observe(dict(self.row, **changes))['reason'], reason)
        # Dots are delimiters, never a literal part of an object-key segment.
        self.metric.write_text('{"a.b":1}')
        self.assertEqual(self.observe(dict(self.row, key='a.b'))['reason'], 'missing_key')

    def test_list_or_object_numeric_segment_and_depth_limit(self):
        for content in ('{"a":[7]}', '{"a":{"0":7}}'):
            self.metric.write_text(content)
            self.assertEqual(self.observe(dict(self.row, key='a.0'))['value'], 7)
        self.metric.write_text('{"nerl":' + '[' * 40 + '1' + ']' * 40 + '}')
        self.assertEqual(self.observe()['reason'], 'nesting_too_deep')
        self.metric.write_text('[' * 2000 + '1' + ']' * 2000)
        self.assertEqual(self.observe()['state'], 'unreadable')

    def test_no_baseline_is_measurement_only(self):
        row = dict(self.row)
        del row['baseline']
        observed = self.observe(row)
        self.assertEqual(observed['value'], .612)
        self.assertNotIn('baseline', observed)
        self.assertNotIn('delta', observed)
        self.assertNotIn('verdict', observed)

    def test_observation_matrix_preserves_authored_bytes(self):
        self.card.write_bytes(self.card.read_bytes().replace(b'stage: idea', b'stage: idea\nverdict: met') + '''
## Acceptance
- [x] Measured — evidence: results/metric.json
<!-- radd-status:begin -->
Generated old snapshot
<!-- radd-status:end -->
```probe-status
{"jobs":[123],"artifacts":{"blocker":"/fixture/blocker"}}
```
'''.encode())
        original = self.card.read_bytes()
        for job, artifact in itertools.product(('COMPLETED', 'FAILED', 'unknown'), ('present', 'absent', 'unknown')):
            def channel(host, channel, items, **kwargs):
                return ([dict(tasks={'123':dict(state=job, elapsed='', reason='')}, reduced=job) if channel == 'jobs'
                         else dict(state=artifact) for _ in items], 'ok')
            inspection._cache.clear()
            with mock.patch.object(inspection, '_channel', side_effect=channel):
                listed = enrich(self.settings, 'alpha', cards.list_cards(self.settings, 'alpha'))
                detail = enrich(self.settings, 'alpha', [cards.read_card(self.settings, 'alpha', 'question.md')])
            self.assertEqual(self.card.read_bytes(), original)
            self.assertTrue(listed[0]['acceptance']['items'][0]['checked'])
            self.assertEqual(detail[0]['verdict'], 'met')

    def test_never_executes_declared_script_or_job(self):
        sentinel = self.root / 'executed'
        self.metric.write_text('#!/bin/sh\ntouch ' + str(sentinel))
        self.metric.chmod(0o700)
        text = '```probe-status\n' + json.dumps(dict(jobs=['1;touch ' + str(sentinel)],
                      artifacts={'script': str(self.metric)}, results=[self.row])) + '\n```'
        self.card.write_text(self.card.read_text() + '\n' + text)
        original = self.card.read_bytes()
        original_exchange = inspection._exchange
        def exchange(argv, payload, **kwargs):
            self.assertNotIn(str(self.metric), ' '.join(argv))
            self.assertNotIn(str(sentinel), ' '.join(argv))
            return original_exchange(argv, payload, **kwargs)
        with mock.patch.object(inspection, '_exchange', side_effect=exchange):
            record = enrich(self.settings, 'alpha', cards.list_cards(self.settings, 'alpha'))[0]
        self.assertEqual(record['jobs'], [])
        self.assertEqual(record['results'][0]['reason'], 'invalid_json')
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.card.read_bytes(), original)

    def test_default_root_symlink_is_resolved_at_settings_load(self):
        import shutil
        shutil.rmtree(str(self.directory))
        actual = self.root / 'actual-results'
        actual.mkdir()
        (actual / 'metric.json').write_text('{"nerl":0.612}')
        self.directory.symlink_to(actual)
        self.settings = replace(self.settings)
        self.assertEqual(self.observe()['value'], .612)
        self.directory.unlink()
        self.directory.mkdir()
        self.metric.write_text('{"nerl":99}')
        # Config remains pinned to the initially resolved directory.
        self.assertEqual(self.observe()['value'], .612)

    def test_invalid_baseline_never_leaks_non_json_number(self):
        for value in (float('nan'), float('inf'), True):
            observed = self.observe(dict(self.row, baseline=value))
            self.assertEqual(observed['reason'], 'invalid_baseline')
            self.assertNotIn('baseline', observed)
            json.dumps(observed, allow_nan=False)

    def test_invalid_declaration_fields_remain_serializable(self):
        for field in ('name', 'path', 'key', 'source', 'direction'):
            observed = self.observe(dict(self.row, **{field: float('nan')}))
            self.assertEqual(observed['state'], 'unreadable')
            json.dumps(observed, allow_nan=False)
