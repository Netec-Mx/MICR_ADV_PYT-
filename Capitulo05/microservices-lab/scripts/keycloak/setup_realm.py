"""Build the declarative import; no broad exception handlers or partial success.

Run from the project root: python scripts/keycloak/setup_realm.py
Keycloak imports it on first startup; an existing realm is not overwritten.
"""
import json
from pathlib import Path

PERMISSIONS={'orders.read':'order:read','orders.write':'order:write',
             'inventory.read':'inventory:read','inventory.write':'inventory:write','ops.admin':'ops:admin'}

def audience_mapper(audience):
    return {'name':'aud-'+audience,'protocol':'openid-connect','protocolMapper':'oidc-audience-mapper',
            'config':{'included.custom.audience':audience,'access.token.claim':'true','id.token.claim':'false'}}

ROLE_MAPPER={'name':'realm-roles','protocol':'openid-connect','protocolMapper':'oidc-usermodel-realm-role-mapper',
 'config':{'claim.name':'realm_access.roles','jsonType.label':'String','multivalued':'true',
           'access.token.claim':'true','id.token.claim':'false','userinfo.token.claim':'false'}}

SUB_MAPPER={'name':'subject','protocol':'openid-connect','protocolMapper':'oidc-sub-mapper',
 'config':{'access.token.claim':'true','id.token.claim':'true','introspection.token.claim':'true'}}

def build_realm():
    scopes=[]
    for scope in PERMISSIONS:
        audience='inventory-api' if scope.startswith('inventory.') else 'order-api'
        scopes.append({'name':scope,'protocol':'openid-connect',
                       'attributes':{'include.in.token.scope':'true'},'protocolMappers':[audience_mapper(audience)]})
    clients=[];users=[]
    definitions=[('lab-admin-client','lab-admin-secret',list(PERMISSIONS),list(PERMISSIONS.values())),
        ('readonly-client','readonly-secret',['orders.read','inventory.read'],['order:read','inventory:read']),
        ('order-service-client','order-svc-secret-lab',['inventory.read'],['inventory:read']),
        ('inventory-service-client','inventory-svc-secret-lab',['inventory.read'],['inventory:read']),
        ('expiry-test-client','expiry-test-secret',['orders.read'],['order:read'])]
    for name,secret,allowed,roles in definitions:
        clients.append({'clientId':name,'enabled':True,'protocol':'openid-connect','publicClient':False,
            'secret':secret,'clientAuthenticatorType':'client-secret','serviceAccountsEnabled':True,
            'standardFlowEnabled':False,'directAccessGrantsEnabled':False,'fullScopeAllowed':False,
            'defaultClientScopes':[],'optionalClientScopes':allowed,'protocolMappers':[ROLE_MAPPER,SUB_MAPPER]})
        if name=='expiry-test-client':clients[-1]['attributes']={'access.token.lifespan':'2'}
        users.append({'username':'service-account-'+name,'enabled':True,'serviceAccountClientId':name,
                      'realmRoles':roles})
    clients.append({'clientId':'frontend-client','enabled':True,'protocol':'openid-connect','publicClient':True,
        'serviceAccountsEnabled':False,'standardFlowEnabled':True,'directAccessGrantsEnabled':False,
        'fullScopeAllowed':False,'redirectUris':['http://127.0.0.1:8765/callback'],
        'webOrigins':['http://127.0.0.1:8765'],'defaultClientScopes':[],
        'optionalClientScopes':list(PERMISSIONS),'protocolMappers':[ROLE_MAPPER,SUB_MAPPER],
        'attributes':{'pkce.code.challenge.method':'S256'}})
    for name,password,roles in [('admin-user','Admin-Lab05!',list(PERMISSIONS.values())),
                                ('readonly-user','Read-Lab05!',['order:read','inventory:read'])]:
        users.append({'username':name,'enabled':True,'firstName':'Lab','lastName':name,
                      'email':name+'@example.test','emailVerified':True,'realmRoles':roles,
                      'credentials':[{'type':'password','value':password,'temporary':False}]})
    return {'realm':'microservices-lab','enabled':True,'sslRequired':'none',
            'accessTokenLifespan':300,'registrationAllowed':False,
            'roles':{'realm':[{'name':name} for name in PERMISSIONS.values()]},
            'clientScopes':scopes,'clients':clients,'users':users,
            'scopeMappings':[{'client':name,'roles':roles} for name,secret,allowed,roles in definitions]
                +[{'client':'frontend-client','roles':list(PERMISSIONS.values())}]}

if __name__=='__main__':
    path=Path(__file__).resolve().parents[2]/'infra/keycloak/microservices-lab-realm.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(build_realm(),indent=2),encoding='utf-8')
    print('Realm declarativo generado:',path)
