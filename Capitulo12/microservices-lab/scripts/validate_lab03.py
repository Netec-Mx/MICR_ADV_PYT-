from api_auth import auth_headers
"""Validación real HTTP/EventStore; requiere API CQRS y PostgreSQL migrado."""
import asyncio,json,os,sys,time
from pathlib import Path
from uuid import uuid4
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'order-service'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,func
from app.eventstore.store import EventStore
from app.eventstore.models import EventRecord,SnapshotOrder,OutboxRecord
from shared.events import OrderCreated as IntegrationOrderCreated

BASE='http://localhost:8001'
def check(condition,message):
    if not condition:raise RuntimeError(message)
def call(path,method='GET',body=None,expected=200,headers=None):
    data=json.dumps(body).encode() if body is not None else None
    request=Request(BASE+path,data=data,method=method,
        headers={'Content-Type':'application/json',**auth_headers(),**(headers or {})})
    try:
        with urlopen(request,timeout=60) as response:code,payload=response.status,json.load(response)
    except HTTPError as error:code,payload=error.code,json.load(error)
    check(code==expected,f'{method} {path}: HTTP {code}, {payload}')
    return payload

async def main():
    url=os.getenv('EVENTSTORE_DATABASE_URL','postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db')
    store=EventStore(url)
    try:
        call('/health')
        request=Request('http://localhost:8002/api/v1/products',method='POST',
            headers={'Content-Type':'application/json',**auth_headers()},data=json.dumps({
            'name':'Snapshot Lab03/04','sku':'SNAP-'+uuid4().hex[:8].upper(),'stock_quantity':100}).encode())
        with urlopen(request,timeout=15) as response:product=json.load(response)
        item={'product_id':product['id'],'quantity':1,'unit_price':'2.50'}
        order=call('/api/v1/orders','POST',{'customer_id':str(uuid4()),'items':[item]},201)
        oid=order['id']
        # Items added are domain-only; do not emit new reservations in Lab 02.
        for _ in range(9):call(f'/api/v1/orders/{oid}/items','POST',item)
        read=call(f'/api/v1/orders/{oid}')
        check(read['total']=='25.00' and len(read['items'])==10,'Proyección incorrecta')
        from uuid import UUID
        async with store.sessions() as session:
            snap=await session.get(SnapshotOrder,UUID(oid))
            check(snap is not None and snap.aggregate_version==10,'Falta snapshot de versión 10')
        call(f'/api/v1/orders/{oid}/status','PATCH',{'new_status':'confirmed'})
        aggregate=await store.load(UUID(oid));full=await store.load(UUID(oid),use_snapshot=False)
        check(aggregate.version==11 and aggregate.snapshot()==full.snapshot(),'Snapshot + tail difiere de replay completo')
        call(f'/api/v1/orders/{oid}/status','PATCH',{'new_status':'shipped'},409)
        call(f'/api/v1/orders/{oid}/cancel','PATCH')
        before=call(f'/api/v1/orders/{oid}')
        call('/admin/rebuild-projections','POST',headers={'X-Admin-Key':os.getenv('EVENTSTORE_ADMIN_KEY','lab-admin-key')})
        check(call(f'/api/v1/orders/{oid}')==before,'Rebuild cambió el estado')
        async with store.sessions() as session:
            record=await session.scalar(select(EventRecord).where(EventRecord.aggregate_id==UUID(oid),EventRecord.aggregate_version==1))
            outbox=await session.scalar(select(OutboxRecord).where(OutboxRecord.order_id==UUID(oid),OutboxRecord.topic=='orders.created'))
            event=IntegrationOrderCreated.model_validate(outbox.payload)
            check(str(event.event_id)==str(record.event_id) and len(event.items)==1,'Contrato Lab 02 incompatible')
        # Require all rows of this aggregate acknowledged, not merely queued.
        deadline=time.monotonic()+90
        while True:
            async with store.sessions() as session:
                pending=await session.scalar(select(func.count()).select_from(OutboxRecord).where(
                    OutboxRecord.order_id==UUID(oid),OutboxRecord.sent_at.is_(None)))
            if pending==0:break
            check(time.monotonic()<deadline,'Outbox sigue pendiente; revisa Kafka y el relay')
            await asyncio.sleep(.2)
        print('LAB 03 APROBADO: snapshot 10, tail 11, transición, cancelación, rebuild y outbox confirmada.')
        print('order_id:',oid)
        print('El producto creado tiene stock; la reserva inicial corresponde al consumidor del laboratorio 2.')
    finally:await store.engine.dispose()

if __name__=='__main__':asyncio.run(main())
