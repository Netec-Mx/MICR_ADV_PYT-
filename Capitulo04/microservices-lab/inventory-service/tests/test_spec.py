from pathlib import Path
import yaml
from openapi_spec_validator import validate

def test_static_contract_is_valid():
    path = Path(__file__).resolve().parents[2] / "contracts/inventory-service.openapi.yaml"
    validate(yaml.safe_load(path.read_text()))
