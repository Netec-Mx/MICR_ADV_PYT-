from pathlib import Path
import importlib.metadata as m
import sys
root=Path(__file__).resolve().parents[1]
if sys.version_info[:2] != (3,12):
    raise SystemExit("Usa Python 3.12 para reproducir el entorno probado.")
versions={"fastapi":"0.111.0","pydantic":"2.7.1","schemathesis":"3.34.0","pytest":"8.2.1","httpx":"0.27.0","confluent-kafka":"2.4.0","redis":"5.0.4"}
if "--eventstore" in sys.argv:
    versions.update({"pydantic-settings":"2.2.1","SQLAlchemy":"2.0.30","asyncpg":"0.29.0","alembic":"1.13.1"})
for name,version in versions.items():
    actual=m.version(name)
    if actual != version: raise SystemExit(f"{name}: esperado {version}, encontrado {actual}")
    print(name,actual)
import yaml
from openapi_spec_validator import validate
for path in (root/"contracts").glob("*.yaml"):
    validate(yaml.safe_load(path.read_text()))
    print("Contrato válido:",path.name)
print("Preflight de Python y contratos aprobado; verificar Docker Compose antes de clase.")
