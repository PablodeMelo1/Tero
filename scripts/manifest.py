"""Validate a release and emit only immutable Compose image references."""
import json
import re
import sys

SERVICES = ('admin', 'catalog', 'cart', 'checkout', 'orders', 'ui')


def validate(data, expected_sha):
    if not re.fullmatch(r'[0-9a-f]{40}', expected_sha) or data.get('commit') != expected_sha:
        raise ValueError('Release does not belong to the expected commit')
    if set(data.get('images', {})) != set(SERVICES):
        raise ValueError('Release must contain exactly the six Tero services')
    for service, image in data['images'].items():
        pattern = rf'docker\.io/[a-z0-9][a-z0-9_-]*/tero-{service}@sha256:[0-9a-f]{{64}}'
        if not isinstance(image, str) or not re.fullmatch(pattern, image):
            raise ValueError(f'Invalid immutable image for {service}')
    return '\n'.join(f'IMAGE_{s.upper()}={data["images"][s]}' for s in SERVICES) + '\n'


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as stream:
        print(validate(json.load(stream), sys.argv[2]), end='')
