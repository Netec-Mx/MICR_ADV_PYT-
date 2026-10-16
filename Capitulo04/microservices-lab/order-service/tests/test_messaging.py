from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app
from shared.events import OrderCreated

class Publisher:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []
    def publish(self, topic, event):
        if self.fail:
            raise RuntimeError("Kafka falló")
        self.calls.append((topic, event))

def body():
    return {"customer_id": str(uuid4()), "items": [
        {"product_id": str(uuid4()), "quantity": 2, "unit_price": "19.99"},
        {"product_id": str(uuid4()), "quantity": 1, "unit_price": "10.00"}]}

def test_creation_publishes_all_items_and_preserves_response():
    publisher = Publisher()
    with TestClient(create_app(publisher=publisher)) as client:
        response = client.post("/api/v1/orders", json=body())
        assert response.status_code == 201
        assert response.json()["total"] == "49.98"
        topic, event = publisher.calls[0]
        assert topic == "orders.created"
        assert len(event.items) == 2
        assert str(event.order_id) == response.json()["id"]
        assert OrderCreated.model_validate_json(event.to_kafka_value()) == event

def test_failed_publication_returns_503_and_does_not_save_order():
    with TestClient(create_app(publisher=Publisher(fail=True))) as client:
        response = client.post("/api/v1/orders", json=body())
        assert response.status_code == 503
        assert response.json()["code"] == "EVENT_PUBLICATION_FAILED"
        assert client.get("/api/v1/orders").json() == []
