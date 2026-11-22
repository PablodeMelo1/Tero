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


def test_health_and_metrics_remain_available_after_framework_upgrade():
    with TestClient(app) as client:
        assert client.get('/health').json() == {'status': 'UP'}
        metrics = client.get('/metrics')
        assert metrics.status_code == 200
        assert 'http_requests_total' in metrics.text


def test_lifespan_initializes_selected_postgres_provider(monkeypatch):
    from unittest.mock import Mock
    from app.config import settings
    from app import postgres_service

    provider = Mock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(settings, 'cart_persistence_provider', 'postgres')
    monkeypatch.setattr(postgres_service, 'PostgresCartService', factory)
    with TestClient(app) as client:
        factory.assert_called_once_with()
        assert app.state.cart_service is provider
        assert client.get('/health').status_code == 200
