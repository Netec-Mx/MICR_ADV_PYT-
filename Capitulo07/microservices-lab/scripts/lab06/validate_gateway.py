"""Validate HTTP routing/security and the retained business flow via gateway."""
import time
from uuid import uuid4
import httpx
from common import GATEWAY,HOST,token,headers,check

def validate():
    admin=token(admin=True);readonly=token()
    with httpx.Client(base_url=GATEWAY,timeout=15,trust_env=False) as h:
        def call(path,expected=200,method='GET',access=admin,body=None,host=HOST):
            hs={'Host':host}
            if access:hs['Authorization']='Bearer '+access
            r=h.request(method,path,json=body,headers=hs)
            check(r.status_code==expected,f'{method} {path}: esperado {expected}, recibido {r.status_code}')
            return r
        paths=['/api/v1/orders','/api/v1/products','/api/v1/users']
        for path in paths:
            call(path,access=readonly);call(path,401,access=None)
            call(path,401,access='invalid.jwt.token')
        call('/api/v1/orders',404,host='wrong.local')
        call('/ruta-inexistente',404)
        call('/api/v1/orders-evil',404)
        call('/dashboard/',404);call('/api/http/routers',404)
        call('/api/v1/orders',403,'POST',readonly,{})
        wrong=token(scope='users.read')
        call('/api/v1/orders',401,access=wrong)
        product=call('/api/v1/products',201,'POST',admin,{
            'name':'Gateway Lab06','sku':'GW-'+uuid4().hex[:8].upper(),'stock_quantity':20}).json()
        r=call('/api/v1/orders',201,'POST',admin,{'customer_id':str(uuid4()),'items':[
            {'product_id':product['id'],'quantity':2,'unit_price':'10.00'}]})
        check(r.headers.get('X-Stock-Precheck')=='verified','Precheck HTTP no autenticado o degradado')
        order=r.json();check(order['status']=='pending' and order['total']=='20.00','Contrato de pedido alterado')
        call('/api/v1/orders/'+order['id'],access=readonly)
        for _ in range(120):
            stock=call('/api/v1/products/'+product['id'],access=readonly).json()['stock_quantity']
            if stock==18:break
            time.sleep(.5)
        check(stock==18,'Kafka/Redis no materializó reserva en 60 s')
        print('APROBADO: tres rutas, JWT, audiencia, permisos, dashboard cerrado y flujo Orders/Inventory/Kafka/Redis.')
if __name__=='__main__':validate()
