from datetime import datetime
from uuid import uuid4
import pytest
from pydantic import ValidationError
from shared.events import OrderCreated, RequestedItem
from shared.kafka import EventPublisher, PublicationError

def event():
    return OrderCreated(order_id=uuid4(), customer_id=uuid4(),
        items=[RequestedItem(product_id=uuid4(), quantity=1)])

def test_event_roundtrip_preserves_identity():
    source = event()
    assert OrderCreated.model_validate_json(source.to_kafka_value()) == source
    assert source.timestamp.utcoffset().total_seconds() == 0

@pytest.mark.parametrize("field,value", [
    ("event_type", "Wrong"), ("source_service", "other"),
    ("event_version", "2.0.0"), ("timestamp", datetime(2026,1,1)),
    ("event_id", "00000000-0000-0000-0000-000000000000"), ("items", [])])
def test_invalid_envelope_rejected(field, value):
    data = event().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        OrderCreated.model_validate(data)

class Message:
    def partition(self):return 1
    def offset(self):return 7

class NativeProducer:
    def __init__(self, error=None, remaining=0, callback=True):
        self.error, self.remaining, self.callback = error, remaining, callback
        self.kwargs = None
    def produce(self, topic, **kwargs):self.kwargs = kwargs
    def flush(self, timeout):
        if self.callback:self.kwargs['on_delivery'](self.error, Message())
        return self.remaining

@pytest.mark.parametrize('error,remaining,callback', [('delivery failed',0,True),(None,1,False),(None,0,False)])
def test_unconfirmed_delivery_raises(error, remaining, callback):
    publisher = EventPublisher('unused','test', NativeProducer(error,remaining,callback))
    with pytest.raises(PublicationError):publisher.publish('orders.created',event())

def test_delivery_uses_order_key_and_checks_ack():
    native = NativeProducer()
    publisher = EventPublisher('unused','test',native)
    source = event()
    assert publisher.publish('orders.created',source) == (1,7)
    assert native.kwargs['key'] == str(source.order_id).encode()

def test_worker_exhausted_retry_window_stops_without_commit(monkeypatch):
    from types import SimpleNamespace
    import app.messaging as messaging
    from app.messaging import InventoryWorker
    class Consumer:
        def __init__(self):self.closed=False;self.commits=[]
        def subscribe(self,topics,on_assign,on_revoke):on_assign(self,[])
        def poll(self,timeout):return SimpleNamespace(error=lambda:None)
        def commit(self,**kwargs):self.commits.append(kwargs)
        def close(self):self.closed=True
    consumer=Consumer()
    worker=InventoryWorker(None,None,'unused',consumer)
    times=iter([0,61])
    monkeypatch.setattr(messaging,'time',SimpleNamespace(monotonic=lambda:next(times)))
    def unavailable(message):raise RuntimeError('Redis unavailable')
    monkeypatch.setattr(worker,'handle',unavailable)
    worker.run()
    assert consumer.closed and not consumer.commits
    assert not worker.ready.is_set()
