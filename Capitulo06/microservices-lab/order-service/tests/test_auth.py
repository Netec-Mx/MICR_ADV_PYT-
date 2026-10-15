import asyncio,json,time
from uuid import uuid4
import httpx,jwt,pytest,pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI,Depends
from shared.auth import JWTValidator,InvalidToken,AuthUnavailable,configure_auth,require_order_read,require_order_write
from shared.auth.token_client import ServiceTokenClient,ServiceAuthenticationError

ISSUER='http://issuer.test/realms/lab'
@pytest.fixture
def keys():
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid='key-1',alg='RS256',use='sig')
    return private,public

def token(keys,**overrides):
    claims={'iss':ISSUER,'aud':'order-api','sub':'user','typ':'Bearer',
            'iat':int(time.time())-1,'exp':int(time.time())+60,
            'realm_access':{'roles':['order:read','order:write']},'scope':'orders.read orders.write'}
    claims.update(overrides)
    return jwt.encode(claims,keys[0],algorithm='RS256',headers={'kid':'key-1'})

@pytest_asyncio.fixture
async def validator(keys):
    v=JWTValidator(ISSUER,'order-api','http://trusted.test/jwks',
        transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'keys':[keys[1]]})))
    yield v
    await v.close()

@pytest.mark.asyncio
async def test_valid_rs256_token(validator,keys):
    assert (await validator.validate_token(token(keys)))['sub']=='user'

@pytest.mark.parametrize('claim,value',[('iss','http://evil.test'),('aud','inventory-api'),('exp',1),
    ('nbf',int(time.time())+600),('iat',int(time.time())+600),('typ','ID'),('sub',''),('exp','9999999999')])
@pytest.mark.asyncio
async def test_rejects_wrong_claims_and_real_expiration(validator,keys,claim,value):
    # Signature remains correct; expired case tests exp, not a forged signature.
    with pytest.raises(InvalidToken):await validator.validate_token(token(keys,**{claim:value}))

@pytest.mark.parametrize('missing',['exp','iat','iss','aud','sub'])
@pytest.mark.asyncio
async def test_rejects_missing_required_claim(validator,keys,missing):
    claims=jwt.decode(token(keys),options={'verify_signature':False});del claims[missing]
    value=jwt.encode(claims,keys[0],algorithm='RS256',headers={'kid':'key-1'})
    with pytest.raises(InvalidToken):await validator.validate_token(value)

@pytest.mark.asyncio
async def test_rejects_tampered_signature(validator,keys):
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    claims=jwt.decode(token(keys),options={'verify_signature':False})
    value=jwt.encode(claims,other,algorithm='RS256',headers={'kid':'key-1'})
    with pytest.raises(InvalidToken):await validator.validate_token(value)

@pytest.mark.parametrize('value',['not.jwt','a'*17000,jwt.encode({'exp':1},'s'*32,algorithm='HS256',headers={'kid':'key-1'})])
@pytest.mark.asyncio
async def test_rejects_malformed_size_and_wrong_algorithm(validator,value):
    with pytest.raises(InvalidToken):await validator.validate_token(value)

@pytest.mark.asyncio
async def test_missing_kid_and_critical_header(validator,keys):
    claims=jwt.decode(token(keys),options={'verify_signature':False})
    for headers in [{},{'kid':'key-1','crit':['unknown'],'unknown':True}]:
        with pytest.raises(InvalidToken):await validator.validate_token(jwt.encode(claims,keys[0],algorithm='RS256',headers=headers))

@pytest.mark.asyncio
async def test_jku_is_ignored_and_cold_cache_coalesced(keys):
    calls=[]
    async def handler(request):
        calls.append(str(request.url));await asyncio.sleep(.01)
        return httpx.Response(200,json={'keys':[keys[1]]})
    v=JWTValidator(ISSUER,'order-api','http://trusted.test/jwks',transport=httpx.MockTransport(handler))
    claims=jwt.decode(token(keys),options={'verify_signature':False})
    value=jwt.encode(claims,keys[0],algorithm='RS256',headers={'kid':'key-1','jku':'http://evil.test/jwks'})
    try:
        await asyncio.gather(*[v.validate_token(value) for _ in range(8)])
        assert calls==['http://trusted.test/jwks']
    finally:await v.close()

@pytest.mark.asyncio
async def test_rotation_and_unknown_kid_refresh_rate_limit(keys):
    now=[0];calls=[];published=[keys[1]]
    v=JWTValidator(ISSUER,'order-api','http://trusted.test/jwks',clock=lambda:now[0],
        transport=httpx.MockTransport(lambda request:(calls.append(1) or httpx.Response(200,json={'keys':published}))))
    try:
        await v.validate_token(token(keys))
        claims=jwt.decode(token(keys),options={'verify_signature':False})
        unknown=jwt.encode(claims,keys[0],algorithm='RS256',headers={'kid':'unknown'})
        for _ in range(8):
            with pytest.raises(InvalidToken):await v.validate_token(unknown)
        assert len(calls)==1
        rotated={**keys[1],'kid':'key-2'};published.append(rotated);now[0]=3
        new_token=jwt.encode(claims,keys[0],algorithm='RS256',headers={'kid':'key-2'})
        await v.validate_token(new_token)
        assert len(calls)==2
    finally:await v.close()

@pytest.mark.asyncio
async def test_jwks_outage_does_not_accept_expired_cache(keys):
    now=[0];down=[False]
    def handler(request):return httpx.Response(503) if down[0] else httpx.Response(200,json={'keys':[keys[1]]})
    v=JWTValidator(ISSUER,'order-api','http://trusted.test/jwks',ttl=10,clock=lambda:now[0],transport=httpx.MockTransport(handler))
    try:
        await v.validate_token(token(keys));down[0]=True
        await v.validate_token(token(keys))
        now[0]=11
        with pytest.raises(AuthUnavailable):await v.validate_token(token(keys))
    finally:await v.close()

@pytest_asyncio.fixture
async def auth_api(validator):
    app=FastAPI();configure_auth(app,'order-api',True,validator)
    @app.get('/read',dependencies=[Depends(require_order_read)])
    async def read():return {'ok':True}
    @app.post('/write',dependencies=[Depends(require_order_write)])
    async def write():return {'ok':True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:yield client

@pytest.mark.parametrize('header',[None,'Basic token','Bearer invalid'])
@pytest.mark.asyncio
async def test_authentication_is_401_with_challenge(auth_api,header):
    response=await auth_api.get('/read',headers={'Authorization':header} if header else {})
    assert response.status_code==401 and response.headers['WWW-Authenticate']=='Bearer'

@pytest.mark.parametrize('roles,scope',[([], 'orders.read'),(['order:read'],''),(['order:read'],'orders.write')])
@pytest.mark.asyncio
async def test_role_and_scope_both_required(auth_api,keys,roles,scope):
    response=await auth_api.get('/read',headers={'Authorization':'Bearer '+token(keys,realm_access={'roles':roles},scope=scope)})
    assert response.status_code==403

@pytest.mark.asyncio
async def test_readonly_cannot_write(auth_api,keys):
    value=token(keys,realm_access={'roles':['order:read']},scope='orders.read orders.write')
    assert (await auth_api.get('/read',headers={'Authorization':'Bearer '+value})).status_code==200
    assert (await auth_api.post('/write',headers={'Authorization':'Bearer '+value})).status_code==403

def test_token_cache_expiry_and_compare_invalidation():
    calls=[];now=[0]
    def handler(request):
        calls.append(request.content.decode())
        return httpx.Response(200,json={'access_token':'token-'+str(len(calls)),'token_type':'Bearer','expires_in':10})
    client=ServiceTokenClient('http://issuer/token','orders','secret',transport=httpx.MockTransport(handler),clock=lambda:now[0])
    try:
        first=client.get_token();assert client.get_token()==first and len(calls)==1
        now[0]=9;second=client.get_token();assert second!=first and len(calls)==2
        client.invalidate(first);assert client.get_token()==second
        client.invalidate(second);assert client.get_token()!=second
        assert 'grant_type=client_credentials' in calls[0] and 'scope=inventory.read' in calls[0]
    finally:client.close()

@pytest.mark.parametrize('status',[400,401,403,500,503])
def test_token_failures_are_not_anonymous_fallback(status):
    client=ServiceTokenClient('http://issuer/token','orders','secret',transport=httpx.MockTransport(lambda request:httpx.Response(status)))
    try:
        with pytest.raises(ServiceAuthenticationError):client.get_token()
    finally:client.close()
