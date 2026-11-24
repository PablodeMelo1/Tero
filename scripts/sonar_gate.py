"""Enforce versioned new-code thresholds in addition to SonarCloud's gate."""
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def enforce(measures, policy):
    values = {}
    for measure in measures:
        value = measure.get('value', measure.get('period', {}).get('value'))
        if value is None and measure.get('periods'):
            value = measure['periods'][0].get('value')
        if value is not None:
            values[measure['metric']] = float(value)
    new_lines = values['new_lines']
    if new_lines == 0:
        return
    if values['new_lines_to_cover'] > 0:
        assert values['new_coverage'] >= policy['minimum_new_coverage'], 'New-code coverage below threshold'
    assert values['new_duplicated_lines_density'] <= policy['maximum_new_duplication'], 'New-code duplication above threshold'
    assert values['new_bugs'] <= policy['maximum_new_bugs'], 'New bugs detected'
    assert values['new_vulnerabilities'] <= policy['maximum_new_vulnerabilities'], 'New vulnerabilities detected'


def main():
    metrics = ['new_lines', 'new_lines_to_cover', 'new_coverage', 'new_duplicated_lines_density', 'new_bugs', 'new_vulnerabilities']
    params = {'component': os.environ['SONAR_PROJECT_KEY'], 'metricKeys': ','.join(metrics)}
    if os.environ.get('PR_NUMBER'):
        params['pullRequest'] = os.environ['PR_NUMBER']
    else:
        params['branch'] = os.environ['BRANCH_NAME']
    token = base64.b64encode((os.environ['SONAR_TOKEN'] + ':').encode()).decode()
    request = Request('https://sonarcloud.io/api/measures/component?' + urlencode(params),
                      headers={'Authorization': 'Basic ' + token})
    with urlopen(request, timeout=30) as response:
        data = json.load(response)
    # Remote JSON is report content only. It never selects a directory or filename.
    Path('reports').mkdir(exist_ok=True)
    Path('reports/sonar-measures.json').write_text(json.dumps(data, indent=2) + '\n')
    policy = json.loads(Path('.ci/policy.json').read_text())['quality']
    enforce(data['component']['measures'], policy)
    print('Versioned SonarCloud quality thresholds passed')


if __name__ == '__main__':
    main()
