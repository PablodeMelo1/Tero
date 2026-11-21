"""Exercise CI clients against contract fixtures without contacting services."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
        spec.loader.exec_module(module)
    return module


class Response(io.BytesIO):
    def __init__(self, data=None, status=200):
        super().__init__(json.dumps(data).encode())
        self.status = status


@contextlib.contextmanager
def project():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / '.ci').mkdir()
        for name in ('policy.json', 'environments.json'):
            (root / '.ci' / name).write_bytes((ROOT / '.ci' / name).read_bytes())
        previous = Path.cwd()
        os.chdir(root)
        try:
            yield root
        finally:
            os.chdir(previous)


class SmokeTests(unittest.TestCase):
    def opener(self, url, **kwargs):
        path = urlsplit(url).path
        if path.endswith('ci-smoke-missing'):
            raise HTTPError(url, self.checkout_status, 'checkout', None, None)
        if path == '/health':
            return Response(status=self.health_status)
        return Response(self.body)

    def setUp(self):
        self.module = load('smoke')
        self.checkout_status = 404
        self.health_status = 200
        self.body = []
        self.open = patch.object(self.module, 'urlopen', side_effect=self.opener).start()
        self.addCleanup(patch.stopall)

    def test_checks_both_frontends_and_every_backend(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.module.check('https://ui.example', 'https://admin.example')
        urls = [call.args[0] for call in self.open.call_args_list]
        self.assertIn('https://admin.example/health', urls)
        self.assertTrue(any('/api/catalog/products' in url for url in urls))
        self.assertTrue(any('/api/carts/' in url for url in urls))
        self.assertTrue(any('/api/orders' in url for url in urls))

    def test_unhealthy_service_invalid_json_shape_and_wrong_checkout_status_block(self):
        for setting, value in [('health_status', 503), ('body', {'unexpected': True}), ('checkout_status', 500)]:
            with self.subTest(setting=setting):
                previous = getattr(self, setting)
                setattr(self, setting, value)
                with self.assertRaises(AssertionError):
                    self.module.check('https://ui.example', 'https://admin.example')
                setattr(self, setting, previous)

    def test_existing_missing_checkout_is_rejected(self):
        def open_existing(url, **kwargs):
            return Response([])
        with patch.object(self.module, 'urlopen', side_effect=open_existing), self.assertRaisesRegex(AssertionError, '404'):
            self.module.check('https://ui.example', 'https://admin.example')


class PurchaseTests(unittest.TestCase):
    def setUp(self):
        self.module = load('e2e')
        self.product = {'id': 'p1', 'name': 'Product', 'price': 12}
        self.item = {'itemId': 'p1', 'quantity': 2, 'unitPrice': 12}

    def results(self):
        return [[self.product], self.item, {'items': [self.item]},
                {'subtotal': 24, 'total': 39}, {'orderId': 'o1'},
                [{'id': 'o1', 'items': [{'productId': 'p1', 'quantity': 2}]}], None]

    def test_purchase_checks_totals_and_persisted_items_then_deletes_cart(self):
        with patch.object(self.module, 'request', side_effect=self.results()) as request:
            with contextlib.redirect_stdout(io.StringIO()):
                self.module.check('https://ui.example')
        self.assertEqual(request.call_args.args[2], 'DELETE')
        self.assertTrue(request.call_args.args[1].startswith('/api/carts/ci-'))
        update = request.call_args_list[3]
        self.assertEqual(update.args[3]['items'][0]['price'], 12)
        self.assertEqual(update.args[3]['shippingAddress']['email'], 'ci@example.org')

    def test_failed_cart_or_calculation_still_cleans_up(self):
        for index, invalid in [(1, {'wrong': 'item'}), (2, {'items': []}),
                               (3, {'subtotal': 1, 'total': 39}), (3, {'subtotal': 24, 'total': 25})]:
            values = self.results()[:index] + [invalid, None]
            with self.subTest(index=index, invalid=invalid):
                with patch.object(self.module, 'request', side_effect=values) as request:
                    with self.assertRaises(AssertionError):
                        self.module.check('https://ui.example')
                self.assertEqual(request.call_args.args[2], 'DELETE')

    def test_persisted_wrong_product_or_quantity_is_rejected(self):
        for item in ({'productId': 'wrong', 'quantity': 2}, {'productId': 'p1', 'quantity': 1}):
            values = self.results()
            values[5] = [{'id': 'o1', 'items': [item]}]
            with patch.object(self.module, 'request', side_effect=values), self.assertRaises(AssertionError):
                self.module.check('https://ui.example')

    def test_empty_catalog_stops_before_creating_cart(self):
        with patch.object(self.module, 'request', return_value=[]) as request:
            with self.assertRaisesRegex(AssertionError, 'empty'):
                self.module.check('https://ui.example')
        self.assertEqual(request.call_count, 1)

    def test_http_client_sends_json_and_handles_empty_response(self):
        with patch.object(self.module, 'urlopen', return_value=Response({'ok': True})) as opened:
            self.assertEqual(self.module.request('https://ui.example', '/checkout', 'POST', {'quantity': 2}), {'ok': True})
        request = opened.call_args.args[0]
        self.assertEqual(request.method, 'POST')
        self.assertEqual(json.loads(request.data), {'quantity': 2})
        with patch.object(self.module, 'urlopen', return_value=io.BytesIO(b'')):
            self.assertIsNone(self.module.request('https://ui.example', '/cart', 'DELETE'))


class PublisherTests(unittest.TestCase):
    def test_publish_uses_tested_tag_and_verified_digests(self):
        module = load('publish')
        sha = 'a' * 40
        def inspect(arguments, **kwargs):
            image = arguments[3]
            prefix = 'docker.io/' if image.endswith('ui:' + sha) else ''
            return json.dumps([prefix + image.split(':')[0] + '@sha256:' + 'b' * 64])
        with project() as root, patch.dict(os.environ, RELEASE_SHA=sha, DOCKERHUB_USERNAME='test'):
            with patch.object(module.subprocess, 'run') as run, patch.object(module.subprocess, 'check_output', side_effect=inspect):
                module.main()
            manifest = json.loads((root / 'release/manifest.json').read_text())
        self.assertEqual(len(manifest['images']), 6)
        self.assertTrue(all('@sha256:' in image for image in manifest['images'].values()))
        self.assertEqual(len(run.call_args_list), 12)
        self.assertTrue(all(call.args[0][1] in ('tag', 'push') for call in run.call_args_list))

    def test_invalid_identity_blocks_registry_commands(self):
        module = load('publish')
        for sha, namespace in [('bad', 'test'), ('a' * 40, '../escape')]:
            with patch.dict(os.environ, RELEASE_SHA=sha, DOCKERHUB_USERNAME=namespace):
                with patch.object(module.subprocess, 'run') as run, self.assertRaises(ValueError):
                    module.main()
            run.assert_not_called()

    def test_missing_remote_digest_does_not_create_promotion_manifest(self):
        module = load('publish')
        with project() as root, patch.dict(os.environ, RELEASE_SHA='a' * 40, DOCKERHUB_USERNAME='test'):
            with patch.object(module.subprocess, 'run'), patch.object(module.subprocess, 'check_output', return_value='[]'):
                with self.assertRaises(StopIteration):
                    module.main()
            self.assertFalse((root / 'release/manifest.json').exists())


class CoveragePathTests(unittest.TestCase):
    def setUp(self):
        self.module = load('normalize_coverage')

    def test_typescript_normalization_is_idempotent(self):
        with project() as root:
            report = root / 'src/ui/coverage/lcov.info'
            report.parent.mkdir(parents=True)
            report.write_text('TN:\nSF:src/app.ts\nDA:1,1\nend_of_record\n')
            self.module.normalize('ui')
            expected = report.read_text()
            self.module.normalize('ui')
            self.assertEqual(report.read_text(), expected)
            self.assertIn('SF:src/ui/src/app.ts', expected)

    def test_go_normalization_preserves_counts_and_module_prefixes(self):
        for service in ('catalog', 'orders'):
            with project() as root:
                report = root / f'src/{service}/coverage.out'
                report.parent.mkdir(parents=True)
                report.write_text(f'mode: atomic\nretail-store/{service}/main.go:1.1,2.2 1 3\n')
                self.module.normalize(service)
                self.assertIn(f'src/{service}/main.go:1.1,2.2 1 3', report.read_text())

    def test_python_normalization_accepts_bare_prefixed_and_already_normalized_names(self):
        for service, report_name, prefix, names in [
            ('cart', 'src/cart/coverage/coverage.xml', 'src/cart/app/', ['main.py', 'app/main.py', 'src/cart/app/main.py']),
            ('ci', 'coverage/ci-coverage.xml', 'scripts/', ['sonar_gate.py', 'scripts/sonar_gate.py']),
        ]:
            for name in names:
                with self.subTest(service=service, name=name), project() as root:
                    report = root / report_name
                    report.parent.mkdir(parents=True)
                    report.write_text(f'<coverage><sources><source>/runner/old</source></sources><packages><class filename="{name}"/></packages></coverage>')
                    self.module.normalize(service)
                    tree = self.module.ET.parse(report)
                    self.assertEqual(tree.find('./sources/source').text, '.')
                    self.assertEqual(tree.find('.//class').get('filename'), prefix + Path(name).name)

    def test_rejects_unknown_services_and_paths_outside_repository(self):
        with self.assertRaises(ValueError):
            self.module.normalize('../../outside')
        for name in ('../outside.py', '/outside.py'):
            with self.assertRaises(ValueError):
                self.module.source_path(name, Path('scripts'))
        path = self.module.ROOT / 'scripts/sonar_gate.py'
        self.assertEqual(self.module.source_path(str(path), Path('scripts')), 'scripts/sonar_gate.py')


class EnvironmentSetupTests(unittest.TestCase):
    def setUp(self):
        self.module = load('github_environments')

    def test_api_sends_json_as_stdin_instead_of_shell_text(self):
        with patch.object(self.module.subprocess, 'check_output', return_value='{"id": 1}') as call:
            self.assertEqual(self.module.api('repos/owner/test/environments/dev', 'PUT', {'reviewers': []}), {'id': 1})
        self.assertIn('--input', call.call_args.args[0])
        self.assertEqual(json.loads(call.call_args.kwargs['input']), {'reviewers': []})
        self.assertFalse(call.call_args.kwargs['shell'])
        self.assertEqual(call.call_args.kwargs['env']['GH_HOST'], 'github.com')
        self.assertEqual(call.call_args.args[0][-2:], ['--', 'repos/owner/test/environments/dev'])
        with patch.object(self.module.subprocess, 'check_output', return_value=''):
            self.assertIsNone(self.module.api('repos/owner/test/environments/dev', 'PUT'))

    def test_api_rejects_options_urls_traversal_and_unexpected_methods(self):
        invalid = ['--hostname=attacker.example', 'https://attacker.example/users/test',
                   'users/test --jq .token', 'users/../../secret', 'repos/owner/../environments/dev',
                   'repos/owner/repo/environments/staging', 'repos/owner/repo/issues']
        with patch.object(self.module.subprocess, 'check_output') as command:
            for path in invalid:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.module.api(path)
            with self.assertRaises(ValueError):
                self.module.api('users/test', '--hostname=attacker.example')
        command.assert_not_called()

    def test_invalid_repositories_and_reviewers_are_rejected_before_api_calls(self):
        for repository in ('--hostname=attacker.example', 'owner/../../secret', 'owner/.',
                           'https://github.com/owner/repo', 'owner/repo?x=1'):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                self.module.repository_name(repository)
        for reviewer in ('--hostname=attacker.example', '../test', 'test --jq .token', 'a' * 40):
            with project(), patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'):
                with patch.object(sys, 'argv', ['environments', 'setup', '--reviewer=' + reviewer]):
                    with patch.object(self.module, 'api') as api:
                        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                            self.module.main()
                    api.assert_not_called()

    def test_policy_cannot_disable_production_approval_or_change_routes(self):
        policies = [
            {'branch': '*', 'environments': {}},
            {'branch': 'main', 'environments': {'dev': {}, 'test': {}, '../../secret': {}}},
            {'branch': 'main', 'environments': {name: {'require_review': 'true'} for name in ('dev', 'test', 'prod')}},
            {'branch': 'main', 'environments': {name: {'require_review': False} for name in ('dev', 'test', 'prod')}},
        ]
        for policy in policies:
            with project() as root:
                (root / '.ci/environments.json').write_text(json.dumps(policy))
                with self.assertRaises(ValueError):
                    self.module.load_policy()

    def test_invalid_reviewer_ids_cannot_change_environments(self):
        for reviewer in (0, -1, '1', True, None):
            with project(), patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'):
                with patch.object(sys, 'argv', ['environments', 'setup', '--reviewer', 'test']):
                    with patch.object(self.module, 'api', return_value={'id': reviewer}) as api:
                        with self.assertRaises(ValueError):
                            self.module.main()
                    self.assertEqual(api.call_count, 1)

    def test_setup_requires_reviewer_and_only_creates_missing_branch_rules(self):
        for existing in ([], [{'name': 'main', 'type': 'branch'}]):
            def api(path, method='GET', body=None):
                if path.startswith('users/'):
                    return {'id': 1}
                if method == 'GET':
                    return {'branch_policies': existing}
                return {}
            with project(), patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'):
                with patch.object(sys, 'argv', ['environments', 'setup', '--reviewer', 'reviewer']):
                    with patch.object(self.module, 'api', side_effect=api) as calls, contextlib.redirect_stdout(io.StringIO()):
                        self.module.main()
            puts = [c for c in calls.call_args_list if len(c.args) > 1 and c.args[1] == 'PUT']
            self.assertEqual(len(puts), 3)
            self.assertEqual(puts[2].args[2]['reviewers'], [{'type': 'User', 'id': 1}])
            posts = [c for c in calls.call_args_list if len(c.args) > 1 and c.args[1] == 'POST']
            self.assertEqual(len(posts), 0 if existing else 3)

    def test_setup_refuses_unrelated_branch_rules(self):
        with project(), patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'):
            with patch.object(sys, 'argv', ['environments', 'setup', '--reviewer', 'reviewer']):
                with patch.object(self.module, 'api', side_effect=[{'id': 1}, {}, {'branch_policies': [{'name': '*'}]}]):
                    with self.assertRaisesRegex(ValueError, 'existing branch policies'):
                        self.module.main()

    def test_check_uses_actual_environment_protections_and_repository_fallback(self):
        environment = {'deployment_branch_policy': {'custom_branch_policies': True},
                       'protection_rules': [{'type': 'required_reviewers', 'reviewers': [{'id': 1}]}]}
        with project(), patch.dict(os.environ, {'GITHUB_REPOSITORY': ''}):
            with patch.object(sys, 'argv', ['environments', 'check', 'prod']):
                with patch.object(self.module.subprocess, 'check_output', return_value='owner/repo\n'):
                    with patch.object(self.module, 'api', side_effect=[environment, {'branch_policies': [{'name': 'main'}]}]):
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.module.main()

    def test_missing_setup_or_check_arguments_do_not_call_github(self):
        for args in (['setup'], ['check']):
            with project(), patch.dict(os.environ, GITHUB_REPOSITORY='owner/repo'):
                with patch.object(sys, 'argv', ['environments', *args]), patch.object(self.module, 'api') as api:
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        self.module.main()
                api.assert_not_called()


class ReportInputTests(unittest.TestCase):
    def test_manifest_reads_fixed_release_file_and_validates_commit(self):
        module = load('manifest')
        sha = 'a' * 40
        manifest = {'commit': sha, 'images': {
            service: f'docker.io/test/tero-{service}@sha256:' + 'b' * 64 for service in module.SERVICES}}
        with project() as root:
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with patch.object(sys, 'argv', ['manifest.py', sha]), contextlib.redirect_stdout(io.StringIO()) as output:
                module.main()
            self.assertEqual(len(output.getvalue().splitlines()), 6)
            for arguments in (['../secret.json', sha], ['../secret.json'], []):
                with patch.object(sys, 'argv', ['manifest.py', *arguments]), self.assertRaises(ValueError):
                    module.main()

    def test_zap_reads_report_content_and_still_blocks_high_risk_or_missing_evidence(self):
        module = load('zap_gate')
        for report, error in [({'site': [{'alerts': []}]}, None),
                              ({'site': [{'alerts': [{'riskcode': '3'}]}]}, ValueError),
                              ({'site': []}, ValueError), ({}, KeyError)]:
            with project(), patch.object(sys, 'stdin', io.StringIO(json.dumps(report))):
                if error:
                    with self.assertRaises(error):
                        module.main()
                else:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        module.main()
                    self.assertIn('DAST gate passed', output.getvalue())

    def test_sonar_branch_metrics_and_period_variants(self):
        module = load('sonar_gate')
        measures = [{'metric': 'new_lines', 'periods': [{'value': '0'}]}, {'metric': 'unused'}]
        with project() as root, patch.dict(os.environ, SONAR_PROJECT_KEY='test', SONAR_TOKEN='test',
                                          PR_NUMBER='', BRANCH_NAME='feature/test'):
            with patch.object(module, 'urlopen', return_value=Response({'component': {'measures': measures}})) as opened:
                with contextlib.redirect_stdout(io.StringIO()):
                    module.main()
            self.assertIn('branch=feature%2Ftest', opened.call_args.args[0].full_url)
            self.assertNotIn('pullRequest', opened.call_args.args[0].full_url)
            self.assertTrue((root / 'reports/sonar-measures.json').is_file())

    def test_sonar_without_coverable_lines_still_enforces_security_and_duplication(self):
        module = load('sonar_gate')
        policy = json.loads((ROOT / '.ci/policy.json').read_text())['quality']
        metrics = {'new_lines': 2, 'new_lines_to_cover': 0, 'new_bugs': 0,
                   'new_vulnerabilities': 0, 'new_duplicated_lines_density': 0}
        module.enforce([{'metric': key, 'value': str(value)} for key, value in metrics.items()], policy)
        metrics['new_vulnerabilities'] = 1
        with self.assertRaises(AssertionError):
            module.enforce([{'metric': key, 'value': str(value)} for key, value in metrics.items()], policy)


if __name__ == '__main__':
    unittest.main()
