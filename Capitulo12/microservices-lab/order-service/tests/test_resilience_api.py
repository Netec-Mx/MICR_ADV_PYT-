from types import SimpleNamespace
from uuid import uuid4
import httpx,pytest,pytest_asyncio
from app.cqrs_app import create_cqrs_app
from app.clients.inventory_client import StockResponse
from app.schemas.order import OrderCreate
from app.domain.order_aggregate import OrderAggregate
from app.eventstore.models import EventRecord,OutboxRecord,OrderProjection
from test_eventstore_integration import store_pg,count

class StubInventory:
    def __init__(self,quantity=10,unknown=False,missing=False):
        self.quantity=quantity;self.unknown=unknown;self.missing=missing;self.calls=[]
    async def check_stock(self,pid):
        self.calls.append(pid)
        return StockResponse(product_id=pid,available=None if self.unknown else self.quantity>0,
            quantity=None if self.unknown else self.quantity,source='fallback' if self.unknown else 'inventory-service',
            reason='product_not_found' if self.missing else None)
    async def status(self):return {'circuit_breakers':{},'bulkheads':{}}
    async def reset(self):return {'state':'closed'}
    async def close(self):pass

@pytest.mark.parametrize('unknown',[False,True])
@pytest.mark.asyncio
async def test_precheck_preserves_eventstore_api_and_outbox(store_pg,unknown):
    inventory=StubInventory(unknown=unknown)
    app=create_cqrs_app(store_pg,admin_key='test',resilience=True,inventory_client=inventory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        pid=str(uuid4())
        response=await client.post('/api/v1/orders',json={'customer_id':str(uuid4()),'items':[
            {'product_id':pid,'quantity':2,'unit_price':'3.50'}]})
        assert response.status_code==201 and response.json()['status']=='pending'
        assert response.headers['X-Stock-Precheck']==('deferred' if unknown else 'verified')
        assert await count(store_pg,EventRecord)==1 and await count(store_pg,OutboxRecord)==2
        assert (await client.get('/api/v1/orders/'+response.json()['id'])).json()['total']=='7.00'
        assert (await client.post('/admin/rebuild-projections',headers={'X-Admin-Key':'test'})).status_code==200

@pytest.mark.parametrize('missing',[False,True])
@pytest.mark.asyncio
async def test_known_insufficient_stock_writes_no_business_data(store_pg,missing):
    inventory=StubInventory(quantity=0,missing=missing)
    app=create_cqrs_app(store_pg,resilience=True,inventory_client=inventory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/api/v1/orders',json={'customer_id':str(uuid4()),'items':[
            {'product_id':str(uuid4()),'quantity':1,'unit_price':'1.00'}]})
        assert response.status_code==409
        assert response.json()['code']==('PRODUCT_NOT_AVAILABLE' if missing else 'INSUFFICIENT_STOCK')
        for model in [EventRecord,OutboxRecord,OrderProjection]:assert await count(store_pg,model)==0

@pytest.mark.asyncio
async def test_repeated_product_lines_are_summed_before_precheck(store_pg):
    inventory=StubInventory(quantity=3)
    app=create_cqrs_app(store_pg,resilience=True,inventory_client=inventory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        pid=str(uuid4());item={'product_id':pid,'quantity':2,'unit_price':'1.00'}
        response=await client.post('/api/v1/orders',json={'customer_id':str(uuid4()),'items':[item,item]})
        assert response.status_code==409 and len(inventory.calls)==1
        assert await count(store_pg,EventRecord)==0

@pytest.mark.asyncio
async def test_resilience_routes_reset_auth_and_uuid_validation(store_pg):
    app=create_cqrs_app(store_pg,resilience=True,inventory_client=StubInventory(),admin_key='secret')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.get('/api/v1/orders/check-stock/PROD-001')).status_code==422
        assert (await client.get('/api/v1/orders/check-stock/'+str(uuid4()))).status_code==200
        assert (await client.get('/health/circuit-breakers')).status_code==200
        url='/health/circuit-breakers/inventory-service/reset'
        assert (await client.post(url)).status_code==403
        assert (await client.post(url,headers={'X-Admin-Key':'secret'})).status_code==200
        assert (await client.post('/health/circuit-breakers/missing/reset',headers={'X-Admin-Key':'secret'})).status_code==404
        assert (await client.get('/health')).status_code==200
