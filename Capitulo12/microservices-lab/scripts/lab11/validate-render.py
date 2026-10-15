#!/usr/bin/env python3
"""Validate Helm-rendered core resources against the official pinned Kubernetes schema."""
import json,sys,urllib.request
from pathlib import Path
import yaml
from jsonschema import Draft4Validator

def validate(path,schema_path):
    schema_path=Path(schema_path)
    if not schema_path.exists():
        schema_path.parent.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen('https://raw.githubusercontent.com/kubernetes/kubernetes/v1.35.8/api/openapi-spec/swagger.json',timeout=60) as response:
            schema_path.write_bytes(response.read())
    d=json.loads(schema_path.read_text())
    d['definitions']['io.k8s.apimachinery.pkg.util.intstr.IntOrString']={'oneOf':[{'type':'integer'},{'type':'string'}]}
    lookup={}
    for key,spec in d['definitions'].items():
        for g in spec.get('x-kubernetes-group-version-kind',[]):
            api=g['group']+'/'+g['version'] if g['group'] else g['version'];lookup[(api,g['kind'])]=key
    def prune(x):
        if isinstance(x,dict):return {k:prune(v) for k,v in x.items() if v is not None}
        if isinstance(x,list):return [prune(v) for v in x]
        return x
    docs=[o for o in yaml.safe_load_all(Path(path).read_text()) if o]
    assert docs,'Empty manifest'
    for o in docs:
        key=lookup[(o['apiVersion'],o['kind'])]
        Draft4Validator({'$ref':'#/definitions/'+key,'definitions':d['definitions']}).validate(prune(o))
        assert o['metadata']['namespace']=='microservices'
    print(f'{len(docs)} Kubernetes resources valid')
if __name__=='__main__':validate(sys.argv[1],sys.argv[2])
