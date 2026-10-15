"""Bounded read-only contract checks through the authenticated gateway."""
import argparse,json,sys,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lab06'))
from common import token,headers,GATEWAY
import schemathesis
from schemathesis.core.failures import FailureGroup
from schemathesis.checks import status_code_conformance,content_type_conformance,response_schema_conformance

def run(output,schema_dir=None):
 output.mkdir(parents=True,exist_ok=True);results=[]
 for service,port,path in [('order-service',8001,'/api/v1/orders'),('inventory-service',8002,'/api/v1/products')]:
  raw=(schema_dir/(service+'.openapi.json')).read_text() if schema_dir else subprocess.check_output(['kubectl','-n','microservices','exec','deploy/'+service,'-c',service,'--','python','-c',f'import urllib.request; print(urllib.request.urlopen("http://localhost:{port}/openapi.json").read().decode())'],text=True)
  schema_path=output/(service+'.openapi.json');schema_path.write_text(raw)
  schema=schemathesis.openapi.from_path(str(schema_path));access=token()
  for limit in (1,5,50):
   case=schema[path]['GET'].Case(query={'limit':limit} if service=='order-service' else {})
   started=datetime.now(timezone.utc).isoformat()
   try:
    response=case.call(base_url=GATEWAY,headers=headers(access),timeout=10)
    if response.status_code>=500 and 'json' not in ' '.join(response.headers.get('content-type',[])).lower():
     results.append({'service':service,'status':response.status_code,'result':'non-json-unavailable','started':started,'finished':datetime.now(timezone.utc).isoformat()});continue
    case.validate_response(response,checks=[status_code_conformance,content_type_conformance,response_schema_conformance])
    results.append({'service':service,'status':response.status_code,'result':'contract-valid'})
   except (Exception,FailureGroup) as exc:
    # Transport exceptions are availability failures; validation failures remain violations.
    import requests
    kind='transport-unavailable' if isinstance(exc,requests.RequestException) else 'contract-violation'
    results.append({'service':service,'result':kind,'error':str(exc).replace(access,'<redacted>')})
   results[-1].update(started=started,finished=datetime.now(timezone.utc).isoformat())
 for entry in results:
  entry['coverage']='Sin validación de cuerpo API' if entry['result']!='contract-valid' else 'Checks documentados en OpenAPI'
 (output/'contracts.json').write_text(json.dumps(results,indent=2))
 return results
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('directory',type=Path);a.add_argument('--during-chaos',action='store_true');a.add_argument('--schema-dir',type=Path);args=a.parse_args();r=run(args.directory,args.schema_dir)
 if any(x['result']=='contract-violation' for x in r) or (not args.during_chaos and any(x['result']!='contract-valid' for x in r)):raise SystemExit(1)
 print(json.dumps(r,indent=2))
