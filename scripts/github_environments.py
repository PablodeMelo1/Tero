"""Create or verify GitHub deployment protections from the versioned policy.

Setup: python3 scripts/github_environments.py setup --reviewer GITHUB_LOGIN
Check: python3 scripts/github_environments.py check dev|test|prod
Uses gh's authenticated session; never stores or displays credentials.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def api(path, method='GET', body=None):
    command = ['gh', 'api', '--method', method, path]
    payload = None
    if body is not None:
        command += ['--input', '-']
        payload = json.dumps(body)
    result = subprocess.check_output(command, input=payload, text=True)
    return json.loads(result) if result else None


def validate(environment, branch_policy, branch, require_review):
    restrictions = environment.get('deployment_branch_policy') or {}
    if not restrictions.get('custom_branch_policies'):
        raise ValueError('Environment must restrict deployments to selected branches')
    policies = branch_policy['branch_policies']
    if not policies or any(p['name'] != branch or p.get('type', 'branch') != 'branch' for p in policies):
        raise ValueError('Environment must allow only the main branch')
    if require_review:
        reviews = [r for r in environment['protection_rules'] if r['type'] == 'required_reviewers']
        if not reviews or not reviews[0].get('reviewers'):
            raise ValueError('Production requires at least one reviewer')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['setup', 'check'])
    parser.add_argument('environment', nargs='?', choices=['dev', 'test', 'prod'])
    parser.add_argument('--reviewer')
    args = parser.parse_args()
    policy = json.loads(Path('.ci/environments.json').read_text())
    repository = os.environ.get('GITHUB_REPOSITORY') or subprocess.check_output(
        ['gh', 'repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner'], text=True).strip()
    prefix = f'repos/{repository}/environments'
    if args.mode == 'setup':
        if not args.reviewer:
            parser.error('setup requires --reviewer GITHUB_LOGIN')
        reviewer = api('users/' + args.reviewer)['id']
        for name, config in policy['environments'].items():
            body = {'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
                    'prevent_self_review': False,
                    'reviewers': [{'type': 'User', 'id': reviewer}] if config['require_review'] else []}
            api(prefix + '/' + name, 'PUT', body)
            existing = api(prefix + '/' + name + '/deployment-branch-policies')['branch_policies']
            # Keep existing matching rules; refuse unrelated rules instead of deleting them.
            if any(p['name'] != policy['branch'] or p.get('type', 'branch') != 'branch' for p in existing):
                raise ValueError(f'Review existing branch policies for {name} before setup')
            if not existing:
                api(prefix + '/' + name + '/deployment-branch-policies', 'POST', {'name': policy['branch'], 'type': 'branch'})
            print('Configured environment:', name)
    else:
        if not args.environment:
            parser.error('check requires an environment')
        name = args.environment
        validate(api(prefix + '/' + name), api(prefix + '/' + name + '/deployment-branch-policies'),
                 policy['branch'], policy['environments'][name]['require_review'])
        print('Environment protection verified:', name)


if __name__ == '__main__':
    main()
