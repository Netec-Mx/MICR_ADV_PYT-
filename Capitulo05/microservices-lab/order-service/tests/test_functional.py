from uuid import uuid4
import pytest

def body():
    return {"customer_id":str(uuid4()),"items":[{"product_id":str(uuid4()),"quantity":3,"unit_price":"19.99"}]}

def test_create_get_cancel(client):
    r=client.post("/api/v1/orders",json=body())
    assert r.status_code == 201
    data=r.json(); oid=data["id"]
    assert data["total"] == "59.97"
    assert data["created_at"].endswith("Z")
    assert client.get(f"/api/v1/orders/{oid}").status_code == 200
    assert len(client.get("/api/v1/orders").json()) == 1
    assert client.patch(f"/api/v1/orders/{oid}/cancel").json()["status"] == "cancelled"
    assert client.patch(f"/api/v1/orders/{oid}/cancel").status_code == 409

def test_missing(client):
    oid=uuid4()
    assert client.get(f"/api/v1/orders/{oid}").status_code == 404
    assert client.patch(f"/api/v1/orders/{oid}/cancel").status_code == 404

@pytest.mark.parametrize("price", ["0.00",19.99,"19.999","-1.00","1e3","1000000.00"])
def test_invalid_money(client, price):
    value=body(); value["items"][0]["unit_price"]=price
    assert client.post("/api/v1/orders",json=value).status_code == 422

def test_empty_items(client):
    assert client.post("/api/v1/orders",json={"customer_id":str(uuid4()),"items":[]}).status_code == 422
