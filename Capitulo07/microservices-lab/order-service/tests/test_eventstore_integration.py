import asyncio,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError,IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from app.eventstore.store import EventStore,VersionConflict
from app.eventstore.models import EventRecord,OrderProjection,SnapshotOrder,OutboxRecord
from app.eventstore.projections import ProjectionEngine
from app.eventstore.outbox import OutboxRelay
from app.domain.order_aggregate import OrderAggregate
from app.domain.events import OrderItemAdded
from app.schemas.order import OrderCreate,OrderItemCreate
from app.cqrs_app import create_cqrs_app
from app.commands.order_commands import OrderCommands
from app.queries.order_queries import OrderQueries
from shared.events import OrderCreated as IntegrationOrderCreated

@pytest_asyncio.fixture
async def store_pg():
    admin=os.getenv('POSTGRES_TEST_ADMIN_URL')
    if not admin:pytest.skip('Define POSTGRES_TEST_ADMIN_URL para probar PostgreSQL real')
    name='lab03_test_'+uuid4().hex
    connection=await asyncpg.connect(admin.replace('postgresql+asyncpg://','postgresql://'))
    await connection.execute(f'CREATE DATABASE {name}')
    admin_url=make_url(admin).set(database=name).render_as_string(hide_password=False)
    app_url=make_url(admin_url).set(username='order_app',password='order_app_lab_pass').render_as_string(hide_password=False)
    root=Path(__file__).resolve().parents[1]
    result=await asyncio.to_thread(subprocess.run,[sys.executable,'-m','alembic','-c','alembic.ini','upgrade','head'],
        cwd=root,env={**os.environ,'EVENTSTORE_ADMIN_DATABASE_URL':admin_url},capture_output=True,text=True)
    if result.returncode:
        await connection.execute(f'DROP DATABASE {name} WITH (FORCE)');await connection.close()
        raise RuntimeError(result.stdout+result.stderr)
    store=EventStore(app_url);store.test_admin_url=admin_url
    try:yield store
    finally:
        await store.engine.dispose()
        await connection.execute(f'DROP DATABASE {name} WITH (FORCE)')
        await connection.close()

@pytest_asyncio.fixture
async def client_pg(store_pg):
    app=create_cqrs_app(store_pg,admin_key='test-admin')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        yield client

def payload(price='0.10'):
    return OrderCreate(customer_id=uuid4(),items=[OrderItemCreate(product_id=uuid4(),quantity=1,unit_price=price)])

async def create(store):
    event=OrderAggregate.creation(payload());aggregate=await store.append_events(event.aggregate_id,[event],0)
    return event,aggregate

async def count(store,model):
    async with store.sessions() as session:return await session.scalar(select(func.count()).select_from(model))

@pytest.mark.asyncio
async def test_migration_chain_role_and_metadata(store_pg):
    event,aggregate=await create(store_pg)
    async with store_pg.sessions() as session:
        assert await session.scalar(text('SELECT current_user'))=='order_app'
        record=await session.scalar(select(EventRecord))
        assert record.aggregate_version==1 and record.event_id==event.event_id
        assert record.metadata_['correlation_id']==str(event.correlation_id)
        assert record.payload['items'][0]['unit_price']=='0.10'
    engine=create_async_engine(store_pg.test_admin_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text('SELECT version_num FROM alembic_version'))=='002_append_only'
    finally:await engine.dispose()

@pytest.mark.parametrize('statement',['UPDATE events SET event_type=event_type','DELETE FROM events','TRUNCATE events'])
@pytest.mark.asyncio
async def test_admin_trigger_rejects_mutation(store_pg,statement):
    await create(store_pg)
    engine=create_async_engine(store_pg.test_admin_url)
    try:
        with pytest.raises(DBAPIError,match='append-only'):
            async with engine.begin() as connection:await connection.execute(text(statement))
        assert await count(store_pg,EventRecord)==1
    finally:await engine.dispose()

@pytest.mark.parametrize('statement',['UPDATE events SET event_type=event_type','DELETE FROM events','TRUNCATE events'])
@pytest.mark.asyncio
async def test_runtime_role_has_no_mutation_privilege(store_pg,statement):
    await create(store_pg)
    with pytest.raises(DBAPIError,match='permission denied'):
        async with store_pg.sessions() as session,session.begin():await session.execute(text(statement))

@pytest.mark.asyncio
async def test_projection_failure_rolls_back_event_and_outbox(store_pg,monkeypatch):
    async def fail(*args):raise RuntimeError('Projection failed')
    monkeypatch.setattr(ProjectionEngine,'apply',staticmethod(fail))
    event=OrderAggregate.creation(payload())
    with pytest.raises(RuntimeError):await store_pg.append_events(event.aggregate_id,[event],0)
    for model in [EventRecord,OrderProjection,OutboxRecord]:assert await count(store_pg,model)==0

@pytest.mark.asyncio
async def test_stale_version_and_concurrent_append_conflict(store_pg):
    event,aggregate=await create(store_pg)
    first=aggregate.change_status('confirmed');second=aggregate.change_status('confirmed')
    results=await asyncio.gather(store_pg.append_events(event.aggregate_id,[first],1),
        store_pg.append_events(event.aggregate_id,[second],1),return_exceptions=True)
    assert sum(isinstance(r,VersionConflict) for r in results)==1
    assert await count(store_pg,EventRecord)==2
    with pytest.raises(VersionConflict):await store_pg.append_events(event.aggregate_id,[second],0)

@pytest.mark.asyncio
async def test_duplicate_event_id_rolls_back(store_pg):
    event,aggregate=await create(store_pg)
    duplicate=OrderItemAdded(**aggregate.common(),event_id=event.event_id,item=payload().items[0])
    with pytest.raises(IntegrityError):await store_pg.append_events(event.aggregate_id,[duplicate],1)
    assert await count(store_pg,EventRecord)==1
    assert (await OrderQueries(store_pg.sessions).get(event.aggregate_id))[0].total=='0.10'

@pytest.mark.asyncio
async def test_snapshot_10_and_tail_11_match_full_replay(store_pg):
    event,aggregate=await create(store_pg)
    for _ in range(10):
        item_event=aggregate.add_item(payload().items[0])
        aggregate=await store_pg.append_events(event.aggregate_id,[item_event],aggregate.version)
    async with store_pg.sessions() as session:
        snapshot=await session.get(SnapshotOrder,event.aggregate_id)
        assert snapshot.aggregate_version==10
        assert len(snapshot.state['order']['items'])==10
    partial=await store_pg.load(event.aggregate_id);full=await store_pg.load(event.aggregate_id,False)
    assert partial.version==11 and partial.snapshot()==full.snapshot()
    assert partial.order.total==__import__('decimal').Decimal('1.10')

@pytest.mark.asyncio
async def test_batch_crossing_snapshot_boundary(store_pg):
    event,aggregate=await create(store_pg)
    events=[aggregate.add_item(payload().items[0]) for _ in range(11)]
    result=await store_pg.append_events(event.aggregate_id,events,1)
    assert result.version==12
    async with store_pg.sessions() as session:
        snapshot=await session.get(SnapshotOrder,event.aggregate_id)
        assert snapshot.aggregate_version==10 and len(snapshot.state['order']['items'])==10
    assert (await store_pg.load(event.aggregate_id)).snapshot()==(await store_pg.load(event.aggregate_id,False)).snapshot()

@pytest.mark.asyncio
async def test_rebuild_restores_projection_without_new_outbox(store_pg):
    event,aggregate=await create(store_pg)
    await store_pg.append_events(event.aggregate_id,[aggregate.cancel('test')],1)
    before=(await OrderQueries(store_pg.sessions).get(event.aggregate_id))[0].model_dump(mode='json')
    queued=await count(store_pg,OutboxRecord)
    async with store_pg.sessions() as session,session.begin():
        row=await session.get(OrderProjection,event.aggregate_id);row.total_amount=999
    assert await ProjectionEngine(store_pg.sessions).rebuild_all()==2
    assert (await OrderQueries(store_pg.sessions).get(event.aggregate_id))[0].model_dump(mode='json')==before
    assert await count(store_pg,OutboxRecord)==queued and await count(store_pg,EventRecord)==2

@pytest.mark.asyncio
async def test_rebuild_failure_keeps_previous_projection(store_pg):
    event,aggregate=await create(store_pg)
    async with store_pg.sessions() as session,session.begin():
        session.add(EventRecord(event_id=uuid4(),event_type='FutureEvent',aggregate_id=event.aggregate_id,
            aggregate_type='Order',aggregate_version=2,occurred_at=datetime.now(timezone.utc),payload={},metadata_={}))
    with pytest.raises(ValueError,match='desconocido'):await ProjectionEngine(store_pg.sessions).rebuild_all()
    read=await OrderQueries(store_pg.sessions).get(event.aggregate_id)
    assert read is not None and read[1]==1

@pytest.mark.asyncio
async def test_rebuild_serializes_with_writes(store_pg,monkeypatch):
    event,aggregate=await create(store_pg)
    original=ProjectionEngine.apply;started=asyncio.Event();release=asyncio.Event();first=True
    async def slow(session,record,state):
        nonlocal first
        if first:
            first=False;started.set();await release.wait()
        await original(session,record,state)
    monkeypatch.setattr(ProjectionEngine,'apply',staticmethod(slow))
    rebuild=asyncio.create_task(ProjectionEngine(store_pg.sessions).rebuild_all())
    await started.wait()
    write=asyncio.create_task(store_pg.append_events(event.aggregate_id,[aggregate.cancel()],1))
    await asyncio.sleep(.1);assert not write.done()
    release.set();assert await rebuild==1;assert (await write).version==2
    assert (await OrderQueries(store_pg.sessions).get(event.aggregate_id))[0].status=='cancelled'

class Publisher:
    def __init__(self,fail=True):self.fail=fail;self.calls=[]
    def publish(self,topic,event):
        self.calls.append((topic,event.payload))
        if self.fail:self.fail=False;raise RuntimeError('Kafka unavailable')

@pytest.mark.asyncio
async def test_outbox_retries_and_preserves_lab02_contract(store_pg):
    event,aggregate=await create(store_pg)
    publisher=Publisher();relay=OutboxRelay(store_pg.sessions,publisher)
    with pytest.raises(RuntimeError):await relay.dispatch_once()
    async with store_pg.sessions() as session:
        assert all(row.sent_at is None for row in (await session.scalars(select(OutboxRecord))).all())
    assert await relay.dispatch_once();assert await relay.dispatch_once();assert not await relay.dispatch_once()
    assert publisher.calls[0]==publisher.calls[1]
    integration=IntegrationOrderCreated.model_validate(publisher.calls[2][1])
    assert integration.event_id==event.event_id and integration.order_id==event.aggregate_id
    assert integration.items[0].product_id==event.items[0].product_id

@pytest.mark.asyncio
async def test_item_added_only_queues_audit_not_new_reservation(store_pg):
    event,aggregate=await create(store_pg)
    await store_pg.append_events(event.aggregate_id,[aggregate.add_item(payload().items[0])],1)
    async with store_pg.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OutboxRecord).where(OutboxRecord.topic=='orders.created'))==1

@pytest.mark.asyncio
async def test_api_commands_query_and_version_headers(client_pg):
    response=await client_pg.post('/api/v1/orders',json=payload().model_dump(mode='json'))
    assert response.status_code==201 and response.headers['X-Aggregate-Version']=='1'
    oid=response.json()['id'];assert response.json()['total']=='0.10'
    response=await client_pg.patch(f'/api/v1/orders/{oid}/status',json={'new_status':'confirmed'})
    assert response.status_code==200 and response.headers['X-Aggregate-Version']=='2'
    stale=await client_pg.patch(f'/api/v1/orders/{oid}/cancel',headers={'X-Expected-Version':'1'})
    assert stale.status_code==409 and stale.json()['code']=='VERSION_CONFLICT'
    invalid=await client_pg.patch(f'/api/v1/orders/{oid}/status',json={'new_status':'shipped'})
    assert invalid.status_code==409
    response=await client_pg.patch(f'/api/v1/orders/{oid}/cancel')
    assert response.status_code==200 and response.json()['status']=='cancelled'
    read=await client_pg.get(f'/api/v1/orders/{oid}')
    assert read.json()==response.json() and read.headers['X-Aggregate-Version']=='3'

@pytest.mark.asyncio
async def test_queries_do_not_fallback_to_events(client_pg,store_pg):
    event,aggregate=await create(store_pg)
    async with store_pg.sessions() as session,session.begin():
        await session.execute(text('DELETE FROM order_projections'))
    assert (await client_pg.get(f'/api/v1/orders/{event.aggregate_id}')).status_code==404
    assert (await store_pg.load(event.aggregate_id)).order is not None
    assert (await client_pg.get('/admin/rebuild-projections')).status_code==405
    assert (await client_pg.post('/admin/rebuild-projections')).status_code==403
    rebuild=await client_pg.post('/admin/rebuild-projections',headers={'X-Admin-Key':'test-admin'})
    assert rebuild.status_code==200 and rebuild.json()['events_processed']==1
    assert (await client_pg.get(f'/api/v1/orders/{event.aggregate_id}')).status_code==200

@pytest.mark.asyncio
async def test_api_validation_and_missing_order(client_pg):
    assert (await client_pg.get('/api/v1/orders/'+str(uuid4()))).status_code==404
    assert (await client_pg.get('/api/v1/orders/not-a-uuid')).status_code==422
    assert (await client_pg.get('/api/v1/orders?limit=-1')).status_code==422
    assert (await client_pg.post('/api/v1/orders',json={'customer_id':str(uuid4()),'items':[]})).status_code==422
    assert (await client_pg.get('/health')).status_code==200
