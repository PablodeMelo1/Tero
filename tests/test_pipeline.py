import copy
import importlib.util
import json
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
