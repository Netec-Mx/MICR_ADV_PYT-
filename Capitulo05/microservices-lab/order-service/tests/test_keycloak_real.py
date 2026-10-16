"""Optional tests against real Keycloak, never substitute mocked JWT issuance."""
import asyncio,base64,hashlib,html,os,secrets
from html.parser import HTMLParser
from urllib.parse import urlencode,urlparse,parse_qs
import httpx,pytest
from shared.auth import JWTValidator,InvalidToken

@pytest.fixture
def issuer():
    value=os.getenv('KEYCLOAK_TEST_ISSUER')
    if not value:pytest.skip('Define KEYCLOAK_TEST_ISSUER for real Keycloak tests')
    return value

def acquire(issuer,name,secret,scope):
    with httpx.Client(timeout=10,trust_env=False) as client:
        response=client.post(issuer+'/protocol/openid-connect/token',data={
            'grant_type':'client_credentials','client_id':name,'client_secret':secret,'scope':scope})
        response.raise_for_status();return response.json()

@pytest.mark.asyncio
async def test_real_service_token_roles_scope_and_resource_audience(issuer):
    token=acquire(issuer,'order-service-client','order-svc-secret-lab','inventory.read')['access_token']
    inv=JWTValidator(issuer,'inventory-api',issuer+'/protocol/openid-connect/certs')
    orders=JWTValidator(issuer,'order-api',issuer+'/protocol/openid-connect/certs')
    try:
        claims=await inv.validate_token(token)
        assert claims['azp']=='order-service-client'
        assert 'inventory:read' in claims['realm_access']['roles'] and 'inventory:write' not in claims['realm_access']['roles']
        assert 'inventory.read' in claims['scope'].split()
        with pytest.raises(InvalidToken):await orders.validate_token(token)
    finally:await inv.close();await orders.close()

@pytest.mark.asyncio
async def test_real_keycloak_expired_correctly_signed_token(issuer):
    data=acquire(issuer,'expiry-test-client','expiry-test-secret','orders.read')
    assert data['expires_in']<=2
    validator=JWTValidator(issuer,'order-api',issuer+'/protocol/openid-connect/certs')
    try:
        await validator.validate_token(data['access_token'])
        await asyncio.sleep(data['expires_in']+1)
        with pytest.raises(InvalidToken):await validator.validate_token(data['access_token'])
    finally:await validator.close()

def test_real_password_grant_disabled(issuer):
    with httpx.Client(timeout=10,trust_env=False) as client:
        response=client.post(issuer+'/protocol/openid-connect/token',data={'grant_type':'password',
            'client_id':'frontend-client','username':'admin-user','password':'Admin-Lab05!'})
        assert response.status_code==400

def authorization_code(issuer,client):
    verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state=secrets.token_urlsafe(32)
    redirect='http://127.0.0.1:8765/callback'
    response=client.get(issuer+'/protocol/openid-connect/auth',params={
        'response_type':'code','client_id':'frontend-client','redirect_uri':redirect,
        'scope':'openid orders.read inventory.read','state':state,
        'code_challenge':challenge,'code_challenge_method':'S256'})
    response.raise_for_status()
    class FormParser(HTMLParser):
        action=None
        def handle_starttag(self,tag,attrs):
            data=dict(attrs)
            if tag=='form' and data.get('id')=='kc-form-login':self.action=data['action']
    parser=FormParser();parser.feed(response.text)
    assert parser.action,'Keycloak did not present login form'
    # Browsers allow Secure cookies on localhost. HTTPX's generic cookie jar
    # does not; send the server-issued session cookies only for this loopback test.
    headers={}
    if urlparse(issuer).hostname in {'localhost','127.0.0.1'}:
        headers['Cookie']='; '.join(f'{cookie.name}={cookie.value}' for cookie in client.cookies.jar)
    response=client.post(html.unescape(parser.action),headers=headers,
        data={'username':'readonly-user','password':'Read-Lab05!','credentialId':''})
    assert response.status_code in {302,303},response.status_code
    params=parse_qs(urlparse(response.headers['Location']).query)
    assert params.get('state')==[state] and 'code' in params
    return params['code'][0],verifier,redirect

@pytest.mark.asyncio
async def test_real_authorization_code_s256_and_readonly_roles(issuer):
    with httpx.Client(timeout=10,trust_env=False,follow_redirects=False) as client:
        code,verifier,redirect=authorization_code(issuer,client)
        response=client.post(issuer+'/protocol/openid-connect/token',data={
            'grant_type':'authorization_code','client_id':'frontend-client','code':code,
            'code_verifier':verifier,'redirect_uri':redirect})
        response.raise_for_status();token=response.json()['access_token']
    validator=JWTValidator(issuer,'order-api',issuer+'/protocol/openid-connect/certs')
    try:
        claims=await validator.validate_token(token)
        assert 'order:read' in claims['realm_access']['roles'] and 'order:write' not in claims['realm_access']['roles']
    finally:await validator.close()

def test_real_authorization_code_rejects_wrong_verifier(issuer):
    with httpx.Client(timeout=10,trust_env=False,follow_redirects=False) as client:
        code,verifier,redirect=authorization_code(issuer,client)
        response=client.post(issuer+'/protocol/openid-connect/token',data={
            'grant_type':'authorization_code','client_id':'frontend-client','code':code,
            'code_verifier':secrets.token_urlsafe(48),'redirect_uri':redirect})
        assert response.status_code==400
