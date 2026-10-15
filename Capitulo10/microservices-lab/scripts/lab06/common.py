import os
import httpx
GATEWAY=os.getenv('GATEWAY_URL','http://localhost:18080')
HOST=os.getenv('GATEWAY_HOST','microservices.local')
ISSUER=os.getenv('AUTH_ISSUER','http://localhost:8080/realms/microservices-lab')
READ_SCOPES='orders.read inventory.read users.read'
def token(admin=False,scope=None):
    name='lab-admin-client' if admin else 'readonly-client'
    secret='lab-admin-secret' if admin else 'readonly-secret'
    scope=scope or ('orders.read orders.write inventory.read inventory.write ops.admin users.read' if admin else READ_SCOPES)
    with httpx.Client(timeout=10,trust_env=False) as h:
        r=h.post(ISSUER+'/protocol/openid-connect/token',data={'grant_type':'client_credentials',
            'client_id':name,'client_secret':secret,'scope':scope})
        r.raise_for_status();return r.json()['access_token']
def headers(access):return {'Host':HOST,'Authorization':'Bearer '+access}
def check(condition,message):
    if not condition:raise RuntimeError(message)
