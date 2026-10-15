"""Reads JSONL from stdin. Emits only identity, operation, path and decision."""
import json
import sys
from collections import Counter
counts=Counter();requests={}
for number,line in enumerate(sys.stdin,1):
    if not line.strip():continue
    try:event=json.loads(line)
    except json.JSONDecodeError:raise SystemExit(f'Invalid audit JSON at line {number}')
    request=event.get('request',{});rid=request.get('id')
    if event.get('type')=='request':
        metadata=(event.get('auth') or {}).get('metadata') or {}
        requests[rid]=(metadata.get('service_account_name','operator-or-unknown'),request.get('operation'),request.get('path'))
    elif event.get('type')=='response':
        who,operation,path=requests.pop(rid,('operator-or-unknown',request.get('operation'),request.get('path')))
        counts[(who,operation,path,'denied-or-error' if event.get('error') else 'allowed')]+=1
for (who,operation,path,decision),count in sorted(counts.items(),key=str):
    print(f'{who} | {operation} | {path} | {decision} | {count}')
print(f'Unpaired requests: {len(requests)}')
