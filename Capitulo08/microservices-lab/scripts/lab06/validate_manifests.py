"""Validate local manifests against pinned official Kubernetes/Traefik schemas.
Arguments: Kubernetes swagger JSON; extracted official chart directory.
No Kubernetes server required. This does not prove a live rollout.
"""
import json,sys
from pathlib import Path
import yaml,jsonschema
ROOT=Path(__file__).resolve().parents[2]
def validate(swagger_path,chart_path):
    swagger=json.loads(Path(swagger_path).read_text());definitions=swagger['definitions']
    # Kubernetes Swagger encodes IntOrString as string + a special format.
    # JSON Schema does not implement that format; preserve its actual API union.
    def adapt(value):
        if isinstance(value,dict):
            if value.get('format')=='int-or-string':value['type']=['integer','string']
            for child in value.values():adapt(child)
        elif isinstance(value,list):
            for child in value:adapt(child)
    adapt(definitions)
    kinds={}
    for name,schema in definitions.items():
        for gvk in schema.get('x-kubernetes-group-version-kind',[]):
            api=(gvk['group']+'/' if gvk['group'] else '')+gvk['version']
            kinds[(api,gvk['kind'])]=name
    crds={}
    for path in (Path(chart_path)/'crds').glob('*.yaml'):
        for crd in yaml.safe_load_all(path.read_text()):
            if not crd:continue
            for version in crd['spec']['versions']:
                crds[(crd['spec']['group']+'/'+version['name'],crd['spec']['names']['kind'])]=version['schema']['openAPIV3Schema']
    seen=[];count=0
    for path in sorted((ROOT/'k8s').rglob('*.yaml')):
        if path.name=='values.yaml':continue
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc:continue
            key=(doc['apiVersion'],doc['kind'])
            if key in crds:
                jsonschema.Draft4Validator(crds[key]).validate(doc)
            else:
                if key not in kinds:raise ValueError(f'Unknown GVK: {key}')
                schema={'$ref':'#/definitions/'+kinds[key],'definitions':definitions}
                jsonschema.Draft4Validator(schema).validate(doc)
            identity=(*key,doc['metadata'].get('namespace',''),doc['metadata']['name'])
            if identity in seen:raise ValueError('Duplicate object: '+str(identity))
            seen.append(identity);count+=1
    print(f'{count} manifests validados contra schemas oficiales.')
if __name__=='__main__':validate(*sys.argv[1:])
