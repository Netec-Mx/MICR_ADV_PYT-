import json,time
import httpx,jwt,pytest,pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from app.main import create_app
from shared.auth import JWTValidator

@pytest_asyncio.fixture
async def secure_inventory():
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()));public.update(kid='test',alg='RS256')
    validator=JWTValidator('http://issuer.test','inventory-api','http://issuer.test/certs',
        transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'keys':[public]})))
    def access(roles=('inventory:read','inventory:write'),scope='inventory.read inventory.write',aud='inventory-api',exp=None):
        return jwt.encode({'iss':'http://issuer.test','aud':aud,'sub':'user','typ':'Bearer','iat':int(time.time())-1,
            'exp':exp if exp is not None else int(time.time())+60,'realm_access':{'roles':list(roles)},'scope':scope},
            private,algorithm='RS256',headers={'kid':'test'})
    app=create_app(auth=True,jwt_validator=validator)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:yield client,access
    await validator.close()

@pytest.mark.asyncio
async def test_health_public_business_requires_bearer(secure_inventory):
    client,access=secure_inventory
    assert (await client.get('/health')).status_code==200
    assert (await client.get('/api/v1/products')).status_code==401
    assert (await client.post('/api/v1/products',json={'name':'Test','sku':'TEST','stock_quantity':10})).status_code==401

@pytest.mark.asyncio
async def test_inventory_readonly_and_write_role_scope(secure_inventory):
    client,access=secure_inventory
    read={'Authorization':'Bearer '+access(('inventory:read',),'inventory.read')}
    assert (await client.get('/api/v1/products',headers=read)).status_code==200
    body={'name':'Test','sku':'TEST','stock_quantity':10}
    assert (await client.post('/api/v1/products',headers=read,json=body)).status_code==403
    full={'Authorization':'Bearer '+access()}
    response=await client.post('/api/v1/products',headers=full,json=body)
    assert response.status_code==201
    assert (await client.get('/api/v1/products/'+response.json()['id'],headers=read)).json()['stock_quantity']==10

@pytest.mark.parametrize('aud,exp',[('order-api',None),('inventory-api',1)])
@pytest.mark.asyncio
async def test_wrong_audience_and_expiration_rejected(secure_inventory,aud,exp):
    client,access=secure_inventory
    assert (await client.get('/api/v1/products',headers={'Authorization':'Bearer '+access(aud=aud,exp=exp)})).status_code==401

@pytest.mark.asyncio
async def test_inventory_write_role_without_scope_is_forbidden(secure_inventory):
    client,access=secure_inventory
    response=await client.post('/api/v1/products',headers={'Authorization':'Bearer '+access(scope='inventory.read')},
                             json={'name':'Test','sku':'TEST','stock_quantity':10})
    assert response.status_code==403
