"""Real SDK OTLP export, app traffic, Prometheus and Alertmanager; receiver is a test double."""
import json
import os
import time
import signal
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
import yaml
import httpx
import grpc
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceServicer,add_TraceServiceServicer_to_server
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
import test_stack

@pytest.mark.asyncio
async def test_exported_otlp_red_and_alert_transport(manager_factory,vault,tmp_path,monkeypatch):
    tools=os.getenv('OBS_TEST_TOOLS')
    if not tools:pytest.skip('Set OBS_TEST_TOOLS for real Prometheus/Alertmanager binaries')
    tools=Path(tools);root=Path(__file__).resolve().parents[1];files=root/'observability/chart/files'
    batches=[]
    class Receiver(TraceServiceServicer):
        def Export(self,request,context):batches.append(request);return ExportTraceServiceResponse()
    server=grpc.server(ThreadPoolExecutor(max_workers=2));add_TraceServiceServicer_to_server(Receiver(),server);assert server.add_insecure_port('127.0.0.1:14319');server.start()
    prom=yaml.safe_load((files/'prometheus.yaml').read_text());prom['global']={'scrape_interval':'500ms','evaluation_interval':'500ms'};prom['rule_files']=[str(files/'rules.yaml')];prom['scrape_configs'][0]['scrape_timeout']='250ms';prom['alerting']['alertmanagers'][0]['static_configs'][0]['targets']=['127.0.0.1:19093']
    for target,port in zip(prom['scrape_configs'][0]['static_configs'],[19001,19002,19003]):target['targets']=[f'127.0.0.1:{port}']
    config=tmp_path/'prom.yaml';config.write_text(yaml.safe_dump(prom));processes=[]
    def start(cmd,name):
        log=open(tmp_path/(name+'.log'),'w');p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT);processes.append((p,log));return p
    try:
        start([str(tools/'alertmanager/alertmanager-0.34.1.linux-amd64/alertmanager'),'--config.file='+str(files/'alertmanager.yaml'),'--storage.path='+str(tmp_path/'amdata'),'--web.listen-address=127.0.0.1:19093','--cluster.listen-address='],'am')
        pp=start([str(tools/'prometheus/prometheus-3.15.0.linux-amd64/prometheus'),'--config.file='+str(config),'--storage.tsdb.path='+str(tmp_path/'promdata'),'--web.listen-address=127.0.0.1:19090'],'prom')
        with httpx.Client(timeout=5,trust_env=False) as h:
            for url in ('http://127.0.0.1:19090/-/ready','http://127.0.0.1:19093/-/ready'):
                for _ in range(100):
                    try:
                        if h.get(url).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.1)
                else:raise RuntimeError('Prometheus/Alertmanager failed')
        tid=uuid4().hex;monkeypatch.setenv('LAB08_TEST_PROM_WAIT','true');monkeypatch.setenv('LAB08_TRACE_ID',tid);monkeypatch.setenv('OBSERVABILITY_ENABLED','true');monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT','http://127.0.0.1:14319')
        await test_stack.test_three_launchers_preserve_business_and_rotate_keys(manager_factory,vault,tmp_path)
        spans=[]
        for batch in batches:
            for rs in batch.resource_spans:
                service=next(a.value.string_value for a in rs.resource.attributes if a.key=='service.name')
                for scope in rs.scope_spans:
                    for span in scope.spans:
                        if span.trace_id.hex()==tid:spans.append((service,span))
        assert {'order-service','inventory-service'}<={service for service,_ in spans}
        assert {'orders.persist','inventory.check'}<={span.name for _,span in spans}
        clients={span.span_id for service,span in spans if service=='order-service' and span.kind==3}
        assert any(service=='inventory-service' and span.kind==2 and span.parent_span_id in clients for service,span in spans)
        with httpx.Client(timeout=5,trust_env=False) as h:
            for query in ('lab:http_request_rate:5m','lab:http_error_ratio:5m','lab:http_latency_p99:5m'):
                d=h.get('http://127.0.0.1:19090/api/v1/query',params={'query':query}).json();assert d['status']=='success' and d['data']['result'],query
            demo=tmp_path/'demo.yaml';demo.write_text(yaml.safe_dump({'groups':[{'name':'demo','rules':[{'alert':'Lab08PipelineTest','expr':'vector(1)','labels':{'service':'lab08-demo'}}]}]}));prom['rule_files'].append(str(demo));config.write_text(yaml.safe_dump(prom));pp.send_signal(signal.SIGHUP)
            for _ in range(100):
                alerts=h.get('http://127.0.0.1:19093/api/v2/alerts').json()
                if any(a['labels'].get('alertname')=='Lab08PipelineTest' for a in alerts):break
                time.sleep(.1)
            else:raise AssertionError('Real Prometheus alert missing from Alertmanager')
        for name in ('order-service','inventory-service'):
            events=[json.loads(line) for line in (tmp_path/(name+'.log')).read_text().splitlines() if line.startswith('{')]
            events=[e for e in events if e.get('trace_id')==tid and e.get('event')=='http_request_completed'];assert events and all(e.get('span_id') for e in events)
    finally:
        for p,log in processes:p.terminate()
        for p,log in processes:p.wait(timeout=20);log.close()
        server.stop(0).wait()
