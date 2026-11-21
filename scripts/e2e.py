"""A real purchase against a disposable CI stack or the Test environment."""
import json
import sys
import uuid
from urllib.request import Request, urlopen


def request(base, path, method='GET', payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=body, method=method, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=20) as response:
        data = response.read()
        return json.loads(data) if data else None


def check(base):
    customer = 'ci-' + uuid.uuid4().hex
    products = request(base, '/api/catalog/products')
    assert products, 'Catalog is empty'
    product = products[0]
    cart = f'/api/carts/{customer}'
    checkout = f'/api/checkout/{customer}'
    try:
        item = {'itemId': product['id'], 'quantity': 2, 'unitPrice': product['price']}
        assert request(base, cart + '/items', 'POST', item) == item
        assert request(base, cart)['items'] == [item]
        payload = {
            'items': [{'id': product['id'], 'name': product['name'], 'quantity': 2, 'price': product['price']}],
            'shippingAddress': {'firstName': 'CI', 'lastName': 'Test', 'email': 'ci@example.org',
                                'address1': 'Test 1', 'city': 'Montevideo', 'state': 'MO', 'zip': '11000'},
            'deliveryOptionToken': 'priority-mail',
        }
        calculated = request(base, checkout + '/update', 'POST', payload)
        assert calculated['subtotal'] == product['price'] * 2
        assert calculated['total'] == calculated['subtotal'] + 15
        submitted = request(base, checkout + '/submit', 'POST', {})
        orders = request(base, '/api/orders')
        order = next(order for order in orders if order['id'] == submitted['orderId'])
        assert order['items'][0]['productId'] == product['id']
        assert order['items'][0]['quantity'] == 2
        print('E2E passed: catalog → cart → checkout → persisted order')
    finally:
        request(base, cart, 'DELETE')


if __name__ == '__main__':
    check(sys.argv[1].rstrip('/'))
