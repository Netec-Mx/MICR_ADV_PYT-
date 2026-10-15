"""Pruebas reales Kafka/Redis/HTTP. Ejecutar desde la raíz del workspace."""
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import redis
from confluent_kafka import Consumer,TopicPartition
from confluent_kafka.admin import AdminClient
from shared.events import OrderCreated,RequestedItem
from shared.kafka import EventPublisher

BOOTSTRAP=os.getenv('KAFKA_BOOTSTRAP_SERVERS','localhost:29092')
REDIS_URL=os.getenv('REDIS_URL','redis://localhost:6379/0')

# No usar assert: las comprobaciones siguen activas con python -O.
def check(condition,message):
    if not condition:raise RuntimeError(message)

def http(port,path,method='GET',body=None,expected=200):
    data=json.dumps(body).encode() if body is not None else None
    request=Request(f'http://localhost:{port}{path}',data=data,method=method,
                    headers={'Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=15) as response:
            code,payload=response.status,json.load(response)
    except HTTPError as error:
        code,payload=error.code,json.load(error)
    check(code==expected,f'{method} {path}: HTTP {code}, {payload}')
    return payload

def wait_for(fn,description,timeout=90):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if fn():return
        time.sleep(.2)
    raise RuntimeError('Timeout: '+description)

def product(stock=10):
    return http(8002,'/api/v1/products','POST',{
        'name':'Sensor','sku':'SNS-'+uuid4().hex[:8].upper(),'stock_quantity':stock},201)

def stock(pid):return http(8002,'/api/v1/products/'+pid)['stock_quantity']

def wait_committed(partition,offset):
    observer=Consumer({'bootstrap.servers':BOOTSTRAP,'group.id':'inventory-service-group',
                       'enable.auto.commit':False})
    try:
        def complete():
            entries=observer.committed([TopicPartition('orders.created',partition)],timeout=5)
            return entries[0].offset>=offset+1
        wait_for(complete,'offset confirmado por InventoryService')
    finally:observer.close()

def main():
    http(8001,'/health');http(8002,'/health')
    metadata=AdminClient({'bootstrap.servers':BOOTSTRAP}).list_topics(timeout=10)
    for topic in ['orders.created','inventory.stock-reserved','inventory.stock-failed']:
        check(topic in metadata.topics and metadata.topics[topic].error is None,'Falta topic '+topic)
        check(len(metadata.topics[topic].partitions)==3,'Se requieren 3 particiones: '+topic)
    client=redis.Redis.from_url(REDIS_URL,decode_responses=True,socket_timeout=5)
    consumer=Consumer({'bootstrap.servers':BOOTSTRAP,'group.id':'lab02-validator-'+str(uuid4()),
                       'auto.offset.reset':'earliest','enable.auto.commit':False})
    consumer.subscribe(['inventory.stock-reserved','inventory.stock-failed'])
    publisher=EventPublisher(BOOTSTRAP,'lab02-validator')
    def reply_for(oid,kind):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            message=consumer.poll(1)
            if message is None:continue
            check(not message.error(),str(message.error()))
            value=json.loads(message.value())
            if value.get('order_id')==oid:
                check(value['event_type']==kind,'Evento de respuesta inesperado')
                check(message.key()==oid.encode(),'Key incorrecta en respuesta')
                return value
        raise RuntimeError('No se recibió '+kind+' para '+oid)
    try:
        client.ping()
        # Flujo API -> Kafka -> inventario, varios artículos.
        first,second=product(10),product(5)
        order=http(8001,'/api/v1/orders','POST',{'customer_id':str(uuid4()),'items':[
            {'product_id':first['id'],'quantity':3,'unit_price':'19.99'},
            {'product_id':second['id'],'quantity':2,'unit_price':'10.00'}]},201)
        check(order['total']=='79.97','Total incorrecto')
        reply=reply_for(order['id'],'StockReserved')
        check(len(reply['items'])==2,'Se perdió un artículo')
        wait_for(lambda:stock(first['id'])==7 and stock(second['id'])==3,'reserva automática')
        print('APROBADO: pedido multiartículo y reserva automática')
        # Fallo por insuficiencia: no descontar ninguno.
        failed=http(8001,'/api/v1/orders','POST',{'customer_id':str(uuid4()),'items':[
            {'product_id':first['id'],'quantity':1,'unit_price':'19.99'},
            {'product_id':second['id'],'quantity':4,'unit_price':'10.00'}]},201)
        reply_for(failed['id'],'StockReservationFailed')
        check(stock(first['id'])==7 and stock(second['id'])==3,'Reserva parcial no permitida')
        print('APROBADO: fallo sin reserva parcial')
        # Mismo evento tres veces, hasta commit del último offset.
        p=product(10)
        event=OrderCreated(order_id=uuid4(),customer_id=uuid4(),
                           items=[RequestedItem(product_id=p['id'],quantity=3)])
        deliveries=[publisher.publish('orders.created',event) for _ in range(3)]
        reply_for(str(event.order_id),'StockReserved')
        check(len({partition for partition,_ in deliveries})==1,'Misma key en particiones distintas')
        wait_committed(*deliveries[-1])
        check(stock(p['id'])==7,'El duplicado volvió a descontar stock')
        key='lab02:idempotency:inventory:'+str(event.event_id)
        record=json.loads(client.get(key))
        check(record['published'],'Respuesta no registrada como publicada')
        check(0<client.ttl(key)<=86400,'TTL inválido')
        print('Clave Redis:',key,'TTL:',client.ttl(key))
        print('APROBADO: 3 entregas, un descuento y TTL de hasta 24 h')
        # 3 keys, cada evento se repite 5 veces; validar todas las entregas.
        p=product(20)
        for _ in range(3):
            event=OrderCreated(order_id=uuid4(),customer_id=uuid4(),
                               items=[RequestedItem(product_id=p['id'],quantity=1)])
            deliveries=[publisher.publish('orders.created',event) for _ in range(5)]
            check(len(deliveries)==5 and len({p for p,_ in deliveries})==1,'Particionamiento inconsistente')
            print('order_id:',event.order_id,'particiones:',[partition for partition,_ in deliveries])
            reply_for(str(event.order_id),'StockReserved')
            wait_committed(*deliveries[-1])
        check(stock(p['id'])==17,'La prueba de particiones duplicó efectos')
        print('APROBADO: 3 order_id, 5 entregas por key, partición estable')
        print('VALIDACIÓN LAB 02 APROBADA. Se crearon productos y pedidos nuevos.')
    finally:
        consumer.close();client.close();publisher.close()

if __name__=='__main__':main()
