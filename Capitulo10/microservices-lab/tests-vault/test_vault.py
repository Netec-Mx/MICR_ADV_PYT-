import asyncio
import time
import threading
import json
import subprocess
import sys
from pathlib import Path
import pytest
import hvac
import requests
import httpx
from fastapi import FastAPI
from shared.auth import configure_auth
from shared.vault.client import VaultManager,VaultUnavailable
from shared.vault.application import install

@pytest.mark.parametrize('service',['order-service','inventory-service','users-service'])
def test_own_read_foreign_read_and_write_denied(manager_factory,service):
    m=manager_factory(service);m.refresh();assert m.snapshot()['admin_key']=='initial-'+service
    for other in ('order-service','inventory-service','users-service'):
        if other==service:continue
        with pytest.raises(hvac.exceptions.Forbidden):m.client.secrets.kv.v2.read_secret_version(other,mount_point='secret',raise_on_deleted_version=True)
    with pytest.raises(hvac.exceptions.Forbidden):m.client.secrets.kv.v2.create_or_update_secret(service,{'admin_key':'bad'},mount_point='secret')
    assert m.client.auth.token.lookup_self()['data']['policies']==[service]

@pytest.mark.parametrize('namespace,name',[('default','users-service'),('microservices','order-service'),('microservices','unknown')])
def test_wrong_service_account_denied(manager_factory,namespace,name):
    m=manager_factory(namespace=namespace,name=name)
    with pytest.raises(VaultUnavailable):m.refresh()
    with pytest.raises(VaultUnavailable):m.snapshot()

def test_renewal_and_reauthentication_are_independent_of_kv_rotation(manager_factory,vault):
    clock=[0.0];m=manager_factory(clock=lambda:clock[0]);m.refresh();assert m.logins==1
    clock[0]=6;m.refresh();assert m.renewals==1 and m.version>0
    vault[0].auth.token.revoke(m.client.token)
    clock[0]=12;m.refresh();assert m.logins==2 and m.snapshot()['admin_key']=='initial-users-service'

def test_projected_jwt_is_reread(manager_factory):
    clock=[0.0];m=manager_factory(clock=lambda:clock[0]);m.refresh()
    m.jwt_file.write_text('expired-and-replaced-with-invalid-jwt');clock[0]=11
    with pytest.raises(VaultUnavailable):m.refresh()
    with pytest.raises(VaultUnavailable):m.snapshot()

def test_permission_revocation_discards_snapshot_immediately(manager_factory,vault):
    m=manager_factory();m.refresh();vault[0].sys.create_or_update_policy(m.role,'path "*" { capabilities = ["deny"] }')
    with pytest.raises(VaultUnavailable):m.refresh()
    with pytest.raises(VaultUnavailable):m.snapshot()

@pytest.mark.parametrize('failure',[requests.ConnectionError('offline'),requests.Timeout('timeout'),hvac.exceptions.InternalServerError('server')])
def test_transient_failure_has_bounded_cache(manager_factory,monkeypatch,failure):
    clock=[0.0];m=manager_factory(clock=lambda:clock[0]);m.refresh()
    def fail(**kwargs):raise failure
    monkeypatch.setattr(m.client.secrets.kv.v2,'read_secret_version',fail)
    clock[0]=.2
    with pytest.raises(VaultUnavailable):m.refresh()
    assert m.snapshot()['admin_key']=='initial-users-service'
    clock[0]=.5
    with pytest.raises(VaultUnavailable):m.snapshot()

@pytest.mark.parametrize('data',[{}, {'admin_key':''}, {'admin_key':42}, {'admin_key':None}])
def test_invalid_rotated_secret_fails_closed(manager_factory,vault,data):
    m=manager_factory();m.refresh();vault[0].secrets.kv.v2.create_or_update_secret(m.path,data,mount_point='secret')
    with pytest.raises(VaultUnavailable):m.refresh()
    with pytest.raises(VaultUnavailable):m.snapshot()

def test_snapshot_is_immutable_and_status_has_no_secret(manager_factory):
    m=manager_factory();m.refresh()
    with pytest.raises(TypeError):m.snapshot()['admin_key']='changed'
    assert 'initial-users-service' not in json.dumps(m.status())
    assert set(m.status())=={'service','version','instance','age_seconds','logins','renewals'}

@pytest.mark.parametrize('poll,age',[(0,10),(10,10),(11,10)])
def test_invalid_poll_rejected(manager_factory,poll,age):
    with pytest.raises(ValueError):manager_factory(poll=poll,max_age=age)

def test_root_environment_is_rejected(monkeypatch):
    monkeypatch.setenv('VAULT_TOKEN','operator-only')
    with pytest.raises(ValueError):VaultManager.from_env()

class Validator:
    async def validate_token(self,token):
        from shared.auth.jwt_validator import InvalidToken
        if token=='bad':raise InvalidToken()
        return {'realm_access':{'roles':['ops:admin'] if token=='admin' else []},'scope':'ops.admin' if token=='admin' else 'users.read'}
    async def close(self):pass

@pytest.mark.asyncio
async def test_real_rotation_changes_admin_authorization_without_restart(manager_factory,vault):
    m=manager_factory(poll=.05,max_age=2);m.refresh();app=FastAPI();configure_auth(app,'users-api',validator=Validator());install(app,m)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
            path='/api/v1/users/config';auth={'Authorization':'Bearer admin'}
            assert (await h.get(path+'/status')).status_code==401
            assert (await h.get(path+'/status',headers={'Authorization':'Bearer reader'})).status_code==403
            assert (await h.get(path+'/status',headers={'Authorization':'Bearer bad'})).status_code==401
            initial=(await h.get(path+'/status',headers=auth)).json()
            assert (await h.post(path+'/refresh',headers={**auth,'X-Admin-Key':'initial-users-service'})).status_code==200
            await asyncio.to_thread(vault[0].secrets.kv.v2.create_or_update_secret,m.path,{'admin_key':'rotated-real-key'},mount_point='secret')
            for _ in range(50):
                state=(await h.get(path+'/status',headers=auth)).json()
                if state.get('version',0)>initial['version']:break
                await asyncio.sleep(.05)
            assert state['version']>initial['version'] and state['instance']==initial['instance']
            assert (await h.post(path+'/refresh',headers={**auth,'X-Admin-Key':'initial-users-service'})).status_code==403
            assert (await h.post(path+'/refresh',headers={**auth,'X-Admin-Key':'rotated-real-key'})).status_code==200
            assert 'rotated-real-key' not in json.dumps(state)

def test_application_requires_jwt(manager_factory):
    m=manager_factory();m.refresh();app=FastAPI();app.state.jwt_validator=None
    with pytest.raises(ValueError):install(app,m)

@pytest.mark.asyncio
async def test_stale_configuration_returns_503(manager_factory):
    clock=[0.0];m=manager_factory(clock=lambda:clock[0]);m.refresh();app=FastAPI();configure_auth(app,'users-api',validator=Validator());install(app,m)
    clock[0]=2
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
        assert (await h.get('/api/v1/users/config/status',headers={'Authorization':'Bearer admin'})).status_code==503

@pytest.mark.asyncio
async def test_snapshot_read_does_not_wait_for_network_lock(manager_factory,monkeypatch):
    m=manager_factory(max_age=2);m.refresh();entered=threading.Event();finish=threading.Event()
    original=m.client.secrets.kv.v2.read_secret_version
    def slow(**kwargs):entered.set();finish.wait(2);return original(**kwargs)
    monkeypatch.setattr(m.client.secrets.kv.v2,'read_secret_version',slow)
    task=asyncio.create_task(asyncio.to_thread(m.refresh))
    await asyncio.to_thread(entered.wait,1)
    before=time.monotonic();assert m.snapshot()['admin_key'];assert time.monotonic()-before<.1
    finish.set();await task

def test_oauth_secret_rotation_invalidates_cached_token():
    from shared.auth.token_client import ServiceTokenClient
    secret=['one'];seen=[]
    def response(request):
        seen.append(request.content.decode());return httpx.Response(200,json={'access_token':'token-'+str(len(seen)),'expires_in':60,'token_type':'Bearer'})
    client=ServiceTokenClient('http://identity/token','svc','one',transport=httpx.MockTransport(response));client.secret_provider=lambda:secret[0]
    try:
        first=client.get_token();assert client.get_token()==first and len(seen)==1
        secret[0]='two';assert client.get_token()!=first and len(seen)==2 and 'client_secret=two' in seen[-1]
    finally:client.close()

def test_audit_report_matches_identity_and_errors(manager_factory,vault):
    m=manager_factory();m.refresh()
    with pytest.raises(hvac.exceptions.Forbidden):m.client.secrets.kv.v2.read_secret_version('order-service',mount_point='secret',raise_on_deleted_version=True)
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/lab07/audit_report.py')],input=(vault[2]/'audit.json').read_text(),capture_output=True,text=True,check=True)
    assert 'users-service | read | secret/data/users-service | allowed' in result.stdout
    assert 'users-service | read | secret/data/order-service | denied-or-error' in result.stdout
    assert 'initial-users-service' not in result.stdout and 'test-root' not in result.stdout
