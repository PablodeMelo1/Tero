"""Publish the exact images tested in CI and assemble the promotion manifest."""
import json
import os
from pathlib import Path
import re
import subprocess
from manifest import SERVICES, validate


def main():
    sha = os.environ['RELEASE_SHA']
    namespace = os.environ['DOCKERHUB_USERNAME']
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', namespace):
        raise ValueError('Invalid commit or Docker Hub namespace')
    images = {}
    for service in SERVICES:
        local = f'tero-{service}:{sha}'
        remote = f'{namespace}/tero-{service}:{sha}'
        subprocess.run(['docker', 'tag', local, remote], check=True)
        subprocess.run(['docker', 'push', remote], check=True)
        digests = json.loads(subprocess.check_output(['docker', 'image', 'inspect', remote, '--format', '{{json .RepoDigests}}'], text=True))
        prefix = f'{namespace}/tero-{service}@sha256:'
        digest = next(d.removeprefix('docker.io/') for d in digests if d.removeprefix('docker.io/').startswith(prefix))
        images[service] = 'docker.io/' + digest
    manifest = {'commit': sha, 'images': images}
    validate(manifest, sha)
    Path('release').mkdir(exist_ok=True)
    Path('release/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
