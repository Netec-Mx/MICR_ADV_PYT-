"""Rotate only the three lab admin keys; fail on any unmet assertion."""
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/lab06'))
from common import token,headers,check,GATEWAY
CONTEXT=os.getenv('KUBE_CONTEXT','msvc-gateway')

def k(*args):
    return subprocess.run(['kubectl','--context',CONTEXT,*args],capture_output=True,text=True,check=True).stdout

def vault(*args):
    return k('-n','vault','exec','vault-0','--','env','VAULT_ADDR=http://127.0.0.1:8200','VAULT_TOKEN=lab07-operator-only','vault',*args)

def pods(service):
    items=json.loads(k('-n','microservices','get','pods','-l','app='+service,'-o','json'))['items']
    return sorted((p['metadata']['uid'],sum(c.get('restartCount',0) for c in p['status'].get('containerStatuses',[]))) for p in items)

def main():
    admin=token(admin=True);reader=token()
    with httpx.Client(timeout=10,trust_env=False) as h:
        for service,prefix in [('order-service','orders'),('inventory-service','products'),('users-service','users')]:
            base=GATEWAY+'/api/v1/'+prefix+'/config'
            check(h.get(base+'/status',headers={'Host':headers(admin)['Host']}).status_code==401,'Missing JWT must return 401')
            check(h.get(base+'/status',headers=headers(reader)).status_code==403,'Reader must not access config')
            initial=h.get(base+'/status',headers=headers(admin));initial.raise_for_status();initial=initial.json()
            old=json.loads(vault('kv','get','-format=json','secret/'+service))['data']['data']['admin_key']
            response=h.post(base+'/refresh',headers={**headers(admin),'X-Admin-Key':old});response.raise_for_status()
            before=pods(service);check(len(before)==1,'This exercise expects one replica')
            new='lab07-'+secrets.token_hex(16)
            vault('kv','patch','secret/'+service,'admin_key='+new)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                time.sleep(2)
                response=h.get(base+'/status',headers=headers(admin))
                if response.status_code==429:continue
                response.raise_for_status();current=response.json()
                if current['version']>initial['version']:break
            else:raise RuntimeError('Automatic secret refresh exceeded 30 seconds')
            check(current['instance']==initial['instance'],'Application process restarted')
            check(pods(service)==before,'Pod UID or restart count changed')
            check(h.post(base+'/refresh',headers={**headers(admin),'X-Admin-Key':old}).status_code==403,'Old key still accepted')
            check(h.post(base+'/refresh',headers={**headers(admin),'X-Admin-Key':new}).status_code==200,'New key not accepted')
            print(service+': JWT 401/403, new KV version, old key 403/new key 200, same process and pod')
        # Wait past the 60-second TTL midpoint, checking renewal separately from rotation.
        time.sleep(2)
        for prefix in ('orders','products','users'):
            deadline=time.monotonic()+75
            while time.monotonic()<deadline:
                r=h.get(GATEWAY+'/api/v1/'+prefix+'/config/status',headers=headers(admin))
                if r.status_code==200 and r.json()['renewals']>0:break
                time.sleep(2)
            else:raise RuntimeError('Token renewal not observed')
            print(prefix+': token renewal observed')
    print('All Vault rotation checks passed; admin keys remain rotated in Vault.')

if __name__=='__main__':
    try:main()
    except Exception:
        # No raw subprocess/HTTP errors: their representation may include credentials.
        print('Validation FAILED. Check readiness, scoped JWT, Vault policies and connectivity.',file=sys.stderr)
        raise SystemExit(1) from None
