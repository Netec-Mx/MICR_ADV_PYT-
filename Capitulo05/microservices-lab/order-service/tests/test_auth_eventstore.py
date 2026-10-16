from uuid import uuid4
import httpx,pytest
from shared.auth.token_client import ServiceAuthenticationError
from app.cqrs_app import create_cqrs_app
from app.eventstore.models import EventRecord,OutboxRecord
from app.clients.inventory_client import StockResponse
from test_eventstore_integration import store_pg,count
from test_auth import keys,validator,token

class BrokenCredentials:
    async def check_stock(self,pid):raise ServiceAuthenticationError('bad credentials')
    async def close(self):pass

@pytest.mark.asyncio
async def test_authenticated_cqrs_read_write_and_unauthorized_atomicity(store_pg,validator,keys):
    app=create_cqrs_app(store_pg,auth=True,jwt_validator=validator)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        body={'customer_id':str(uuid4()),'items':[{'product_id':str(uuid4()),'quantity':1,'unit_price':'2.00'}]}
        read=token(keys,realm_access={'roles':['order:read']},scope='orders.read')
        assert (await client.get('/api/v1/orders')).status_code==401
        assert (await client.post('/api/v1/orders',json=body,headers={'Authorization':'Bearer '+read})).status_code==403
        assert await count(store_pg,EventRecord)==0
        response=await client.post('/api/v1/orders',json=body,headers={'Authorization':'Bearer '+token(keys)})
        assert response.status_code==201 and response.json()['status']=='pending'
        assert await count(store_pg,EventRecord)==1 and await count(store_pg,OutboxRecord)==2
        assert (await client.get('/api/v1/orders',headers={'Authorization':'Bearer '+read})).status_code==200
        assert (await client.post('/admin/rebuild-projections',headers={'Authorization':'Bearer '+read,'X-Admin-Key':'lab-admin-key'})).status_code==403

@pytest.mark.asyncio
async def test_service_auth_failure_blocks_write_instead_of_deferring(store_pg,validator,keys):
    app=create_cqrs_app(store_pg,auth=True,jwt_validator=validator,resilience=True,inventory_client=BrokenCredentials())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        body={'customer_id':str(uuid4()),'items':[{'product_id':str(uuid4()),'quantity':1,'unit_price':'2.00'}]}
        response=await client.post('/api/v1/orders',json=body,headers={'Authorization':'Bearer '+token(keys)})
        assert response.status_code==503 and response.json()['code']=='SERVICE_AUTHENTICATION_FAILED'
        assert await count(store_pg,EventRecord)==0 and await count(store_pg,OutboxRecord)==0
