"""Interactive Authorization Code + S256 PKCE; passwords stay on Keycloak's page."""
import argparse,base64,hashlib,hmac,json,os,secrets,time,webbrowser
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlencode,urlparse,parse_qs
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--scope',default='orders.read inventory.read')
parser.add_argument('--output',default='user-token.json')
args=parser.parse_args()
issuer=os.getenv('AUTH_ISSUER','http://localhost:8080/realms/microservices-lab')
redirect='http://127.0.0.1:8765/callback'
verifier=secrets.token_urlsafe(48)
challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
state=secrets.token_urlsafe(32)
result={}
class Callback(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path!='/callback':self.send_error(404);return
        query=parse_qs(parsed.query)
        if not hmac.compare_digest(query.get('state',[''])[0],state):
            self.send_error(400,'Invalid state');return
        if 'error' in query:result['error']=query['error'][0]
        elif 'code' in query:result['code']=query['code'][0]
        else:self.send_error(400,'Missing code');return
        self.send_response(200);self.end_headers()
        self.wfile.write(b'Login received. You can close this window and return to the terminal.')
url=issuer+'/protocol/openid-connect/auth?'+urlencode({'response_type':'code','client_id':'frontend-client',
    'redirect_uri':redirect,'scope':'openid '+args.scope,'state':state,
    'code_challenge':challenge,'code_challenge_method':'S256'})
with HTTPServer(('127.0.0.1',8765),Callback) as server:
    server.timeout=1
    print('Abre esta URL para iniciar sesión:',url)
    webbrowser.open(url)
    deadline=time.monotonic()+180
    while not result and time.monotonic()<deadline:server.handle_request()
if 'code' not in result:raise SystemExit('No se recibió un código válido: '+result.get('error','timeout'))
with httpx.Client(timeout=10,trust_env=False,follow_redirects=False) as client:
    response=client.post(issuer+'/protocol/openid-connect/token',data={'grant_type':'authorization_code',
        'client_id':'frontend-client','redirect_uri':redirect,'code':result['code'],'code_verifier':verifier})
    response.raise_for_status()
    data=response.json()
# Keep only the access token needed for this exercise; no refresh/id token stored.
fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as output:
    json.dump({'access_token':data['access_token'],'expires_in':data['expires_in']},output)
print('Access token guardado en',args.output,'; no se muestra en consola.')
