from pathlib import Path
import pytest
import yaml
import schemathesis
from schemathesis.checks import ALL_CHECKS

def call_checked(self, *, app, checks=ALL_CHECKS):
    response = self.call_asgi(app=app)
    self.validate_response(response, checks=checks)
    return response

schemathesis.experimental.OPEN_API_3_1.enable()
from hypothesis import given, settings, strategies as st
from app.main import create_app

contract = Path(__file__).resolve().parents[2] / "contracts/legacy/order-service.openapi.yaml"
spec = yaml.safe_load(contract.read_text())
schema = schemathesis.from_path(str(contract))
schemathesis.register_string_format("uuid", st.uuids().map(str))
operations = [(path, method.upper()) for path, methods in spec["paths"].items() for method in methods]

@pytest.mark.parametrize("path,method", operations)
@given(data=st.data())
@settings(max_examples=10, deadline=None, derandomize=True)
def test_contract_generated(path, method, data):
    # Generación positiva acotada. Negativos explícitos: test_functional.py.
    case = data.draw(schema[path][method].as_strategy())
    call_checked(case, app=create_app())
