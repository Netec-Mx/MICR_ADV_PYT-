import json,time,os
import httpx,jwt,pytest,pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from app.main import create_app
from shared.auth import JWTValidator

@pytest_asyncio.fixture
async def secure():
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()));public.update(kid='test',alg='RS256')
    validator=JWTValidator('http://issuer.test','users-api','http://issuer.test/certs',
        transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'keys':[public]})))
    def token(role='user:read',scope='users.read',aud='users-api',expired=False):
        return jwt.encode({'iss':'http://issuer.test','aud':aud,'sub':'user','typ':'Bearer',
            'iat':int(time.time())-10,'exp':int(time.time())+(-1 if expired else 60),
            'realm_access':{'roles':[role]},'scope':scope},private,algorithm='RS256',headers={'kid':'test'})
    app=create_app(auth=True,jwt_validator=validator)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:yield h,token,app
    await validator.close()

@pytest.mark.asyncio
async def test_public_health_and_private_routes(secure):
    h,token,app=secure
    assert (await h.get('/health')).status_code==200
    for path in ['/api/v1/users','/api/v1/users/1','/api/v1/users/fail/simulate']:
        assert (await h.get(path)).status_code==401
        assert (await h.get(path,headers={'Authorization':'Bearer invalid.jwt.token'})).status_code==401

@pytest.mark.parametrize('change,status',[(dict(role='inventory:read'),403),(dict(scope='inventory.read'),403),
    (dict(aud='order-api'),401),(dict(expired=True),401)])
@pytest.mark.asyncio
async def test_claims_and_permissions(secure,change,status):
    h,token,app=secure
    r=await h.get('/api/v1/users',headers={'Authorization':'Bearer '+token(**change)})
    assert r.status_code==status

@pytest.mark.asyncio
async def test_data_demo_and_static_failure_route_precedence(secure):
    h,token,app=secure;hs={'Authorization':'Bearer '+token()}
    r=await h.get('/api/v1/users',headers=hs)
    assert r.status_code==200 and r.json()['demo'] is True and r.json()['total']==2
    assert (await h.get('/api/v1/users/1',headers=hs)).json()['username']=='admin-user'
    assert (await h.get('/api/v1/users/99',headers=hs)).status_code==404
    for fail,status in [('true',500),('false',200)]:
        r=await h.get('/api/v1/users/fail/simulate',params={'fail':fail},headers=hs)
        assert r.status_code==status and r.headers['X-Lab-Backend']=='users-service'
    assert (await h.get('/api/v1/users/fail/simulate',params={'fail':'invalid'},headers=hs)).status_code==422

@pytest.mark.asyncio
async def test_real_keycloak_users_audience(secure):
    issuer=os.getenv('KEYCLOAK_TEST_ISSUER')
    if not issuer:pytest.skip('Define KEYCLOAK_TEST_ISSUER para Keycloak real')
    h,token,app=secure
    with httpx.Client(timeout=10,trust_env=False) as client:
        response=client.post(issuer+'/protocol/openid-connect/token',data={'grant_type':'client_credentials',
            'client_id':'readonly-client','client_secret':'readonly-secret','scope':'users.read'})
        response.raise_for_status();access=response.json()['access_token']
    validator=JWTValidator(issuer,'users-api',issuer+'/protocol/openid-connect/certs')
    old=app.state.jwt_validator;app.state.jwt_validator=validator
    try:
        r=await h.get('/api/v1/users',headers={'Authorization':'Bearer '+access})
        assert r.status_code==200
        claims=await validator.validate_token(access)
        assert 'user:read' in claims['realm_access']['roles'] and 'order:write' not in claims['realm_access']['roles']
    finally:await validator.close();app.state.jwt_validator=old
