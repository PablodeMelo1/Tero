"""Prove that remote JSON content cannot select the report's destination."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sonar_gate', ROOT / 'scripts/sonar_gate.py')
sonar_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sonar_gate)


class SonarReportPathTests(unittest.TestCase):
    def test_remote_filename_and_path_are_only_report_content(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / 'project'
            (project / '.ci').mkdir(parents=True)
            (project / '.ci/policy.json').write_bytes((ROOT / '.ci/policy.json').read_bytes())
            original_cwd = Path.cwd()
            try:
                os.chdir(project)
                for filename in ('../outside.json', str(base / 'absolute.json')):
                    with self.subTest(filename=filename):
                        # Even an API-provided path and metric name cannot change
                        # which file main() opens for writing.
                        data = {'filename': filename, 'path': filename, 'component': {'measures': [
                            {'metric': 'new_lines', 'value': '10'},
                            {'metric': 'new_lines_to_cover', 'value': '10'},
                            {'metric': 'new_coverage', 'value': '85'},
                            {'metric': 'new_duplicated_lines_density', 'value': '0'},
                            {'metric': 'new_bugs', 'value': '0'},
                            {'metric': 'new_vulnerabilities', 'value': '0'},
                            {'metric': filename, 'value': '1'},
                        ]}}
                        response = io.BytesIO(json.dumps(data).encode())
                        env = {'SONAR_PROJECT_KEY': 'unit-test-project', 'SONAR_TOKEN': 'unit-test-token',
                               'PR_NUMBER': '26', 'BRANCH_NAME': 'feature/test'}
                        with patch.dict(os.environ, env), patch.object(sonar_gate, 'urlopen', return_value=response):
                            with contextlib.redirect_stdout(io.StringIO()):
                                sonar_gate.main()
                        report = project / 'reports/sonar-measures.json'
                        self.assertEqual(json.loads(report.read_text()), data)
                        self.assertFalse((base / 'outside.json').exists())
                        self.assertFalse((base / 'absolute.json').exists())
                        self.assertEqual(sorted(path.name for path in report.parent.iterdir()), ['sonar-measures.json'])
            finally:
                os.chdir(original_cwd)


if __name__ == '__main__':
    unittest.main()
