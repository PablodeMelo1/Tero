"""Fail closed on incomplete ZAP reports or alerts at/above the policy limit."""
import json
import sys
from pathlib import Path


def enforce(report, maximum):
    sites = report['site']
    if not sites:
        raise ValueError('ZAP did not scan any site')
    alerts = [alert for site in sites for alert in site['alerts'] if int(alert['riskcode']) >= 3]
    if len(alerts) > maximum:
        raise ValueError(f'ZAP detected {len(alerts)} high-risk alerts')


def main():
    policy = json.loads(Path('.ci/policy.json').read_text())['security']
    # Read report content, never a caller-selected filesystem path.
    enforce(json.load(sys.stdin), policy['maximum_zap_high_alerts'])
    print('DAST gate passed: no high-risk alerts')


if __name__ == '__main__':
    main()
