from pathlib import Path
import pytest
import yaml
import schemathesis

def call_checked(self, *, app, checks=None):
    response = self.call(app=app)
    self.validate_response(response, checks=checks)
    return response

from hypothesis import given, settings, strategies as st
from app.main import create_app

contract = Path(__file__).resolve().parents[2] / "contracts/legacy/inventory-service.openapi.yaml"
spec = yaml.safe_load(contract.read_text())
schema = schemathesis.openapi.from_path(str(contract))
schemathesis.openapi.format("uuid", st.uuids().map(str))
operations = [(path, method.upper()) for path, methods in spec["paths"].items() for method in methods]

@pytest.mark.parametrize("path,method", operations)
@given(data=st.data())
@settings(max_examples=10, deadline=None, derandomize=True)
def test_contract_generated(path, method, data):
    # Generación positiva acotada. Negativos explícitos: test_functional.py.
    case = data.draw(schema[path][method].as_strategy())
    if isinstance(case.body,dict):
        for key in ['stock_quantity','quantity','reorder_threshold']:
            if isinstance(case.body.get(key),float) and case.body[key].is_integer():
                case.body[key]=int(case.body[key])
    call_checked(case, app=create_app())
