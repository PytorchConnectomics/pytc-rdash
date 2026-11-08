import concurrent.futures
import shutil
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
from fixtures import RepoTest, SOURCE, SAMPLE
from dashboard.app import cards, focus, ladder, lint, questions
from dashboard.app.config import Settings
from dashboard.app.safety import Error


class WorkbenchTests(RepoTest):
    def test_owner_allocation_and_lint(self):
        shutil.copyfile(FIXTURES / 'TEMPLATE.md', self.repo / 'dashboard/TEMPLATE.md')
        alice = Settings(self.repo, self.cache, 0, owner='alice')
        first = cards.create_idea(alice, 'alpha', 'first')
        second = cards.create_idea(alice, 'alpha', 'second')
        self.assertEqual(first['owner'], 'alice')
        self.assertEqual(first['metadata']['id'], 'ALPHA-IDEA-alice-001')
        self.assertEqual(second['metadata']['id'], 'ALPHA-IDEA-alice-002')
        self.assertRegex(first['card'], r'inbox/\d{4}-\d\d-\d\d_alice_first.md')
        bob = Settings(self.repo, self.cache, 0, owner='bob')
        self.assertEqual(cards.create_idea(bob, 'alpha', 'first')['metadata']['id'], 'ALPHA-IDEA-bob-001')
        duplicate = self.repo / 'projects/alpha/cards/duplicate.md'
        duplicate.write_bytes((self.repo / 'projects/alpha/cards' / first['card']).read_bytes())
        self.assertTrue(any('duplicate id' in item[2] for item in lint.duplicate_ids(alice)))
        duplicate.write_bytes(duplicate.read_bytes().replace(b'owner: alice', b'owner: bob'))
        self.assertTrue(any('owner mismatch' in item[2] for item in lint.duplicate_ids(alice)))

    def test_required_owner_and_validation(self):
        directory = self.repo / 'projects/config'; directory.mkdir()
        (directory / 'rdash-owner.json').write_text('{"require_owner": true}')
        settings = Settings(self.repo, self.cache, 0)
        self.error(409, 'owner_required', cards.create_idea, settings, 'alpha', 'first')
        self.assertFalse((self.repo / 'projects/alpha/cards/inbox').exists())
        with self.assertRaises(ValueError):
            Settings(self.repo, self.cache, 0, owner='Bad')
        (directory / 'rdash-owner.json').write_text('{}')
        with self.assertRaises(ValueError):
            Settings(self.repo, self.cache, 0)

    def test_ladder_and_focus(self):
        ladderfile = self.repo / 'LADDER.md'
        self.assertTrue(ladder.read(self.settings)['missing'])
        shutil.copyfile(FIXTURES / 'LADDER.md', ladderfile)
        result = ladder.read(self.settings)
        self.assertEqual(len(result['rows']), 9)
        self.assertEqual([r['gates_met'] for r in result['rows']], [1, 1, 0, 1, 0, 0, 0, 0, 0])
        folder = self.repo / 'projects/alpha/focus'; folder.mkdir()
        (folder / 'F-001.md').write_text('# Title\nDecision needed: yes\n## Next\n- [ ] todo\n- [x] done\n2. numbered\n')
        notebook = focus.read(self.settings, 'alpha')['notebooks'][0]
        self.assertEqual(notebook['decision'], 'yes')
        self.assertEqual(notebook['next'], [dict(text='todo', done=False), dict(text='done', done=True), dict(text='numbered', done=False)])
        (folder / 'F-002.md').symlink_to(folder / 'F-001.md')
        with self.assertRaises(Error):
            focus.read(self.settings, 'alpha')

    def test_questions_optional_fields(self):
        folder = self.repo / 'projects/alpha/questions'; folder.mkdir()
        (folder / 'Q-001_x.md').write_text('---\nid: Q-001\ntitle: Test\nrung: 20um\nmetric: nerl\n---\n')
        question = questions.read(self.settings, 'alpha')['questions'][0]
        self.assertEqual((question['rung'], question['metric'], question['train_data']), ('20um', 'nerl', ''))
