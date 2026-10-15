import json,os,time,math,httpx
from common import ROOT
PROM=os.getenv('PROMETHEUS_URL','http://localhost:9090');GRAF=os.getenv('GRAFANA_URL','http://localhost:3000')

def query(h,q):
    d=h.get(PROM+'/api/v1/query',params={'query':q}).raise_for_status().json()
    assert d['status']=='success';return d['data']['result']
def main():
    with httpx.Client(timeout=10,trust_env=False) as h:
        targets=h.get(PROM+'/api/v1/targets').raise_for_status().json()['data']['activeTargets']
        targets=[t for t in targets if t['labels'].get('job')=='microservices']
        assert len(targets)==5 and all(t['health']=='up' for t in targets),targets
        # Counters establish actual traffic, require both variants, and prove mTLS on application HTTP.
        samples=query(h,'sum by (destination_canonical_service,destination_version,connection_security_policy) (istio_requests_total{reporter="destination",response_code="200"})')
        found={(s['metric'].get('destination_canonical_service'),s['metric'].get('destination_version')) for s in samples if s['metric'].get('connection_security_policy')=='mutual_tls' and float(s['value'][1])>0}
        expected={('order-service','v1'),('order-service','v2'),('inventory-service','blue'),('inventory-service','green')}
        assert expected<=found,found
        # Generate traffic for >=30s before running this check so rate windows have samples.
        dashboard=json.loads((ROOT/'observability/chart/files/dashboard-mesh.json').read_text())
        measurements=[]
        for panel in dashboard['panels']:
            result=query(h,panel['targets'][0]['expr'])
            assert result and all(math.isfinite(float(s['value'][1])) for s in result),panel['title']
            measurements.append({'panel':panel['title'],'series':len(result)})
        dash=h.get(GRAF+'/api/dashboards/uid/lab10-mesh',auth=('admin',os.getenv('GRAFANA_PASSWORD','lab08-grafana-demo'))).raise_for_status().json()
        assert len(dash['dashboard']['panels'])==5
        report={'targets':len(targets),'mtls_versions':[list(v) for v in sorted(found)],'panels':measurements}
        (ROOT/'reports/lab10/observability.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
