#!/usr/bin/env python3
import sys
from pathlib import Path
import httpx,yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lab06'))
from common import GATEWAY,HOST,token,headers
v=yaml.safe_load((Path(sys.argv[1])/'charts/order-service/values.yaml').read_text())
access=token()
with httpx.Client(base_url=GATEWAY,timeout=15,trust_env=False) as c:
    unauthorized=c.get('/api/v1/orders/release',headers={'Host':HOST});assert unauthorized.status_code==401
    r=c.get('/api/v1/orders/release',headers=headers(access));r.raise_for_status()
    assert r.json()=={'service':'order-service','version':v['appVersion']}
    assert r.headers['X-Lab-Version']==v['appVersion'] and r.headers['X-Lab-Variant']=='v1'
    assert c.get('/api/v1/orders',headers=headers(access)).status_code==200
print('Orders JWT, release identity and CQRS query smoke checks passed')
