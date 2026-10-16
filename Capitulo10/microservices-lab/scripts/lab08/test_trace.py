import json
import time
from uuid import uuid4
from pathlib import Path
import httpx
from common import token,headers,GATEWAY,JAEGER,check

def main():
    access=token(admin=True);tid=uuid4().hex
    with httpx.Client(timeout=15,trust_env=False) as h:
        product=h.post(GATEWAY+'/api/v1/products',headers=headers(access),json={'name':'OTel Lab08','sku':'OT-'+uuid4().hex[:8].upper(),'stock_quantity':20})
        product.raise_for_status()
        response=h.post(GATEWAY+'/api/v1/orders',headers={**headers(access),'traceparent':f'00-{tid}-00f067aa0ba902b7-01'},json={'customer_id':str(uuid4()),'items':[{'product_id':product.json()['id'],'quantity':2,'unit_price':'10.00'}]})
        check(response.status_code==201,'Expected persisted order 201')
        check(response.headers.get('X-Stock-Precheck')=='verified','Inventory call was not verified')
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            r=h.get(JAEGER+'/api/traces/'+tid)
            if r.status_code==200 and r.json().get('data'):break
            time.sleep(1)
        else:raise RuntimeError('Exact trace missing from Jaeger')
        t=r.json()['data'][0];spans=t['spans'];processes=t['processes']
        check({'order-service','inventory-service'} <= {p['serviceName'] for p in processes.values()},'Missing service in distributed trace')
        check({'inventory.check','orders.persist'} <= {s['operationName'] for s in spans},'Missing business spans')
        clients={s['spanID'] for s in spans if processes[s['processID']]['serviceName']=='order-service' and any(tag['key']=='span.kind' and tag['value']=='client' for tag in s.get('tags',[]))}
        check(any(processes[s['processID']]['serviceName']=='inventory-service' and any(ref.get('spanID') in clients for ref in s.get('references',[])) for s in spans),'Missing HTTP client/server parent relation')
    Path('lab08-trace-id.txt').write_text(tid+'\n')
    print('APROBADO: traza '+tid+' con Orders, Inventory, spans de negocio y relación cliente/servidor.')

if __name__=='__main__':main()
