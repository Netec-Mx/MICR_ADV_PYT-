"""Temporarily tests transport; never shortens real SLO alert durations."""
import os
import json
import subprocess
import time
import httpx
from common import PROMETHEUS,ALERTMANAGER,check
context=os.getenv('KUBE_CONTEXT','msvc-gateway')
def k(*args):return subprocess.run(['kubectl','--context',context,*args],check=True,capture_output=True,text=True)
try:
    k('apply','-f','observability/demo-alert.yaml')
    with httpx.Client(timeout=10,trust_env=False) as h:
        # A projected ConfigMap can take up to ~2 minutes to update in the pod.
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            h.post(PROMETHEUS+'/-/reload').raise_for_status()
            groups=h.get(PROMETHEUS+'/api/v1/rules',params={'type':'alert'}).json()['data']['groups']
            if any(r['name']=='Lab08PipelineTest' for g in groups for r in g['rules']):break
            time.sleep(5)
        else:raise RuntimeError('Demo rule projection/reload failed')
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            r=h.get(ALERTMANAGER+'/api/v2/alerts');r.raise_for_status()
            if any(a['labels'].get('alertname')=='Lab08PipelineTest' for a in r.json()):break
            time.sleep(3)
        else:raise RuntimeError('Demo alert missing from Alertmanager')
        print('APROBADO: alerta de prueba recibida en Alertmanager.')
finally:
    k('-n','monitoring','patch','configmap','lab08-demo-rules','--type=merge','-p',json.dumps({'data':{'rules.yaml':'groups: []\n'}}))
    # Reload until the temporary rule disappears; restoration failures are errors.
    with httpx.Client(timeout=10,trust_env=False) as h:
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            h.post(PROMETHEUS+'/-/reload').raise_for_status()
            groups=h.get(PROMETHEUS+'/api/v1/rules',params={'type':'alert'}).json()['data']['groups']
            if not any(r['name']=='Lab08PipelineTest' for g in groups for r in g['rules']):break
            time.sleep(5)
        else:raise RuntimeError('Temporary alert cleanup failed')
