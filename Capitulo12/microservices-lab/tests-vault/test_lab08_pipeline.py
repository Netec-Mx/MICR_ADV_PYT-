"""Actual binaries and HTTP/OTLP; host substitutions do not simulate Kubernetes."""
import os
import json
import time
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4
import pytest
import yaml
import httpx
import test_stack

@pytest.fixture
def observability_stack(tmp_path):
    tools=os.getenv('OBS_TEST_TOOLS')
    if not tools:pytest.skip('Set OBS_TEST_TOOLS to directory with real backend binaries')
    if not Path('/proc/'+str(os.getpid())+'/stat').exists():
        pytest.skip('Complete backend test requires procfs process entries and Unix IPC')
    tools=Path(tools);root=Path(__file__).resolve().parents[1]
    files=root/'observability/chart/files';config=tmp_path/'configs';config.mkdir()
    jaeger=yaml.safe_load((files/'jaeger.yaml').read_text());jaeger['receivers']['otlp']['protocols']['grpc']['endpoint']='127.0.0.1:14317';jaeger['receivers']['otlp']['protocols']['http']['endpoint']='127.0.0.1:14318';jaeger['extensions']['healthcheckv2']['http']['endpoint']='127.0.0.1:13134';jaeger['service']['telemetry']={'metrics':{'level':'none'}}
    collector=yaml.safe_load((files/'collector.yaml').read_text());collector['receivers']['otlp']['protocols']['grpc']['endpoint']='127.0.0.1:14319';collector['receivers']['otlp']['protocols']['http']['endpoint']='127.0.0.1:14320';collector['exporters']['otlp/jaeger']['endpoint']='127.0.0.1:14317';collector['extensions']['health_check']['endpoint']='127.0.0.1:13135';collector['service']['telemetry']={'metrics':{'level':'none'}}
    prom=yaml.safe_load((files/'prometheus.yaml').read_text());prom['global']={'scrape_interval':'500ms','evaluation_interval':'500ms'};prom['rule_files']=[str(files/'rules.yaml')];prom['scrape_configs'][0]['scrape_timeout']='250ms';prom['alerting']['alertmanagers'][0]['static_configs'][0]['targets']=['127.0.0.1:19093']
    for target,port in zip(prom['scrape_configs'][0]['static_configs'],[19001,19002,19003]):target['targets']=[f'127.0.0.1:{port}']
    for name,data in [('jaeger',jaeger),('collector',collector),('prometheus',prom)]:
        (config/(name+'.yaml')).write_text(yaml.safe_dump(data,sort_keys=False))
    processes=[]
    def start(cmd,name,env=None):
        log=open(tmp_path/(name+'.log'),'w');p=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT);processes.append((p,log))
    try:
        start([str(tools/'jaeger/jaeger-2.22.0-linux-amd64/jaeger'),'--config='+str(config/'jaeger.yaml')],'jaeger')
        start([str(tools/'collector/otelcol-contrib'),'--config='+str(config/'collector.yaml')],'collector')
        start([str(tools/'alertmanager/alertmanager-0.34.1.linux-amd64/alertmanager'),'--config.file='+str(files/'alertmanager.yaml'),'--storage.path='+str(tmp_path/'amdata'),'--web.listen-address=127.0.0.1:19093','--cluster.listen-address='],'alertmanager')
        start([str(tools/'prometheus/prometheus-3.15.0.linux-amd64/prometheus'),'--config.file='+str(config/'prometheus.yaml'),'--storage.tsdb.path='+str(tmp_path/'promdata'),'--web.listen-address=127.0.0.1:19090'],'prometheus')
        # Provision Grafana using the delivered files, with only host URL/path substitutions.
        provision=tmp_path/'provisioning';(provision/'datasources').mkdir(parents=True);(provision/'dashboards').mkdir()
        dashboard=tmp_path/'dashboards';dashboard.mkdir();shutil.copyfile(files/'dashboard.json',dashboard/'red.json')
        ds=yaml.safe_load((files/'grafana-datasources.yaml').read_text());ds['datasources'][0]['url']='http://127.0.0.1:19090';ds['datasources'][1]['url']='http://127.0.0.1:16686'
        provider=yaml.safe_load((files/'grafana-providers.yaml').read_text());provider['providers'][0]['options']['path']=str(dashboard)
        (provision/'datasources/lab.yaml').write_text(yaml.safe_dump(ds));(provision/'dashboards/lab.yaml').write_text(yaml.safe_dump(provider))
        env={**os.environ,'GF_PATHS_DATA':str(tmp_path/'grafdata'),'GF_PATHS_LOGS':str(tmp_path/'graflogs'),'GF_PATHS_PROVISIONING':str(provision),'GF_SERVER_HTTP_ADDR':'127.0.0.1','GF_SERVER_HTTP_PORT':'13000','GF_SECURITY_ADMIN_USER':'admin','GF_SECURITY_ADMIN_PASSWORD':'lab08-grafana-demo','GF_ANALYTICS_REPORTING_ENABLED':'false','GF_ANALYTICS_CHECK_FOR_UPDATES':'false','GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES':'false','GF_PLUGINS_PREINSTALL_DISABLED':'true','GF_LOG_LEVEL':'warn'}
        start([str(tools/'grafana/usr/share/grafana/bin/grafana'),'server','--homepath='+str(tools/'grafana/usr/share/grafana')],'grafana',env)
        with httpx.Client(timeout=2,trust_env=False) as h:
            for url in ['http://127.0.0.1:13134/status','http://127.0.0.1:13135/','http://127.0.0.1:19093/-/ready','http://127.0.0.1:19090/-/ready','http://127.0.0.1:13000/api/health']:
                for _ in range(300):
                    if any(p.poll() is not None for p,_ in processes):
                        logs='\n'.join((tmp_path/(name+'.log')).read_text() for name in ['jaeger','collector','prometheus','alertmanager','grafana'])
                        if 'failed to register process metrics: process does not exist' in logs:
                            pytest.skip('Collector/Jaeger runtime requires process metrics unavailable in this sandbox')
                        raise RuntimeError('An observability backend exited during startup')
                    try:
                        if h.get(url).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.1)
                else:raise RuntimeError('Observability backend startup failed: '+url)
        yield {'config':config,'prometheus':processes[3][0]}
    finally:
        for p,log in processes:p.terminate()
        for p,log in processes:p.wait(timeout=20);log.close()

@pytest.mark.asyncio
async def test_real_vault_business_otlp_trace_metrics_logs_and_dashboard(manager_factory,vault,tmp_path,observability_stack,monkeypatch):
    tid=uuid4().hex;monkeypatch.setenv('LAB08_TEST_PROM_WAIT','true');monkeypatch.setenv('LAB08_TRACE_ID',tid);monkeypatch.setenv('OBSERVABILITY_ENABLED','true');monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT','http://127.0.0.1:14319')
    await test_stack.test_three_launchers_preserve_business_and_rotate_keys(manager_factory,vault,tmp_path)
    with httpx.Client(timeout=5,trust_env=False) as h:
        for _ in range(50):
            r=h.get('http://127.0.0.1:16686/api/traces/'+tid)
            if r.status_code==200 and r.json().get('data'):break
            time.sleep(.1)
        else:raise AssertionError('Trace not found in real Jaeger')
        t=r.json()['data'][0];spans=t['spans'];processes=t['processes']
        assert {'order-service','inventory-service'} <= {p['serviceName'] for p in processes.values()}
        assert {'orders.persist','inventory.check'} <= {s['operationName'] for s in spans}
        clients={s['spanID'] for s in spans if processes[s['processID']]['serviceName']=='order-service' and any(tag['key']=='span.kind' and tag['value']=='client' for tag in s.get('tags',[]))}
        assert any(processes[s['processID']]['serviceName']=='inventory-service' and any(ref.get('spanID') in clients for ref in s.get('references',[])) for s in spans)
        for query in ['sum by(service)(rate(http_requests_total{job="microservices"}[5m]))','lab:http_error_ratio:5m','lab:http_latency_p99:5m']:
            data=h.get('http://127.0.0.1:19090/api/v1/query',params={'query':query}).json()
            assert data['status']=='success' and data['data']['result'],query
        ds=h.get('http://127.0.0.1:13000/api/datasources',auth=('admin','lab08-grafana-demo'));ds.raise_for_status();assert {d['uid'] for d in ds.json()}=={'prometheus','jaeger'}
        dashboard=h.get('http://127.0.0.1:13000/api/dashboards/uid/lab08-red',auth=('admin','lab08-grafana-demo'));dashboard.raise_for_status();assert len(dashboard.json()['dashboard']['panels'])==3
        # Transport test uses a separate temporary rule, preserving the real 2m/5m SLO durations.
        path=observability_stack['config']/'prometheus.yaml';p=yaml.safe_load(path.read_text());demo=observability_stack['config']/'demo.yaml';demo.write_text(yaml.safe_dump({'groups':[{'name':'test','rules':[{'alert':'Lab08PipelineTest','expr':'vector(1)','labels':{'service':'lab08-demo'}}]}]}));p['rule_files'].append(str(demo));path.write_text(yaml.safe_dump(p))
        # Prometheus test process uses SIGHUP for reload (no lifecycle admin endpoint needed).
        import signal
        observability_stack['prometheus'].send_signal(signal.SIGHUP)
        for _ in range(100):
            alerts=h.get('http://127.0.0.1:19093/api/v2/alerts').json()
            if any(a['labels'].get('alertname')=='Lab08PipelineTest' for a in alerts):break
            time.sleep(.1)
        else:raise AssertionError('Prometheus alert did not reach real Alertmanager')
    for name in ['order-service','inventory-service']:
        events=[]
        for line in (tmp_path/(name+'.log')).read_text().splitlines():
            if line.startswith('{'):
                e=json.loads(line)
                if e.get('event')=='http_request_completed' and e.get('trace_id')==tid:events.append(e)
        assert events and all(e.get('span_id') for e in events)
        assert 'order-svc-secret-lab' not in json.dumps(events) and 'initial-order-service' not in json.dumps(events)
