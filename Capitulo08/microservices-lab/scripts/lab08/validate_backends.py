import math
import time
import httpx
from common import PROMETHEUS,GRAFANA,ALERTMANAGER,check

with httpx.Client(timeout=10,trust_env=False) as h:
    deadline=time.monotonic()+75
    while time.monotonic()<deadline:
        targets=h.get(PROMETHEUS+'/api/v1/targets');targets.raise_for_status();active=targets.json()['data']['activeTargets']
        services={t['labels'].get('service') for t in active if t['labels'].get('job')=='microservices' and t['health']=='up'}
        if services=={'order-service','inventory-service','users-service'}:break
        time.sleep(3)
    else:raise RuntimeError('Not all three metrics targets are healthy')
    for metric in ('lab:http_request_rate:5m','lab:http_error_ratio:5m','lab:http_latency_p99:5m'):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            r=h.get(PROMETHEUS+'/api/v1/query',params={'query':metric});r.raise_for_status();data=r.json()
            check(data['status']=='success','Prometheus query failed')
            result=data['data']['result']
            if {v['metric'].get('service') for v in result}==services and all(math.isfinite(float(v['value'][1])) for v in result):break
            time.sleep(3)
        else:raise RuntimeError('RED query missing a service or producing NaN: '+metric)
    rules=h.get(PROMETHEUS+'/api/v1/rules',params={'type':'alert'}).json()['data']['groups']
    names={r['name'] for g in rules for r in g['rules']}
    check({'HighLatencyP99','HighErrorRate','MicroserviceMetricsUnavailable'}<=names,'Missing rules')
    h.get(ALERTMANAGER+'/-/ready').raise_for_status()
    auth=('admin','lab08-grafana-demo')
    ds=h.get(GRAFANA+'/api/datasources',auth=auth);ds.raise_for_status();check({d['uid'] for d in ds.json()}=={'prometheus','jaeger'},'Grafana sources differ')
    dashboard=h.get(GRAFANA+'/api/dashboards/uid/lab08-red',auth=auth);dashboard.raise_for_status();check(len(dashboard.json()['dashboard']['panels'])==3,'Missing RED panels')
print('APROBADO: tres targets UP, consultas RED finitas, reglas y dashboard con datasources provisionados.')
