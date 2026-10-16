from uuid import uuid4
import pytest

def product(client):
    r = client.post("/api/v1/products", json={"name":"Sensor","sku":"SNS-001","stock_quantity":5})
    assert r.status_code == 201
    return r.json()["id"]

def test_create_and_get_product(client):
    pid = product(client)
    assert client.get(f"/api/v1/products/{pid}").json()["stock_quantity"] == 5
    assert len(client.get("/api/v1/products").json()) == 1

@pytest.mark.parametrize("quantity", [0,-1,"3",True,1.5,1000001])
def test_invalid_quantity(client, quantity):
    pid = product(client)
    r = client.post("/api/v1/reservations", json={"product_id":pid,"order_id":str(uuid4()),"quantity":quantity})
    assert r.status_code == 422
    assert client.get(f"/api/v1/products/{pid}").json()["stock_quantity"] == 5

@pytest.mark.parametrize("changes", [{"product_id":"bad"},{"order_id":"bad"},{"extra":1}])
def test_invalid_fields(client, changes):
    body={"product_id":product(client),"order_id":str(uuid4()),"quantity":1}
    body.update(changes)
    assert client.post("/api/v1/reservations",json=body).status_code == 422

def test_missing_quantity(client):
    assert client.post("/api/v1/reservations",json={"product_id":product(client),"order_id":str(uuid4())}).status_code == 422

def test_http_insufficient_stock(client):
    pid=product(client)
    r=client.post("/api/v1/reservations",json={"product_id":pid,"order_id":str(uuid4()),"quantity":6})
    assert r.status_code == 409
    assert r.json()["code"] == "INSUFFICIENT_STOCK"
    assert client.get(f"/api/v1/products/{pid}").json()["stock_quantity"] == 5

def test_http_missing_product(client):
    r=client.post("/api/v1/reservations",json={"product_id":str(uuid4()),"order_id":str(uuid4()),"quantity":1})
    assert r.status_code == 404
    assert r.json()["code"] == "PRODUCT_NOT_FOUND"
