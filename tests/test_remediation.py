"""Check staging and failure handling with a simulated container runner."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ('src/catalog/go.mod', 'src/catalog/go.sum', 'src/orders/go.mod',
         'src/orders/go.sum', 'src/checkout/package.json', 'src/checkout/yarn.lock')
FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args == ['info']:
    raise SystemExit(0)
stage = pathlib.Path(args[args.index('-v') + 1].rsplit(':', 1)[0])
workdir = args[args.index('-w') + 1]
if workdir.endswith(('catalog', 'orders')):
    folder = stage / workdir.removeprefix('/work/')
    (folder / 'go.mod').write_text('module fixture\n\ngo 1.26.0\n')
    (folder / 'go.sum').write_text('updated checksums\n')
elif workdir.endswith('checkout'):
    (stage / 'src/checkout/yarn.lock').write_text('updated lockfile\n')
else:
    mode = os.environ['TERO_TEST_SCAN']
    if mode == 'fail':
        raise SystemExit(1)
    results = [{'Target': '/work/' + name, 'Vulnerabilities': []} for name in (
        'src/admin/package-lock.json', 'src/ui/package-lock.json', 'src/cart/requirements.lock',
        'src/catalog/go.mod', 'src/orders/go.mod', 'src/checkout/yarn.lock')]
    if mode == 'incomplete':
        results.pop()
    if mode == 'high':
        results[0]['Vulnerabilities'].append({'Severity': 'HIGH'})
    (stage / 'reports/dependencies.json').write_text(json.dumps({'Results': results}))
    if os.environ.get('TERO_TEST_CONCURRENT'):
        target = pathlib.Path(os.environ['TERO_TEST_ROOT']) / 'src/catalog/go.mod'
        target.write_text('concurrent user change\n')
'''


class RemediationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copy(ROOT / 'scripts/remediate-dependencies.sh', self.root / 'scripts')
        for name in FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('original\n')
        (self.root / 'src/checkout/package.json').write_text(json.dumps({'dependencies': {}}))
        for service, image in [('catalog', 'golang:fixture'), ('orders', 'golang:fixture'),
                               ('checkout', 'node:fixture')]:
            (self.root / f'src/{service}/Dockerfile').write_text(f'FROM {image}\n')
        (self.root / '.ci').mkdir()
        (self.root / '.ci/policy.json').write_text(json.dumps({
            'security': {'blocked_severities': ['HIGH', 'CRITICAL'], 'ignore_unfixed': False}}))
        self.original = {name: (self.root / name).read_bytes() for name in FILES}
        binary = self.root / 'bin'
        binary.mkdir()
        (binary / 'docker').write_text(FAKE_DOCKER)
        (binary / 'docker').chmod(0o755)
        self.env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                        TERO_TEST_ROOT=str(self.root), TERO_TEST_SCAN='pass')

    def run_script(self, mode, concurrent=False):
        self.env['TERO_TEST_SCAN'] = mode
        if concurrent:
            self.env['TERO_TEST_CONCURRENT'] = '1'
        return subprocess.run(['bash', 'scripts/remediate-dependencies.sh', '--apply'],
                              cwd=self.root, env=self.env, capture_output=True, text=True, timeout=30)

    def assert_original_files(self):
        for name, data in self.original.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)

    def test_failed_scan_preserves_all_original_dependency_files(self):
        result = self.run_script('fail')
        self.assertNotEqual(result.returncode, 0)
        self.assert_original_files()

    def test_incomplete_report_preserves_all_original_dependency_files(self):
        result = self.run_script('incomplete')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('incompleto', result.stderr)
        self.assert_original_files()

    def test_high_finding_blocks_copy_even_if_scanner_returns_zero(self):
        result = self.run_script('high')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hallazgos=1', result.stderr)
        self.assert_original_files()

    def test_success_copies_manifest_and_generated_locks_together(self):
        result = self.run_script('pass')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        package = json.loads((self.root / 'src/checkout/package.json').read_text())
        self.assertEqual(package['dependencies']['@nestjs/platform-express'], '11.2.9')
        self.assertEqual((self.root / 'src/checkout/yarn.lock').read_text(), 'updated lockfile\n')
        self.assertIn('1.26.0', (self.root / 'src/catalog/go.mod').read_text())

    def test_concurrent_local_change_is_preserved_and_blocks_all_other_copies(self):
        result = self.run_script('pass', concurrent=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('modificados durante', result.stderr)
        for name in FILES[1:]:
            self.assertEqual((self.root / name).read_bytes(), self.original[name], name)
        self.assertEqual((self.root / FILES[0]).read_text(), 'concurrent user change\n')


if __name__ == '__main__':
    unittest.main()
