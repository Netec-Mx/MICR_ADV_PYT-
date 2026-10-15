from pathlib import Path
from uuid import uuid4
import schemathesis
from schemathesis.checks import ALL_CHECKS

def call_checked(self, *, app, checks=ALL_CHECKS):
    response = self.call_asgi(app=app)
    self.validate_response(response, checks=checks)
    return response

schemathesis.experimental.OPEN_API_3_1.enable()

schema=schemathesis.from_path(str(Path(__file__).resolve().parents[2]/"contracts/inventory-service.openapi.yaml"))

def create_product(app):
    response=call_checked(schema["/api/v1/products"]["POST"].make_case(body={"name":"Sensor","sku":"SNS-001","stock_quantity":5}), app=app)
    return response.json()["id"]

def test_reservation_success_contract(app):
    pid=create_product(app)
    response=call_checked(schema["/api/v1/reservations"]["POST"].make_case(body={"product_id":pid,"order_id":str(uuid4()),"quantity":3}), app=app)
    assert response.status_code == 201
    assert response.json()["quantity"] == 3

def test_reservation_conflict_contract(app):
    pid=create_product(app)
    response=call_checked(schema["/api/v1/reservations"]["POST"].make_case(body={"product_id":pid,"order_id":str(uuid4()),"quantity":6}), app=app)
    assert response.status_code == 409

def test_product_missing_contract(app):
    response=call_checked(schema["/api/v1/reservations"]["POST"].make_case(body={"product_id":str(uuid4()),"order_id":str(uuid4()),"quantity":1}), app=app)
    assert response.status_code == 404
