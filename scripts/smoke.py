"""Read-only post-deployment checks, including all backend routes through the UI."""
import json
import sys
from urllib.error import HTTPError
from urllib.request import urlopen


def check(ui, admin):
    for base in (ui, admin):
        with urlopen(base + '/health', timeout=15) as response:
            assert response.status == 200
    for route in ('/api/catalog/products', '/api/carts/ci-smoke/items', '/api/orders'):
        with urlopen(ui + route, timeout=15) as response:
            data = json.load(response)
            assert isinstance(data, list) or data is None, (route, data)
    try:
        urlopen(ui + '/api/checkout/ci-smoke-missing', timeout=15)
    except HTTPError as error:
        assert error.code == 404, error.code
    else:
        raise AssertionError('Missing checkout should return 404')
    print('Smoke tests passed: UI, admin, catalog, carts, orders and checkout')


if __name__ == '__main__':
    check(sys.argv[1].rstrip('/'), sys.argv[2].rstrip('/'))
