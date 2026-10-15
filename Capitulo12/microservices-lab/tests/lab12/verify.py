import json,subprocess,threading,tempfile,time,os,sys,yaml,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import urllib.request
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts/lab12'))
from analyze import summarize
from jsonschema import Draft7Validator
for f in (root/'chaos/lab12').glob('*.yaml'):
 d=yaml.safe_load(f.read_text());c=yaml.safe_load(Path(os.environ['CHAOS_CRDS']+'/chaos-mesh.org_'+d['kind'].lower()+'.yaml').read_text());schema=c['spec']['versions'][0]['schema']['openAPIV3Schema'];Draft7Validator(schema).validate(d)
 print('CRD VALID',f.name)
render=subprocess.check_output([os.environ.get('HELM','helm'),'template','lab08-observability',str(root/'observability/chart'),'--set','mesh.enabled=true','--set','lab12.enabled=true'],text=True);docs=list(yaml.safe_load_all(render));cm=next(x for x in docs if x and x['kind']=='ConfigMap' and x['metadata']['name']=='lab08-prometheus');rules=Path('/tmp/lab12-rules.yaml');rules.write_text(cm['data']['rules.yaml']);subprocess.run([os.environ.get('PROMTOOL','promtool'),'check','rules',str(rules)],check=True)
# Real k6 and Prometheus; fixture verifies request shape/Host/auth, not business backend.
seen=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def answer(self,code,body):
  raw=json.dumps(body).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
 def do_POST(self):
  raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
  if self.path.endswith('/token'):self.answer(200,{'access_token':'test-token','expires_in':300});return
  if self.headers.get('Host')!='microservices.local' or self.headers.get('Authorization')!='Bearer test-token':self.answer(403,{});return
  body=json.loads(raw);seen.append((self.path,body))
  if self.path=='/api/v1/products':
   assert body['stock_quantity']==1000000;self.answer(201,{**body,'id':'22222222-2222-4222-8222-222222222222'})
  elif self.path=='/api/v1/orders':
   assert body['items'][0]['unit_price']=='3.50';uuid.UUID(body['items'][0]['product_id']);self.answer(201,{'id':str(uuid.uuid4())})
  else:self.answer(404,{})
 def do_GET(self):
  assert self.headers['Host']=='microservices.local';assert self.headers['Authorization']=='Bearer test-token'
  self.answer(200,[] if self.path.startswith('/api/v1/orders') else {'id':'22222222-2222-4222-8222-222222222222'})
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();port=server.server_address[1]
tmp=Path(tempfile.mkdtemp());(tmp/'prom.yaml').write_text('global:\n  scrape_interval: 1s\nscrape_configs: []\n');prom=subprocess.Popen([os.environ.get('PROMETHEUS','prometheus'),'--config.file='+str(tmp/'prom.yaml'),'--storage.tsdb.path='+str(tmp/'data'),'--web.listen-address=127.0.0.1:19090','--web.enable-remote-write-receiver'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(30):
  try:urllib.request.urlopen('http://127.0.0.1:19090/-/ready');break
  except Exception:time.sleep(.1)
 env={**os.environ,'RUN_ID':'fixture-verification','PROFILE':'smoke','WORKLOAD':'mixed','GATEWAY_URL':f'http://127.0.0.1:{port}','AUTH_ISSUER':f'http://127.0.0.1:{port}','SUMMARY_PATH':str(tmp/'summary.json'),'K6_PROMETHEUS_RW_SERVER_URL':'http://127.0.0.1:19090/api/v1/write','K6_PROMETHEUS_RW_TREND_STATS':'p(95),p(99)','K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM':'false','K6_PROMETHEUS_RW_PUSH_INTERVAL':'1s'}
 subprocess.run([os.environ.get('K6','k6'),'run','--stage','4s:2','-o','experimental-prometheus-rw','-o','json='+str(tmp/'samples.json'),str(root/'tests/load/lab12.js')],env=env,check=True,stdout=subprocess.DEVNULL)
 metrics=json.load(urllib.request.urlopen('http://127.0.0.1:19090/api/v1/label/__name__/values'))['data'];assert 'k6_lab12_requests_total' in metrics;assert 'k6_lab12_latency_p95' in metrics,metrics
 result=summarize((tmp/'samples.json').read_text().splitlines());assert len(result)==2 and all(x['bad']==0 and x['availability']==1 for x in result)
 assert any(path=='/api/v1/orders' for path,_ in seen),'mixed POST not exercised'
 print('LATENCY PROM',json.load(urllib.request.urlopen('http://127.0.0.1:19090/api/v1/query?query=k6_lab12_latency_p95'))['data']);print('LATENCY SUMMARY',json.loads((tmp/'summary.json').read_text())['metrics']['lab12_latency']);print('K6 HTTP + TOKEN + MIXED PAYLOAD + PROM REMOTE WRITE: PASS');print('METRIC NAMES',metrics);print('ANALYSIS',result)
 # Budget denominator and phase boundaries.
 lines=[]
 for i in range(100):lines.append(json.dumps({'type':'Point','metric':'lab12_errors','data':{'time':'2026-10-08T00:00:00Z','tags':{'service':'order-service'},'value':int(i<2)}}))
 r=summarize(lines)[0];assert r['availability']==.98 and r['availability_budget_consumed']==4
 assert summarize([])==[]
 print('BUDGET: 2 BAD / 100 REQUESTS = 400% WINDOW BUDGET; NO DATA IS EMPTY: PASS')
finally:prom.terminate();prom.wait();server.shutdown()
