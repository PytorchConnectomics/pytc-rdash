import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('check_plan', HERE / 'check_plan.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PlanTests(unittest.TestCase):
    def test_template_and_frozen_checks(self):
        self.assertEqual(checker.check(HERE / 'plan.md'), 1)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'plan.md'
            good = '## Review checks\n' + ''.join(f'S{i} Data: concrete. Evidence path: app.py\n' for i in range(1, 5))
            path.write_text(good)
            self.assertEqual(checker.check(path), 0)
            path.write_text(good.replace('S3 Data: concrete. Evidence path: app.py\n', ''))
            self.assertEqual(checker.check(path), 1)
            path.write_text(good.replace('app.py', '<path>', 1))
            self.assertEqual(checker.check(path), 1)
