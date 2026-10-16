"""Real CLI bootstrap + Keycloak + PostgreSQL + Redis + Vault; Kafka tested on cluster."""
import os
import json
import sys
import asyncio
import subprocess
import time
from pathlib import Path
from uuid import uuid4
import asyncpg
import httpx
import pytest

@pytest.mark.asyncio
async def test_three_launchers_preserve_business_and_rotate_keys(manager_factory,vault,tmp_path):
    issuer=os.getenv('KEYCLOAK_TEST_ISSUER');admin_url=os.getenv('POSTGRES_TEST_ADMIN_URL')
    if not issuer or not admin_url:pytest.skip('Requires real Keycloak, PostgreSQL and Redis test endpoints')
    root=Path(__file__).resolve().parents[1];db='lab07_vault_http_test'
    admin_url=admin_url.replace('postgresql+asyncpg://','postgresql://')
    connection=await asyncpg.connect(admin_url)
    processes=[]
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS {db} WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE {db}')
        db_admin=admin_url.rsplit('/',1)[0]+'/'+db
        db_app=db_admin.replace('postgres@','order_app:order_app_lab_pass@').replace('postgresql://','postgresql+asyncpg://')
        env={**os.environ,'PYTHONPATH':str(root)+os.pathsep+os.environ.get('PYTHONPATH',''),'AUTH_ENABLED':'true','AUTH_ISSUER':issuer,'AUTH_JWKS_URL':issuer+'/protocol/openid-connect/certs',
             'AUTH_TOKEN_URL':issuer+'/protocol/openid-connect/token','ORDER_SERVICE_CLIENT_ID':'order-service-client',
             'EVENTSTORE_ENABLED':'true','RESILIENCE_ENABLED':'true','MESSAGING_ENABLED':'false',
             'RESILIENCE_REDIS_URL':os.environ['REDIS_TEST_URL'].rsplit('/',1)[0]+'/1','INVENTORY_BASE_URL':'http://127.0.0.1:19002',
             'EVENTSTORE_ADMIN_DATABASE_URL':db_admin.replace('postgresql://','postgresql+asyncpg://')}
        env.pop('VAULT_TOKEN',None)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=root/'order-service',env=env,check=True,capture_output=True)
        for service,port in [('order-service',19001),('inventory-service',19002),('users-service',19003)]:
            manager=manager_factory(service,poll=.1,max_age=3)
            data={'admin_key':'initial-'+service}
            if service=='order-service':data.update(database_url=db_app,service_client_secret='order-svc-secret-lab')
            vault[0].secrets.kv.v2.create_or_update_secret(service,data,mount_point='secret')
            service_env={**env,'LAB10_VARIANT':{'order-service':'v1','inventory-service':'blue','users-service':'stable'}[service],'APP_VERSION':'10.0.0','VAULT_ADDR':vault[0].url,'VAULT_ROLE':service,'VAULT_SECRET_PATH':service,'VAULT_JWT_FILE':str(manager.jwt_file),'VAULT_POLL_SECONDS':'.1','VAULT_MAX_AGE_SECONDS':'3'}
            log=open(tmp_path/(service+'.log'),'w')
            process=subprocess.Popen([sys.executable,'-m','shared.vault.launcher','--port',str(port)],cwd=root/service,env=service_env,stdout=log,stderr=subprocess.STDOUT)
            processes.append((process,log))
        async with httpx.AsyncClient(timeout=5,trust_env=False) as h:
            for port in (19001,19002,19003):
                for _ in range(100):
                    try:
                        if (await h.get(f'http://127.0.0.1:{port}/health')).status_code==200:break
                    except httpx.HTTPError:pass
                    await asyncio.sleep(.1)
                else:raise RuntimeError(f'Launcher on {port} failed; inspect test log')
            token_response=await h.post(issuer+'/protocol/openid-connect/token',data={'grant_type':'client_credentials','client_id':'lab-admin-client','client_secret':'lab-admin-secret','scope':'orders.read orders.write inventory.read inventory.write ops.admin users.read'})
            token_response.raise_for_status();headers={'Authorization':'Bearer '+token_response.json()['access_token']}
            product=await h.post('http://127.0.0.1:19002/api/v1/products',headers=headers,json={'name':'Vault integration','sku':uuid4().hex[:8].upper(),'stock_quantity':20})
            assert product.status_code==201
            order=await h.post('http://127.0.0.1:19001/api/v1/orders',headers={**headers,'traceparent':'00-'+os.getenv('LAB08_TRACE_ID',uuid4().hex)+'-00f067aa0ba902b7-01'},json={'customer_id':str(uuid4()),'items':[{'product_id':product.json()['id'],'quantity':2,'unit_price':'10.00'}]})
            assert order.headers['X-Lab-Variant']=='v1' and order.headers['X-Lab-Version']=='10.0.0'
            assert order.status_code==201 and order.headers['X-Stock-Precheck']=='verified' and order.json()['total']=='20.00'
            users=await h.get('http://127.0.0.1:19003/api/v1/users',headers=headers)
            assert users.status_code==200 and users.headers['X-Lab-Variant']=='stable'
            for service,port,prefix in [('order-service',19001,'orders'),('inventory-service',19002,'products'),('users-service',19003,'users')]:
                base=f'http://127.0.0.1:{port}/api/v1/{prefix}/config'
                initial=(await h.get(base+'/status',headers=headers)).json()
                assert (await h.get(base+'/status')).status_code==401
                values=vault[0].secrets.kv.v2.read_secret_version(service,mount_point='secret',raise_on_deleted_version=True)['data']['data'];values['admin_key']='rotated-'+service
                vault[0].secrets.kv.v2.create_or_update_secret(service,values,mount_point='secret')
                for _ in range(60):
                    state=(await h.get(base+'/status',headers=headers)).json()
                    if state.get('version',0)>initial['version']:break
                    await asyncio.sleep(.1)
                assert state['version']>initial['version'] and state['instance']==initial['instance']
                assert (await h.post(base+'/refresh',headers={**headers,'X-Admin-Key':'initial-'+service})).status_code==403
                assert (await h.post(base+'/refresh',headers={**headers,'X-Admin-Key':'rotated-'+service})).status_code==200
            assert (await h.post('http://127.0.0.1:19001/admin/rebuild-projections',headers={**headers,'X-Admin-Key':'initial-order-service'})).status_code==403
            assert (await h.post('http://127.0.0.1:19001/admin/rebuild-projections',headers={**headers,'X-Admin-Key':'rotated-order-service'})).status_code==200
        if os.getenv('LAB08_TEST_PROM_WAIT')=='true':
            async with httpx.AsyncClient(timeout=5,trust_env=False) as h:
                for _ in range(30):
                    d=(await h.get('http://127.0.0.1:19090/api/v1/query',params={'query':'lab:http_request_rate:5m'})).json()
                    if d.get('data',{}).get('result'):break
                    await asyncio.sleep(.5)
                else:
                    targets=(await h.get('http://127.0.0.1:19090/api/v1/targets')).json()
                    (tmp_path/'prom-targets.json').write_text(json.dumps(targets))
                    raise AssertionError('No RED recording samples; inspect prom-targets.json')
    finally:
        for process,log in processes:process.terminate()
        for process,log in processes:process.wait(timeout=20);log.close()
        await connection.execute(f'DROP DATABASE IF EXISTS {db} WITH (FORCE)');await connection.close()
