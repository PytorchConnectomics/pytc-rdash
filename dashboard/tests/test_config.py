import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from dashboard.app import config, launch, projects
from dashboard.tests.fixtures import RepoTest, SAMPLE


class ConfigTests(RepoTest):
    def test_override_validation_and_default(self):
        settings = config.Settings.from_env({'RDASH_REPO_ROOT': str(self.repo)})
        self.assertEqual(settings.config_dir, self.repo / 'projects/config')
        directory = self.root / 'config'; directory.mkdir()
        for value in ('relative', str(directory / 'missing'), ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.Settings.from_env({'RDASH_REPO_ROOT': str(self.repo), 'RDASH_CONFIG_DIR': value})
        settings = config.Settings.from_env({'RDASH_REPO_ROOT': str(self.repo), 'RDASH_CONFIG_DIR': str(directory)})
        self.assertEqual(settings.config_dir, directory)

    def test_labels_bounded_validated_loaded_once_and_fallback(self):
        directory = self.root / 'config'; directory.mkdir()
        path = directory / 'project-labels.json'
        env = {'RDASH_REPO_ROOT': str(self.repo), 'RDASH_CONFIG_DIR': str(directory)}
        self.assertEqual(config.Settings.from_env(env).project_labels, {})
        path.write_text(json.dumps({'alpha': 'Alpha label'}))
        settings = config.Settings.from_env(env)
        path.write_text('{}')
        self.assertEqual({p['id']: p['label'] for p in projects.list_projects(settings)}, {'alpha': 'Alpha label', 'beta': 'beta'})
        for data in ('not json', '[]', '{"a": 2}', 'x' * 65537):
            path.write_text(data)
            with self.assertLogs(level='WARNING'):
                self.assertEqual(config.Settings.from_env(env).project_labels, {})

    def test_unlabelled_project_uses_spaced_name(self):
        project = self.repo / 'projects/2026_new-project'
        project.mkdir()
        (project / 'spec.md').write_text('# New project\n')
        settings = config.Settings.from_env({'RDASH_REPO_ROOT': str(self.repo)})
        labels = {p['id']: p['label'] for p in projects.list_projects(settings)}
        self.assertEqual(labels['2026_new-project'], '2026 new project')

    def test_student_alias_config_and_launch(self):
        directory = self.root / 'config'; directory.mkdir()
        root = '/projects/weilab/shared/runs'
        for name in ('rdash-roots.yaml', 'rdash-launch.yaml'):
            (directory / name).write_text('bc:\n  - ' + root + '\n')
        env = {'RDASH_REPO_ROOT': str(self.repo), 'RDASH_CONFIG_DIR': str(directory), 'RDASH_SSH_HOSTS': 'bc'}
        block = {'schema_version': 1, 'host': 'bc', 'launch': {'script': 'scripts/slurm/job.sbatch'}, 'jobs': []}
        self.card.write_bytes(SAMPLE + ('\n```probe-status\n' + json.dumps(block) + '\n```\n').encode())
        calls = []
        tree = 'a' * 40
        responses = [(b'', 'ok'), ((root + '/alpha/stage/' + tree + '\n').encode(), 'ok'), (b'', 'ok')]
        def exchange(argv, payload, **kwargs):
            calls.append(argv)
            return responses.pop(0)
        with mock.patch.object(launch.inspection, 'resolve_roots', side_effect=lambda host, paths: tuple(paths)) as resolve, \
             mock.patch.object(launch.inspection, '_exchange', side_effect=exchange), \
             mock.patch.object(launch, 'committed_scripts', return_value=('0123456789ab', tree, b'TAR')):
            settings = config.Settings.from_env(env)
            self.assertEqual(settings.result_roots, (('bc', root),))
            self.assertTrue(launch.launch(settings, 'alpha', 'question.md', test_only=True)['test_only'])
            self.assertTrue(all(call.args[0] == 'bc' for call in resolve.call_args_list))
            self.assertEqual(len(calls), 3)
            self.assertTrue(all('bc' in argv for argv in calls))
            self.assertIn(root + '/alpha/results', calls[-1][-1])
            self.assertNotIn('weidf', str(calls))
            self.card.write_text(self.card.read_text().replace('"host": "bc"', '"host": "student1@a002.bc.edu"'))
            with self.assertRaises(launch.Error):
                launch.launch(settings, 'alpha', 'question.md', test_only=True)
            self.assertEqual(len(calls), 3)


class EnvFileTests(unittest.TestCase):
    def test_parser_rejects_commands_unknown_keys_and_preserves_explicit_env(self):
        helper = Path(__file__).resolve().parents[1] / 'app/rdash_env.sh'
        with tempfile.TemporaryDirectory(prefix='rdash-env-') as temp:
            root = Path(temp); file = root / 'env'; sentinel = root / 'executed'
            env = dict(os.environ, RDASH_ENV_FILE=str(file))
            for key in ('RDASH_HOST', 'RDASH_SSH_HOSTS', 'RDASH_CONFIG_DIR'):
                env.pop(key, None)
            command = ['bash', '-c', 'source "$1"; printf "%s|%s|%s" "$RDASH_HOST" "$RDASH_SSH_HOSTS" "$RDASH_CONFIG_DIR"', 'test', str(helper)]
            for text in ('RDASH_HOST=$(touch ' + str(sentinel) + ')\n', 'UNKNOWN_KEY=yes\n', 'RDASH_SSH_HOSTS=user@host\n'):
                file.write_text(text)
                result = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(sentinel.exists())
            file.write_text('# comment\n\nRDASH_HOST=g08\nRDASH_SSH_HOSTS=bc\nRDASH_CONFIG_DIR=/tmp/config\n')
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout, 'g08|bc|/tmp/config')
            result = subprocess.run(command, env=dict(env, RDASH_HOST='explicit', RDASH_SSH_HOSTS=''), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout, 'explicit||/tmp/config')
            # Both entry points invoke the helper before any host or lifecycle work.
            file.write_text('UNKNOWN_KEY=yes\n')
            for name in ('hub.sh', 'research_dash.sh'):
                result = subprocess.run(['bash', str(helper.parent / name), 'status'], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('invalid environment file line', result.stderr)
