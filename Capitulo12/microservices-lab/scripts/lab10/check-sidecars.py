import json
from common import k,EXPECTED

def main():
    pods=json.loads(k('-n','microservices','get','pods','-l','lab10-mesh=true','-o','json'))['items']
    pods=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
    found={}
    for p in pods:
        labels=p['metadata']['labels'];svc=labels['lab10-service'];variant=labels['version']
        found.setdefault(svc,set()).add(variant)
        spec=p['spec'];names={c['name'] for c in spec['containers']+spec.get('initContainers',[])}
        assert 'istio-proxy' in names,p['metadata']['name']
        assert any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions',[]))
        assert spec['serviceAccountName']==svc and spec['automountServiceAccountToken'] is False
        vault=next(v for v in spec['volumes'] if v['name']=='vault-jwt')
        assert vault['projected']['sources'][0]['serviceAccountToken']['audience']=='vault'
        assert any(v['name']=='istio-token' for v in spec['volumes']), 'Istio projected identity missing'
        print(svc,variant,p['metadata']['name'],'Ready with Vault and Istio identities')
    assert found=={svc:set(vs) for svc,vs in EXPECTED.items()},found
if __name__=='__main__':main()
