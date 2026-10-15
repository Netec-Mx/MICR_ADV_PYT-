import importlib.util,json,sys
from pathlib import Path
import pytest,schemathesis,requests
from schemathesis.core.failures import FailureGroup
from types import SimpleNamespace
from urllib3._collections import HTTPHeaderDict
from schemathesis.checks import response_schema_conformance,status_code_conformance,content_type_conformance
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/lab12'))
from analyze import summarize
import experiment

def point(metric,value,time='2026-10-08T00:00:00Z'):
 return json.dumps({'type':'Point','metric':metric,'data':{'time':time,'value':value,'tags':{'service':'order-service'}}})

def test_budget_and_empty():
 assert summarize([])==[]
 r=summarize([point('lab12_errors',i<2) for i in range(100)])[0]
 assert r['availability']==.98 and r['availability_budget_consumed']==4

def test_transport_is_latency_failure():
 r=summarize([point('lab12_errors',1),point('lab12_latency',0),point('lab12_slow_requests',1)])[0]
 assert r['latency_good_fraction']==0 and r['availability']==0

def test_phase_boundaries():
 timeline={'injection_requested':'2026-10-08T00:00:10Z','cleanup_confirmed':'2026-10-08T00:00:20Z'}
 lines=[point('lab12_errors',0,'2026-10-08T00:00:09Z'),point('lab12_errors',1,'2026-10-08T00:00:10Z'),point('lab12_errors',0,'2026-10-08T00:00:21Z')]
 r={x['phase']:x for x in summarize(lines,timeline)}
 assert r['baseline']['bad']==0 and r['fault-window']['bad']==1 and r['recovery']['bad']==0

def response(code,body):
 r=requests.Response();r.raw=SimpleNamespace(headers=HTTPHeaderDict({'Content-Type':'application/json'}),version=11);r.status_code=code;r.headers['Content-Type']='application/json';r._content=json.dumps(body).encode();r.request=requests.Request('GET','http://test/api/v1/orders').prepare();return r

def test_contract_accepts_documented_shape():
 schema=schemathesis.openapi.from_path(str(ROOT/'contracts/order-service.openapi.yaml'));case=schema['/api/v1/orders']['GET'].Case(query={'limit':5})
 case.validate_response(response(200,[]),checks=[status_code_conformance,content_type_conformance,response_schema_conformance])

@pytest.mark.parametrize('code,body',[(200,{'wrong':'shape'}),(418,[])])
def test_contract_rejects_shape_or_status(code,body):
 schema=schemathesis.openapi.from_path(str(ROOT/'contracts/order-service.openapi.yaml'));case=schema['/api/v1/orders']['GET'].Case()
 with pytest.raises(FailureGroup):case.validate_response(response(code,body),checks=[status_code_conformance,content_type_conformance,response_schema_conformance])

def test_active_chaos_blocks_injection_and_releases_owned_lock(monkeypatch,tmp_path):
 calls=[];monkeypatch.setattr(experiment,'ROOT',tmp_path);monkeypatch.setattr(sys,'argv',['experiment.py','pod-kill'])
 # Reuse the actual manifest while keeping reports isolated.
 (tmp_path/'chaos/lab12').mkdir(parents=True)
 (tmp_path/'chaos/lab12/pod-kill.yaml').write_text((ROOT/'chaos/lab12/pod-kill.yaml').read_text())
 monkeypatch.setattr(experiment,'cmd',lambda *a,**k:calls.append(a))
 def read(*a):
  if a==('kubectl','config','current-context'):return 'msvc-gateway'
  return json.dumps({'items':[{'metadata':{'name':'other-experiment'}}]})
 monkeypatch.setattr(experiment,'read',read)
 with pytest.raises(RuntimeError,match='otro experimento'):experiment.main()
 assert any('lab12-run-lock' in c for c in calls)
 assert not any('PodChaos/lab12-pod-kill' in c for c in calls)
 assert len([c for c in calls if c[:2]==('kubectl','create')])==1

def test_wrong_context_prevents_all_mutations(monkeypatch,tmp_path):
 calls=[];monkeypatch.setattr(experiment,'ROOT',tmp_path);monkeypatch.setattr(sys,'argv',['experiment.py','pod-kill'])
 monkeypatch.setattr(experiment,'read',lambda *a:'production');monkeypatch.setattr(experiment,'cmd',lambda *a,**k:calls.append(a))
 with pytest.raises(RuntimeError,match='Contexto'):experiment.main()
 assert calls==[]

@pytest.mark.parametrize('status,body,ctype,expected',[(200,[], 'application/json','contract-valid'),(200,{'wrong':'shape'},'application/json','contract-violation'),(503,'no healthy upstream','text/plain','non-json-unavailable')])
def test_contract_runner_classifies_real_http(monkeypatch,tmp_path,status,body,ctype,expected):
 import contracts,yaml,threading
 from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   assert self.headers['Authorization']=='Bearer fixture'
   order=self.path.startswith('/api/v1/orders');code=status if order else 200;content=body if order else []
   self.send_response(code);self.send_header('Content-Type',ctype if order else 'application/json');self.end_headers();self.wfile.write((json.dumps(content) if isinstance(content,(dict,list)) else content).encode())
 schemas=tmp_path/'schemas';schemas.mkdir()
 schema=yaml.safe_load((ROOT/'contracts/order-service.openapi.yaml').read_text());(schemas/'order-service.openapi.json').write_text(json.dumps(schema))
 inventory={'openapi':'3.0.3','info':{'title':'fixture','version':'1'},'paths':{'/api/v1/products':{'get':{'responses':{'200':{'description':'list','content':{'application/json':{'schema':{'type':'array','items':{'type':'object'}}}}}}}}}};(schemas/'inventory-service.openapi.json').write_text(json.dumps(inventory))
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 monkeypatch.setattr(contracts,'GATEWAY',f'http://127.0.0.1:{server.server_address[1]}');monkeypatch.setattr(contracts,'token',lambda:'fixture')
 try:r=contracts.run(tmp_path/'results',schemas)
 finally:server.shutdown();server.server_close()
 assert [x['result'] for x in r if x['service']=='order-service']==[expected]*3
 assert all(x['result']=='contract-valid' for x in r if x['service']=='inventory-service')
 assert (tmp_path/'results/contracts.json').exists()
