"""Verify each release, Helm values, Ready pods, image digest and runtime UID/version."""
import argparse,json,os,subprocess
import yaml
from pathlib import Path
from report import SERVICES
CONTEXT=os.getenv('KUBE_CONTEXT','msvc-gateway')
def run(*args):return subprocess.check_output(args,text=True)
def kube(*args):return run('kubectl','--context',CONTEXT,'-n','microservices',*args)
def verify(svc,version):
    values=json.loads(run('helm','--kube-context',CONTEXT,'get','values',svc,'-n','microservices','--all','-o','json'))
    digest=values['image']['digest'];image=values['image']['repository']+'@'+digest
    expected=yaml.safe_load((Path('reports/lab09')/version/f'{svc}-image.yaml').read_text())
    assert values['appVersion']==version and digest==expected['image']['digest']
    status=json.loads(run('helm','--kube-context',CONTEXT,'status',svc,'-n','microservices','-o','json'))
    assert status['info']['status']=='deployed'
    deployment=json.loads(kube('get','deployment',svc,'-o','json'))
    assert deployment['spec']['template']['spec']['containers'][0]['image']==image
    assert deployment['status'].get('observedGeneration',0)>=deployment['metadata']['generation']
    pods=json.loads(kube('get','pods','-l','app='+svc,'-o','json'))['items']
    active=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
    assert active and len(active)==values['replicaCount'],f'{svc}: rollout incomplete'
    for pod in active:
        assert any(c['type']=='Ready' and c['status']=='True' for c in pod['status'].get('conditions',[]))
        assert pod['spec']['containers'][0]['image']==image
        c=pod['status']['containerStatuses'][0];assert c['ready'] and c.get('imageID'),c
        runtime=json.loads(kube('exec',pod['metadata']['name'],'--','python','-c',
            'import os,json; print(json.dumps({"uid":os.getuid(),"version":os.environ["APP_VERSION"]}))'))
        assert runtime=={'uid':10001,'version':version},runtime
    for kind in ('deployment','service','serviceaccount'):
        checkpoint=Path('reports/lab09')/version/f'{kind}-{svc}-before.json'
        if checkpoint.exists():
            before=json.loads(checkpoint.read_text());current=json.loads(kube('get',kind,svc,'-o','json'))
            assert before['metadata']['uid']==current['metadata']['uid'],f'{kind}/{svc}: identity replaced'
            if kind=='service':assert before['spec']['clusterIP']==current['spec']['clusterIP']
    print(f'{svc}: deployed, Ready, exact image reference {digest}, UID 10001, APP_VERSION {version}')
    return {'service':svc,'version':version,'digest':digest,'pods':[p['metadata']['name'] for p in active]}
def main():
    p=argparse.ArgumentParser();p.add_argument('--version',required=True);p.add_argument('--service',choices=SERVICES);a=p.parse_args()
    rows=[verify(s,a.version) for s in ([a.service] if a.service else SERVICES)]
    dest=Path('reports/lab09')/a.version;dest.mkdir(parents=True,exist_ok=True)
    (dest/'verified-releases.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':main()
