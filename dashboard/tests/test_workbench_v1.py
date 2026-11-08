"""Regression tests for owner allocation and the read-only workbench views."""
import concurrent.futures
import multiprocessing
import os
import shutil
import subprocess
import sys
import threading
from unittest import mock

from fixtures import RepoTest
from dashboard.app import cards, focus, ladder, lint
from dashboard.app.config import Settings
from dashboard.app.safety import Error


def _process_capture(root, cache, barrier, connection):
    try:
        settings = Settings(root, cache, 0, owner='alice')
        barrier.wait(timeout=10)
        try:
            result = cards.create_idea(settings, 'alpha', 'parallel')
            connection.send(('ok', result['metadata']['id']))
        except Error as exc:
            connection.send((exc.status, exc.payload['error']))
    finally:
        connection.close()


class WorkbenchV1Tests(RepoTest):
    def owner(self, repo=None, name='alice'):
        return Settings(repo or self.repo, self.cache, 0, owner=name)

    def assert_allocations(self, results):
        ids = [identifier for status, identifier in results if status == 'ok']
        self.assertTrue(ids)
        self.assertTrue(all(result[0] == 'ok' or result == (503, 'busy') for result in results), results)
        self.assertEqual(sorted(ids), [f'ALPHA-IDEA-alice-{i:03}' for i in range(1, len(ids) + 1)])
        files = list((self.repo / 'projects/alpha/cards/inbox').glob('*.md'))
        self.assertEqual(len(files), len(ids))
        self.assertEqual({cards.parse(path.read_bytes(), 'alpha')[0]['id'] for path in files}, set(ids))

    def test_eight_concurrent_threads(self):
        settings = self.owner()
        barrier = threading.Barrier(8)
        def capture(_):
            barrier.wait(timeout=10)
            try:
                return 'ok', cards.create_idea(settings, 'alpha', 'parallel')['metadata']['id']
            except Error as exc:
                return exc.status, exc.payload['error']
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(capture, range(8)))
        self.assertEqual(len(results), 8)
        self.assert_allocations(results)

    def test_two_concurrent_processes(self):
        ctx = multiprocessing.get_context('fork')
        barrier = ctx.Barrier(2)
        receivers, processes = [], []
        for _ in range(2):
            receive, send = ctx.Pipe(duplex=False)
            process = ctx.Process(target=_process_capture, args=(self.repo, self.cache, barrier, send))
            process.start()
            send.close()
            receivers.append(receive)
            processes.append(process)
        for process in processes:
            self.addCleanup(lambda p=process: p.terminate() if p.is_alive() else None)
        results = []
        for receive in receivers:
            self.assertTrue(receive.poll(15), 'worker did not return')
            results.append(receive.recv())
            receive.close()
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
        self.assert_allocations(results)

    def test_two_clone_attribution_and_same_owner_clash(self):
        clone = self.root / 'clone'
        shutil.copytree(self.repo, clone)
        alice, bob = self.owner(), self.owner(clone, 'bob')
        first = cards.create_idea(alice, 'alpha', 'same title')
        other = cards.create_idea(bob, 'alpha', 'same title')
        self.assertEqual((first['owner'], first['metadata']['id']), ('alice', 'ALPHA-IDEA-alice-001'))
        self.assertEqual((other['owner'], other['metadata']['id']), ('bob', 'ALPHA-IDEA-bob-001'))
        source = clone / 'projects/alpha/cards' / other['card']
        target = self.repo / 'projects/alpha/cards' / other['card']
        shutil.copyfile(source, target)
        self.assertEqual(cards.parse(target.read_bytes(), 'alpha')[0]['owner'], 'bob')
        self.assertEqual(lint.duplicate_ids(alice), [])
        self.assertEqual(cards.create_idea(alice, 'alpha', 'next')['metadata']['id'], 'ALPHA-IDEA-alice-002')

        # Two fresh clones for the same owner both allocate 001 before merging.
        left, right = self.root / 'left', self.root / 'right'
        shutil.copytree(clone, left)
        shutil.copytree(clone, right)
        lcard = cards.create_idea(self.owner(left), 'alpha', 'left')
        rcard = cards.create_idea(self.owner(right), 'alpha', 'right')
        self.assertEqual(lcard['metadata']['id'], 'ALPHA-IDEA-alice-001')
        self.assertEqual(rcard['metadata']['id'], lcard['metadata']['id'])
        shutil.copyfile(right / 'projects/alpha/cards' / rcard['card'], left / 'projects/alpha/cards' / rcard['card'])
        findings = lint.duplicate_ids(self.owner(left))
        clashes = [item for item in findings if item[1] == lcard['metadata']['id'] and item[2] == 'duplicate id']
        self.assertEqual(len(clashes), 1)
        self.assertIn(lcard['card'], clashes[0][0])
        self.assertIn(rcard['card'], clashes[0][0])

    def test_parked_highest_id_is_not_reused(self):
        settings = self.owner()
        first = cards.create_idea(settings, 'alpha', 'first')
        second = cards.create_idea(settings, 'alpha', 'second')
        parked = cards.edit_card(settings, 'alpha', second['card'], second['revision'], stage='parked', text='Parked after review')
        self.assertEqual(parked['metadata']['stage'], 'parked')
        self.assertEqual(first['metadata']['id'], 'ALPHA-IDEA-alice-001')
        self.assertEqual(cards.create_idea(settings, 'alpha', 'third')['metadata']['id'], 'ALPHA-IDEA-alice-003')

    def test_counter_spans_tasks_but_ignores_legacy_ids(self):
        folder = self.repo / 'projects/alpha/cards'
        (folder / 'prior.md').write_bytes(self.card.read_bytes().replace(
            b'id: ALPHA-QUESTION', b'id: ALPHA-MODEL-alice-007\nowner: alice'))
        (folder / 'legacy.md').write_bytes(self.card.read_bytes().replace(
            b'id: ALPHA-QUESTION', b'id: ALPHA-MODEL-048'))
        result = cards.create_idea(self.owner(), 'alpha', 'next')
        self.assertEqual(result['metadata']['id'], 'ALPHA-IDEA-alice-008')
        self.assertEqual(cards.create_idea(self.owner(name='bob'), 'alpha', 'next')['metadata']['id'],
                         'ALPHA-IDEA-bob-001')

    def test_configured_owner_allows_capture_when_required(self):
        directory = self.repo / 'projects/config'
        directory.mkdir()
        (directory / 'rdash-owner.json').write_text('{"require_owner": true}')
        result = cards.create_idea(self.owner(), 'alpha', 'owned')
        self.assertEqual(result['owner'], 'alice')
        self.assertEqual(result['metadata']['id'], 'ALPHA-IDEA-alice-001')

    def test_unset_owner_matches_baseline_golden(self):
        # Literal output from 521204f create_idea for this template and frozen date.
        (self.repo / 'dashboard/TEMPLATE.md').write_text('---\nid: TEMPLATE\n---\n\n## Ideas and discussion\n\n- YYYY-MM-DD placeholder\n')
        self.assertFalse(self.settings.require_owner)
        with mock.patch.object(cards, '_today', return_value='2026-11-07'):
            record = cards.create_idea(self.settings, 'alpha', 'A new idea', idea='Try this')
        self.assertEqual(record['card'], 'inbox/a-new-idea.md')
        self.assertEqual((self.repo / 'projects/alpha/cards' / record['card']).read_bytes(),
                         b'---\nid: ALPHA-A-NEW-IDEA\ntitle: A new idea\nproject: alpha\ntrack: model\nstage: idea\ncreated: 2026-11-07\nupdated: 2026-11-07\n---\n\n## Ideas and discussion\n\n- 2026-11-07 \xe2\x80\x94 rdash: Try this\n')

    def test_ladder_gate_states_and_unknown(self):
        (self.repo / 'LADDER.md').write_text('## Rungs\n| Month | G1 | G2 | G3 |\n|---|---|---|---|\n| 2026-11 | [failed] failed test | [foo] unrecognized | target bar |\n| 2026-12 | [met] done | [open] pending | — |\n| 2027-01 | - | | proposal |\n')
        result = ladder.read(self.settings)
        one, two, three = result['rows']
        self.assertEqual(one['g1'], {'state': 'failed', 'text': 'failed test'})
        self.assertEqual(one['g2'], {'state': 'target', 'text': '[foo] unrecognized'})
        self.assertEqual(one['g3'], {'state': 'target', 'text': 'target bar'})
        self.assertEqual(two['g1'], {'state': 'met', 'text': 'done'})
        self.assertEqual(two['g2'], {'state': 'open', 'text': 'pending'})
        self.assertEqual(two['g3']['state'], 'none')
        self.assertEqual(three['g1']['state'], 'none')
        self.assertEqual(three['g2']['state'], 'none')
        self.assertEqual([row['gates_met'] for row in result['rows']], [0, 1, 0])
        self.assertIn('Unknown gate tag: [foo]', result['errors'])

    def test_focus_without_next(self):
        directory = self.repo / 'projects/alpha/focus'
        directory.mkdir()
        (directory / 'F-001.md').write_text('# Notebook\nDecision needed: none\n## Other\n- Not a next item\n')
        notebook = focus.read(self.settings, 'alpha')['notebooks'][0]
        self.assertFalse(notebook['has_next'])
        self.assertEqual(notebook['next'], [])

    def test_lint_cli_clean_and_finding_exit_codes(self):
        env = dict(os.environ, RDASH_REPO_ROOT=str(self.repo), PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-m', 'dashboard.app.lint']
        clean = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(clean.stdout, '')
        duplicate = self.repo / 'projects/alpha/cards/duplicate.md'
        shutil.copyfile(self.card, duplicate)
        failed = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertIn('ALPHA-QUESTION duplicate id', failed.stdout)
        self.assertIn('question.md', failed.stdout)
        self.assertIn('duplicate.md', failed.stdout)

    def test_absent_owner_config_defaults_false(self):
        self.assertFalse((self.repo / 'projects/config/rdash-owner.json').exists())
        self.assertFalse(Settings.from_env({'RDASH_REPO_ROOT': str(self.repo)}).require_owner)
