import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('check_receipt', HERE / 'check_receipt.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

INTENT = '- intent E1 2026-11-22T21:05-05:00 submit host=bc card=cards/a.md job-name=x comment=y replay=never\n'
PROGRESS = ('## Progress\nProving check: eval/metrics.json → pass\n'
            'Changed since last iteration: nERL 0.61 → 0.63 (eval/metrics.json)\nNext: CONTINUE — one more seed\n')


class EffectsTests(unittest.TestCase):
    def run_effects(self, text):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'effects.md'
            path.write_text(text)
            return checker.check_effects(path)

    def test_template_is_clean_and_missing_file_is_fine(self):
        self.assertEqual(checker.check_effects(HERE / 'effects.md'), [])
        self.assertEqual(checker.check_effects(HERE / 'absent.md'), [])

    def test_open_intent_blocks(self):
        problems = self.run_effects(INTENT)
        self.assertEqual(len(problems), 1)
        self.assertIn('no settled line', problems[0])

    def test_settled_ok_passes_and_unknown_blocks(self):
        self.assertEqual(self.run_effects(INTENT + '- settled E1 2026-11-22T21:06-05:00 ok slurm=1\n'), [])
        self.assertIn('unknown', self.run_effects(INTENT + '- settled E1 t unknown\n')[0])

    def test_malformed_and_orphan(self):
        self.assertEqual(len(self.run_effects('- settled E2 t ok\n- intent oops\n')), 2)
        self.assertIn('outcome', self.run_effects(INTENT + '- settled E1 t maybe\n')[0])


class ProgressTests(unittest.TestCase):
    def test_template_fails_and_filled_passes(self):
        self.assertEqual(len(checker.check_progress(HERE / 'receipt.md')), 3)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'receipt.md'
            path.write_text('# r\n\n' + PROGRESS + '\n## What ran\n')
            self.assertEqual(checker.check_progress(path), [])
            path.write_text(PROGRESS.replace('→ pass', ''))
            self.assertEqual(len(checker.check_progress(path)), 1)

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'receipt.md').write_text(PROGRESS)
            self.assertEqual(checker.main([root]), 0)
            (Path(root) / 'effects.md').write_text(INTENT)
            self.assertEqual(checker.main([root]), 1)
            self.assertEqual(checker.main([root + '/nope']), 2)


if __name__ == '__main__':
    unittest.main()
