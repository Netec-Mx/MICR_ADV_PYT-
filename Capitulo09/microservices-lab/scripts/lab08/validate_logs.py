import json
import os
import re
import subprocess
from pathlib import Path
context=os.getenv('KUBE_CONTEXT','msvc-gateway')
tid=Path('lab08-trace-id.txt').read_text().strip()
if not re.fullmatch('[0-9a-f]{32}',tid):raise RuntimeError('Invalid trace ID evidence')
for service in ('order-service','inventory-service'):
    result=subprocess.run(['kubectl','--context',context,'-n','microservices','logs','deployment/'+service,'--since=5m','--tail=2000'],capture_output=True,text=True,check=True)
    events=[]
    for line in result.stdout.splitlines():
        if not line.startswith('{'):continue
        entry=json.loads(line)
        if entry.get('event')=='http_request_completed' and entry.get('trace_id')==tid:events.append(entry)
    if not events or not all(re.fullmatch('[0-9a-f]{16}',e.get('span_id') or '') for e in events):
        raise RuntimeError('Correlated request log missing for '+service)
    if any(set(e)-{'timestamp','level','event','service','method','route','status','trace_id','span_id'} for e in events):
        raise RuntimeError('Unexpected fields in request log')
    print('APROBADO: log JSON de '+service+' comparte trace_id y tiene span_id válido.')
