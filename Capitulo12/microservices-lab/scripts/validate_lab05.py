"""Real HTTP/Keycloak validation. Requires all five Compose overlays."""
import os,time
from uuid import uuid4
import httpx
ISSUER=os.getenv('AUTH_ISSUER','http://localhost:8080/realms/microservices-lab')
ORDER=os.getenv('ORDER_API_URL','http://localhost:8001')
INVENTORY=os.getenv('INVENTORY_API_URL','http://localhost:8002')
def check(condition,message):
    if not condition:raise RuntimeError(message)
def main():
    with httpx.Client(timeout=15,trust_env=False) as http:
        def token(client,secret,scope):
            r=http.post(ISSUER+'/protocol/openid-connect/token',data={'grant_type':'client_credentials','client_id':client,'client_secret':secret,'scope':scope})
            r.raise_for_status();return r.json()['access_token']
        def call(base,path,expected=200,method='GET',access=None,body=None):
            r=http.request(method,base+path,json=body,headers={'Authorization':'Bearer '+access} if access else {})
            check(r.status_code==expected,f'{method} {path}: esperado {expected}, recibido {r.status_code}')
            return r
        admin=token('lab-admin-client','lab-admin-secret','orders.read orders.write inventory.read inventory.write ops.admin')
        readonly=token('readonly-client','readonly-secret','orders.read inventory.read')
        service=token('order-service-client','order-svc-secret-lab','inventory.read')
        for base,path in [(ORDER,'/api/v1/orders'),(INVENTORY,'/api/v1/products')]:
            call(base,'/health');call(base,path,401);call(base,path,401,access='invalid.jwt.token')
            call(base,path,access=readonly)
            call(base,path,403,'POST',readonly,{})
        call(ORDER,'/api/v1/orders',401,access=service)
        call(INVENTORY,'/api/v1/products',403,'POST',service,{})
        product=call(INVENTORY,'/api/v1/products',201,'POST',admin,{'name':'Lab05','sku':'AUTH-'+uuid4().hex[:8].upper(),'stock_quantity':20}).json()
        response=call(ORDER,'/api/v1/orders',201,'POST',admin,{'customer_id':str(uuid4()),'items':[{'product_id':product['id'],'quantity':2,'unit_price':'10.00'}]})
        check(response.headers.get('X-Stock-Precheck')=='verified','La prevalidación debe usar el servicio real autenticado')
        order=response.json();check(order['status']=='pending','Estado inicial incorrecto')
        call(ORDER,'/api/v1/orders/'+order['id'],access=readonly)
        for _ in range(120):
            stock=call(INVENTORY,'/api/v1/products/'+product['id'],access=readonly).json()['stock_quantity']
            if stock==18:break
            time.sleep(.5)
        check(stock==18,'La reserva Kafka/Redis no se materializó en 60 segundos')
        short=token('expiry-test-client','expiry-test-secret','orders.read')
        call(ORDER,'/api/v1/orders',access=short);time.sleep(3)
        call(ORDER,'/api/v1/orders',401,access=short)
        call(ORDER,'/health/circuit-breakers',403,access=readonly)
        call(ORDER,'/health/circuit-breakers',access=admin)
        print('APROBADO: JWT, audiencias, roles/scopes, Client Credentials, expiración y reserva Kafka/Redis; tokens no impresos.')
if __name__=='__main__':main()
