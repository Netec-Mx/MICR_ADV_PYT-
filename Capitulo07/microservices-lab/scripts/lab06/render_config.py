"""Generate the realm ConfigMap after running setup_realm.py."""
from pathlib import Path
import yaml
root=Path(__file__).resolve().parents[2]
realm=(root/'infra/keycloak/microservices-lab-realm.json').read_text()
path=root/'k8s/lab06/03-keycloak-realm.yaml'
path.write_text(yaml.safe_dump({'apiVersion':'v1','kind':'ConfigMap',
    'metadata':{'name':'keycloak-realm','namespace':'microservices'},
    'data':{'microservices-lab-realm.json':realm}},sort_keys=False))
print('Realm ConfigMap actualizado:',path)
