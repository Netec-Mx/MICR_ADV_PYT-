"""REDIS_TEST_URL debe apuntar a un Redis de pruebas accesible."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
import redis
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.product import ProductCreate, StockReservationCreate
from app.services.redis_inventory import RedisInventoryService, EventIdCollision
from app.messaging import InventoryWorker
from shared.events import OrderCreated, RequestedItem

@pytest.fixture
def service():
    url = os.getenv('REDIS_TEST_URL')
    if not url:pytest.skip('Define REDIS_TEST_URL para ejecutar contra Redis real')
    client = redis.Redis.from_url(url,decode_responses=True,socket_timeout=3)
    client.ping()
    prefix = f'lab02-test:{uuid4()}:'
    instance = RedisInventoryService(client,prefix)
    try:yield instance
    finally:
        keys = list(client.scan_iter(match=prefix+'*'))
        if keys:client.delete(*keys)
        client.close()

def add(service, stock=10):
    return service.add_product(ProductCreate(name='Sensor',sku='SNS-TEST',stock_quantity=stock))

def event(product, quantity=3, extra=None):
    items = [RequestedItem(product_id=product.id,quantity=quantity)]
    if extra:items.extend(extra)
    return OrderCreated(order_id=uuid4(),customer_id=uuid4(),items=items)

def test_duplicate_three_times_decrements_once_and_retains_ttl(service):
    product=add(service);source=event(product)
    records=[service.process_event(source) for _ in range(3)]
    assert [fresh for _,fresh in records] == [True,False,False]
    assert service.get_product(product.id).stock_quantity == 7
    assert service.reservation_count() == 1
    assert len({record['reply']['event_id'] for record,_ in records}) == 1
    assert 86390 <= service.client.ttl(service.event_key(source.event_id)) <= 86400
    service.mark_published(source.event_id)
    assert 86390 <= service.client.ttl(service.event_key(source.event_id)) <= 86400

def test_multi_item_failure_is_atomic_and_deduplicated(service):
    first,second=add(service,10),add(service,1)
    source=event(first,3,[RequestedItem(product_id=second.id,quantity=2)])
    record,fresh=service.process_event(source)
    assert fresh and record['reply']['event_type']=='StockReservationFailed'
    assert record['reply']['reason']=='INSUFFICIENT_STOCK'
    assert service.get_product(first.id).stock_quantity==10
    assert service.get_product(second.id).stock_quantity==1
    assert service.reservation_count()==0
    assert not service.process_event(source)[1]

def test_missing_product_is_not_treated_as_zero_stock_product(service):
    product=add(service)
    source=event(product,1,[RequestedItem(product_id=uuid4(),quantity=1)])
    record,_=service.process_event(source)
    assert record['reply']['reason']=='PRODUCT_NOT_FOUND'
    assert service.get_product(product.id).stock_quantity==10

def test_repeated_product_lines_consolidated(service):
    product=add(service)
    source=event(product,2,[RequestedItem(product_id=product.id,quantity=3)])
    record,_=service.process_event(source)
    assert len(record['reply']['items'])==1
    assert record['reply']['items'][0]['quantity_reserved']==5
    assert service.get_product(product.id).stock_quantity==5
    assert service.reservation_count()==1

def test_concurrent_duplicates_apply_one_effect(service):
    product=add(service);source=event(product)
    with ThreadPoolExecutor(max_workers=8) as pool:
        records=list(pool.map(lambda _: service.process_event(source),range(8)))
    assert sum(fresh for _,fresh in records)==1
    assert service.get_product(product.id).stock_quantity==7
    assert service.reservation_count()==1

def test_different_events_cannot_overdraw_same_product(service):
    product=add(service,6);events=[event(product,3) for _ in range(5)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(service.process_event,events))
    assert sum(r['reply']['event_type']=='StockReserved' for r,_ in results)==2
    assert service.get_product(product.id).stock_quantity==0
    assert service.reservation_count()==2

def test_event_id_collision_rejected(service):
    product=add(service);source=event(product)
    service.process_event(source)
    altered=OrderCreated(**{**source.model_dump(),'items':[RequestedItem(product_id=product.id,quantity=4)]})
    with pytest.raises(EventIdCollision):service.process_event(altered)
    assert service.get_product(product.id).stock_quantity==7

def test_api_and_events_share_same_inventory(service):
    with TestClient(create_app(service=service)) as client:
        product=client.post('/api/v1/products',json={'name':'Sensor','sku':'SNS-HTTP','stock_quantity':5}).json()
        source=OrderCreated(order_id=uuid4(),customer_id=uuid4(),items=[RequestedItem(product_id=product['id'],quantity=3)])
        service.process_event(source)
        assert client.get('/api/v1/products/'+product['id']).json()['stock_quantity']==2
        response=client.post('/api/v1/reservations',json={'product_id':product['id'],'order_id':str(source.order_id),'quantity':3})
        assert response.status_code==409
        assert client.get('/api/v1/products/'+product['id']).json()['stock_quantity']==2

class Message:
    def __init__(self,source):self.source=source
    def value(self):return self.source.to_kafka_value()
    def key(self):return str(self.source.order_id).encode()
    def partition(self):return 0
    def offset(self):return 10

class Consumer:
    def __init__(self):self.commits=[]
    def commit(self,**kwargs):self.commits.append(kwargs)

class Publisher:
    def __init__(self,fail=True):self.fail,self.calls=fail,[]
    def publish(self,topic,event):
        self.calls.append((topic,event))
        if self.fail:
            self.fail=False
            raise RuntimeError('Fallo después de efecto Redis')

def test_publication_retry_does_not_decrement_again_or_commit_early(service):
    product=add(service);source=event(product)
    publisher,consumer=Publisher(),Consumer()
    worker=InventoryWorker(service,publisher,'unused',consumer)
    message=Message(source)
    with pytest.raises(RuntimeError):worker.handle(message)
    assert not consumer.commits
    assert service.get_product(product.id).stock_quantity==7
    worker.handle(message)
    worker.handle(message)
    assert service.get_product(product.id).stock_quantity==7
    assert len(publisher.calls)==2
    assert publisher.calls[0][1].event_id==publisher.calls[1][1].event_id
    assert len(consumer.commits)==2
    assert all(c['asynchronous'] is False for c in consumer.commits)


def test_new_service_instance_recovers_cached_result(service):
    product=add(service);source=event(product)
    record,_=service.process_event(source)
    recreated=RedisInventoryService(service.client,service.prefix)
    recovered,fresh=recreated.process_event(source)
    assert not fresh and recovered['reply']['event_id']==record['reply']['event_id']
    assert recreated.get_product(product.id).stock_quantity==7
    assert recreated.reservation_count()==1


def test_commit_failure_retries_without_republishing_or_decrementing(service):
    product=add(service);source=event(product)
    class FailingConsumer(Consumer):
        def commit(self,**kwargs):
            if not self.commits:
                self.commits.append(kwargs)
                raise RuntimeError('Commit falló')
            self.commits.append(kwargs)
    publisher,consumer=Publisher(fail=False),FailingConsumer()
    worker=InventoryWorker(service,publisher,'unused',consumer)
    message=Message(source)
    with pytest.raises(RuntimeError):worker.handle(message)
    worker.handle(message)
    assert service.get_product(product.id).stock_quantity==7
    assert service.reservation_count()==1
    assert len(publisher.calls)==1
