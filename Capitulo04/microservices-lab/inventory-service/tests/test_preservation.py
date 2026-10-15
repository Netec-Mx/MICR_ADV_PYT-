from uuid import uuid4

def test_rejection_preserves_stock(client):
    product=client.post("/api/v1/products",json={"name":"Sensor","sku":"SNS-001","stock_quantity":5}).json()
    pid=product["id"]
    before=client.get(f"/api/v1/products/{pid}").json()["stock_quantity"]
    response=client.post("/api/v1/reservations",json={"product_id":pid,"order_id":str(uuid4()),"quantity":6})
    assert response.status_code == 409
    after=client.get(f"/api/v1/products/{pid}").json()["stock_quantity"]
    assert after == before == 5
