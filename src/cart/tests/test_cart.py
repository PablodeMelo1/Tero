from fastapi.testclient import TestClient
from app.main import app
from app.models import Item
from app.service import InMemoryCartService


def test_cart_lifecycle():
    with TestClient(app) as client:
        root = '/carts/ci-customer'
        assert client.get(root).json()['items'] == []
        item = {'itemId': 'p1', 'quantity': 2, 'unitPrice': 10}
        assert client.post(root + '/items', json=item).status_code == 201
        assert client.get(root + '/items/p1').json() == item
        item['quantity'] = 3
        assert client.patch(root + '/items', json=item).status_code == 202
        assert client.get(root + '/items').json() == [item]
        assert client.delete(root + '/items/p1').status_code == 202
        assert client.get(root + '/items/p1').status_code == 404
        assert client.patch(root + '/items', json=item).status_code == 404
        assert client.delete(root).status_code == 202
        assert client.get('/health').status_code == 200


def test_merge_preserves_customer_items_and_removes_session():
    service = InMemoryCartService()
    customer_item = Item(itemId='same', quantity=1, unitPrice=10)
    session_item = Item(itemId='other', quantity=2, unitPrice=20)
    service.add_item('customer', customer_item)
    service.add_item('session', Item(itemId='same', quantity=9, unitPrice=10))
    service.add_item('session', session_item)
    service.merge('customer', 'session')
    assert service.get_items('customer') == [customer_item, session_item]
    assert service.get_items('session') == []
    service.delete('customer')
    assert service.get_items('customer') == []
