from pathlib import Path
from uuid import uuid4
import schemathesis
from schemathesis.checks import ALL_CHECKS

def call_checked(self, *, app, checks=ALL_CHECKS):
    response = self.call_asgi(app=app)
    self.validate_response(response, checks=checks)
    return response

schemathesis.experimental.OPEN_API_3_1.enable()
schema=schemathesis.from_path(str(Path(__file__).resolve().parents[2]/"contracts/legacy/order-service.openapi.yaml"))

def test_order_lifecycle_contract(app):
    response=call_checked(schema["/api/v1/orders"]["POST"].make_case(body={"customer_id":str(uuid4()),"items":[{"product_id":str(uuid4()),"quantity":3,"unit_price":"19.99"}]}), app=app)
    oid=response.json()["id"]
    assert response.json()["total"] == "59.97"
    call_checked(schema["/api/v1/orders/{order_id}"]["GET"].make_case(path_parameters={"order_id":oid}), app=app)
    operation=schema["/api/v1/orders/{order_id}/cancel"]["PATCH"]
    assert call_checked(operation.make_case(path_parameters={"order_id":oid}), app=app).status_code == 200
    assert call_checked(operation.make_case(path_parameters={"order_id":oid}), app=app).status_code == 409
