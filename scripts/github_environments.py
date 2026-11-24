"""Create or verify GitHub deployment protections from the versioned policy.

Setup: python3 scripts/github_environments.py setup --reviewer GITHUB_LOGIN
Check: python3 scripts/github_environments.py check dev|test|prod
Uses gh's authenticated session; never stores or displays credentials.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ENVIRONMENTS = ('dev', 'test', 'prod')
REPOSITORY_PATTERN = r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+'
API_PATTERN = rf'(?:users/[A-Za-z0-9][A-Za-z0-9-]{{0,38}}|repos/{REPOSITORY_PATTERN}/environments/(?:dev|test|prod)(?:/deployment-branch-policies)?)'


def repository_name(value):
    if not re.fullmatch(REPOSITORY_PATTERN, value) or value.split('/')[1] in ('.', '..'):
        raise ValueError('Expected a GitHub owner/repository name')
    return value


def load_policy():
    policy = json.loads(Path('.ci/environments.json').read_text())
    if policy.get('branch') != 'main' or set(policy.get('environments', {})) != set(ENVIRONMENTS):
        raise ValueError('Deployment policy must define main and Dev, Test, Prod')
    for name, config in policy['environments'].items():
        if not isinstance(config, dict) or type(config.get('require_review')) is not bool:
            raise ValueError('require_review must be a boolean')
        if name == 'prod' and not config['require_review']:
            raise ValueError('Production approval cannot be disabled')
    return policy


def api(path, method='GET', body=None):
    # Only this script's fixed GitHub routes and methods may reach the CLI.
    if not re.fullmatch(API_PATTERN, path) or '/./' in path or '/../' in path:
        raise ValueError('Unexpected GitHub API route')
    if method not in ('GET', 'PUT', 'POST'):
        raise ValueError('Unexpected GitHub API method')
    command = ['gh', 'api', '--hostname', 'github.com', '--method', method]
    payload = None
    if body is not None:
        command += ['--input', '-']
        payload = json.dumps(body)
    command += ['--', path]
    result = subprocess.check_output(command, input=payload, text=True, shell=False,
                                     env=dict(os.environ, GH_HOST='github.com'))
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
    if args.mode == 'setup' and (not args.reviewer or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', args.reviewer)):
        parser.error('setup requires --reviewer with a GitHub login')
    if args.mode == 'check' and not args.environment:
        parser.error('check requires an environment')
    policy = load_policy()
    repository = repository_name(os.environ.get('GITHUB_REPOSITORY') or subprocess.check_output(
        ['gh', 'repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner'], text=True,
        shell=False, env=dict(os.environ, GH_HOST='github.com')).strip())
    prefix = f'repos/{repository}/environments'
    if args.mode == 'setup':
        reviewer = api('users/' + args.reviewer)['id']
        if type(reviewer) is not int or reviewer <= 0:
            raise ValueError('GitHub must return a positive numeric reviewer ID')
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
        name = args.environment
        validate(api(prefix + '/' + name), api(prefix + '/' + name + '/deployment-branch-policies'),
                 policy['branch'], policy['environments'][name]['require_review'])
        print('Environment protection verified:', name)


if __name__ == '__main__':
    main()
