import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a' * 40
        self.manifest = {'commit': self.sha, 'images': {
            s: f'docker.io/test/tero-{s}@sha256:' + 'b' * 64 for s in load('manifest').SERVICES}}

    def test_release_requires_matching_commit_and_all_immutable_images(self):
        validate = load('manifest').validate
        self.assertIn('IMAGE_UI=docker.io/test/tero-ui@sha256:', validate(self.manifest, self.sha))
        invalid = copy.deepcopy(self.manifest)
        invalid['images']['ui'] = 'docker.io/test/tero-ui:latest'
        with self.assertRaises(ValueError): validate(invalid, self.sha)
        with self.assertRaises(ValueError): validate(self.manifest, 'c' * 40)
        del invalid['images']['cart']
        with self.assertRaises(ValueError): validate(invalid, self.sha)

    def test_zap_blocks_high_alerts_and_missing_evidence(self):
        enforce = load('zap_gate').enforce
        enforce({'site': [{'alerts': [{'riskcode': '2'}]}]}, 0)
        with self.assertRaises(ValueError): enforce({'site': [{'alerts': [{'riskcode': '3'}]}]}, 0)
        with self.assertRaises(ValueError): enforce({'site': []}, 0)
        with self.assertRaises(KeyError): enforce({}, 0)

    def test_production_requires_main_and_a_reviewer(self):
        validate = load('github_environments').validate
        environment = {'deployment_branch_policy': {'custom_branch_policies': True},
                       'protection_rules': [{'type': 'required_reviewers', 'reviewers': [{'id': 1}]}]}
        branches = {'branch_policies': [{'name': 'main', 'type': 'branch'}]}
        validate(environment, branches, 'main', True)
        with self.assertRaises(ValueError):
            validate(dict(environment, protection_rules=[]), branches, 'main', True)
        with self.assertRaises(ValueError):
            validate(environment, {'branch_policies': [{'name': '*'}]}, 'main', True)

    def test_quality_thresholds_block_coverage_bugs_and_missing_metrics(self):
        enforce = load('sonar_gate').enforce
        policy = json.loads((ROOT / '.ci/policy.json').read_text())['quality']
        good = {'new_lines': 10, 'new_lines_to_cover': 10, 'new_coverage': 85,
                'new_duplicated_lines_density': 0, 'new_bugs': 0, 'new_vulnerabilities': 0}
        def measures(values):
            return [{'metric': k, 'period': {'value': str(v)}} for k, v in values.items()]
        enforce(measures(good), policy)
        for key, value in [('new_coverage', 79), ('new_bugs', 1), ('new_vulnerabilities', 1), ('new_duplicated_lines_density', 4)]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                enforce(measures(dict(good, **{key: value})), policy)
        with self.assertRaises(KeyError): enforce([], policy)


class TrivyCommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / '.ci').mkdir()
        shutil.copy(ROOT / '.ci/policy.json', self.root / '.ci/policy.json')
        binary = self.root / 'bin'
        binary.mkdir()
        # Model the CLI incompatibility observed with Trivy 0.76.1 in CI.
        (binary / 'trivy').write_text(
            '#!/usr/bin/env python3\n'
            'import json, os, pathlib, sys\n'
            'args = sys.argv[1:]\n'
            'if args[0] == "image" and "--include-dev-deps" in args:\n'
            '    raise SystemExit("unknown flag: --include-dev-deps")\n'
            'pathlib.Path("arguments.json").write_text(json.dumps(args))\n'
            'raise SystemExit(int(os.environ.get("TRIVY_TEST_STATUS", "0")))\n')
        (binary / 'trivy').chmod(0o755)
        self.env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'])

    def scan(self, mode, target, status=0):
        env = dict(self.env, TRIVY_TEST_STATUS=str(status))
        return subprocess.run(['bash', str(ROOT / 'scripts/trivy.sh'), mode, target, 'reports/scan.json'],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=15)

    def arguments(self):
        return json.loads((self.root / 'arguments.json').read_text())

    def test_image_scan_uses_supported_options_and_keeps_security_policy(self):
        target = 'docker.io/test/tero-ui@sha256:' + 'a' * 64
        result = self.scan('image', target)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.arguments()
        self.assertEqual(args[0], 'image')
        self.assertNotIn('--include-dev-deps', args)
        self.assertEqual(args[-1], target)
        self.assertEqual(args[args.index('--severity') + 1], 'HIGH,CRITICAL')
        self.assertIn('--ignore-unfixed=false', args)
        self.assertEqual(args[args.index('--exit-code') + 1], '1')
        self.assertEqual(args[args.index('--scanners') + 1], 'vuln')
        self.assertEqual(args[args.index('--output') + 1], 'reports/scan.json')
        self.assertTrue((self.root / 'reports').is_dir())

    def test_filesystem_scan_includes_development_dependencies_and_preserves_target(self):
        result = self.scan('fs', 'source tree')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--include-dev-deps', self.arguments())
        self.assertEqual(self.arguments()[-1], 'source tree')

    def test_vulnerabilities_and_scanner_errors_block_both_modes(self):
        for mode in ('image', 'fs'):
            for status in (1, 2):
                with self.subTest(mode=mode, status=status):
                    self.assertEqual(self.scan(mode, 'target', status).returncode, status)

    def test_unsupported_mode_never_runs_trivy(self):
        self.assertNotEqual(self.scan('invalid', 'target').returncode, 0)
        self.assertFalse((self.root / 'arguments.json').exists())


if __name__ == '__main__':
    unittest.main()
