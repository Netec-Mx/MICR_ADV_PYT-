from pathlib import Path
from uuid import uuid4
import schemathesis

def call_checked(self, *, app, checks=None):
    response = self.call(app=app)
    self.validate_response(response, checks=checks)
    return response


schema=schemathesis.openapi.from_path(str(Path(__file__).resolve().parents[2]/"contracts/legacy/inventory-service.openapi.yaml"))

def create_product(app):
    response=call_checked(schema["/api/v1/products"]["POST"].Case(body={"name":"Sensor","sku":"SNS-001","stock_quantity":5}), app=app)
    return response.json()["id"]

def test_reservation_success_contract(app):
    pid=create_product(app)
    response=call_checked(schema["/api/v1/reservations"]["POST"].Case(body={"product_id":pid,"order_id":str(uuid4()),"quantity":3}), app=app)
    assert response.status_code == 201
    assert response.json()["quantity"] == 3

def test_reservation_conflict_contract(app):
    pid=create_product(app)
    response=call_checked(schema["/api/v1/reservations"]["POST"].Case(body={"product_id":pid,"order_id":str(uuid4()),"quantity":6}), app=app)
    assert response.status_code == 409

def test_product_missing_contract(app):
    response=call_checked(schema["/api/v1/reservations"]["POST"].Case(body={"product_id":str(uuid4()),"order_id":str(uuid4()),"quantity":1}), app=app)
    assert response.status_code == 404
