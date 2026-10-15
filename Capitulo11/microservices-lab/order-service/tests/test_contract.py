from pathlib import Path
from uuid import uuid4
import schemathesis

def call_checked(self, *, app, checks=None):
    response = self.call(app=app)
    self.validate_response(response, checks=checks)
    return response

schema=schemathesis.openapi.from_path(str(Path(__file__).resolve().parents[2]/"contracts/legacy/order-service.openapi.yaml"))

def test_order_lifecycle_contract(app):
    response=call_checked(schema["/api/v1/orders"]["POST"].Case(body={"customer_id":str(uuid4()),"items":[{"product_id":str(uuid4()),"quantity":3,"unit_price":"19.99"}]}), app=app)
    oid=response.json()["id"]
    assert response.json()["total"] == "59.97"
    call_checked(schema["/api/v1/orders/{order_id}"]["GET"].Case(path_parameters={"order_id":oid}), app=app)
    operation=schema["/api/v1/orders/{order_id}/cancel"]["PATCH"]
    assert call_checked(operation.Case(path_parameters={"order_id":oid}), app=app).status_code == 200
    assert call_checked(operation.Case(path_parameters={"order_id":oid}), app=app).status_code == 409
