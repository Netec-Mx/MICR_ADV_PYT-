import os
import sys
import time
import json
import threading
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
import hvac
import requests
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.vault.client import VaultManager

@pytest.fixture(scope='session')
def vault(tmp_path_factory):
    binary=os.getenv('VAULT_TEST_BINARY')
    if not binary:pytest.skip('Set VAULT_TEST_BINARY for real Vault integration')
    temp=tmp_path_factory.mktemp('vault');key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    class Reviewer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                assert self.path=='/apis/authentication.k8s.io/v1/tokenreviews'
                assert self.headers['Authorization']=='Bearer test-reviewer'
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                claims=jwt.decode(body['spec']['token'],key.public_key(),algorithms=['RS256'],audience='vault')
                namespace=claims['kubernetes.io']['namespace'];name=claims['kubernetes.io']['serviceaccount']['name']
                status={'authenticated':True,'audiences':['vault'],'user':{'username':f'system:serviceaccount:{namespace}:{name}','uid':name+'-uid','groups':['system:serviceaccounts']}}
            except Exception:status={'authenticated':False}
            result=json.dumps({'apiVersion':'authentication.k8s.io/v1','kind':'TokenReview','status':status}).encode()
            self.send_response(201);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(result)
    server=ThreadingHTTPServer(('127.0.0.1',0),Reviewer);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    log=open(temp/'server.log','w');process=subprocess.Popen([binary,'server','-dev','-dev-root-token-id=test-root','-dev-listen-address=127.0.0.1:18200'],stdout=log,stderr=subprocess.STDOUT)
    session=requests.Session();session.trust_env=False
    admin=hvac.Client(url='http://127.0.0.1:18200',token='test-root',session=session,timeout=2)
    try:
        for _ in range(200):
            try:
                if admin.sys.is_initialized():break
            except requests.RequestException:time.sleep(.05)
        else:raise RuntimeError('Vault test startup failed')
        admin.sys.enable_auth_method('kubernetes')
        admin.write('auth/kubernetes/config',kubernetes_host=f'http://127.0.0.1:{server.server_port}',token_reviewer_jwt='test-reviewer',disable_local_ca_jwt=True)
        admin.sys.enable_audit_device('file',options={'file_path':str(temp/'audit.json')})
        yield admin,key,temp
    finally:
        process.terminate();process.wait(timeout=20);log.close();server.shutdown();server.server_close()

@pytest.fixture
def manager_factory(vault,tmp_path):
    admin,key,temp=vault
    root=Path(__file__).resolve().parents[1]
    for service in ('order-service','inventory-service','users-service'):
        admin.sys.create_or_update_policy(service,(root/'vault/policies'/f'{service}.hcl').read_text())
        admin.write('auth/kubernetes/role/'+service,bound_service_account_names=[service],bound_service_account_namespaces=['microservices'],audience='vault',token_policies=[service],token_ttl=10,token_max_ttl=20,token_no_default_policy=True)
        data={'admin_key':'initial-'+service}
        if service=='order-service':data.update(database_url='postgresql+asyncpg://example',service_client_secret='test-secret')
        admin.secrets.kv.v2.create_or_update_secret(service,data,mount_point='secret')
    managers=[]
    def factory(service='users-service',namespace='microservices',name=None,clock=time.monotonic,poll=.05,max_age=.5):
        name=name or service
        claims={'sub':f'system:serviceaccount:{namespace}:{name}','aud':['vault'],'exp':int(time.time())+600,'iat':int(time.time()),'kubernetes.io':{'namespace':namespace,'serviceaccount':{'name':name,'uid':name+'-uid'}}}
        path=tmp_path/(str(len(managers))+'.jwt');path.write_text(jwt.encode(claims,key,algorithm='RS256'))
        session=requests.Session();session.trust_env=False
        client=hvac.Client(url=admin.url,token='',session=session,timeout=2)
        manager=VaultManager(client,service,service,path,clock=clock,poll=poll,max_age=max_age)
        managers.append(manager);return manager
    yield factory
    for manager in managers:
        try:
            if manager.client.token:manager.client.auth.token.revoke_self()
        except hvac.exceptions.VaultError:pass
        manager.client.adapter.session.close()
