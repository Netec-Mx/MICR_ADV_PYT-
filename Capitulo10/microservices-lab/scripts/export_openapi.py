from pathlib import Path
import json
from openapi_spec_validator import validate
from urllib.request import urlopen
root=Path(__file__).resolve().parents[1]
out=root/"docs/api";out.mkdir(parents=True,exist_ok=True)
for service,port in [("order-service",8001),("inventory-service",8002)]:
    with urlopen(f"http://localhost:{port}/openapi.json",timeout=5) as response:
        schema=json.load(response)
    validate(schema)
    path=out/f"{service}-generated.json"
    path.write_text(json.dumps(schema,indent=2),encoding="utf-8")
    print(path)
print("Exportación derivada guardada. contracts/ permanece independiente.")
