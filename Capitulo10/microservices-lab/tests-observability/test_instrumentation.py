import asyncio
import io
import json
import logging
from uuid import uuid4
import pytest
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared.observability.application import install
from shared.observability.context import business_span,order_created
from shared.observability.logging import JsonFormatter

@pytest.mark.asyncio
async def test_red_metrics_and_business_counter_are_real():
    app=FastAPI()
    @app.post('/api/v1/orders')
    async def orders():
        with business_span('orders.persist'):order_created()
        return JSONResponse(status_code=201,content={'created':True})
    @app.get('/health')
    async def health():return {'ok':True}
    @app.get('/api/v1/users/fail')
    async def fail():return JSONResponse(status_code=500,content={'demo':True})
    exp=InMemorySpanExporter();obs=install(app,'order-service',exp)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
            assert (await h.post('/api/v1/orders')).status_code==201
            assert (await h.get('/api/v1/users/fail')).status_code==500
            await h.get('/health');metrics=(await h.get('/metrics')).text
            assert 'http_requests_total{handler="/api/v1/orders",method="POST",service="order-service",status="201"} 1.0' in metrics
            assert 'status="500"' in metrics and 'http_request_duration_seconds_bucket' in metrics and 'le="0.5"' in metrics
            assert 'business_orders_created_total{service="order-service"} 1.0' in metrics
            assert 'handler="/health"' not in metrics and 'handler="/metrics"' not in metrics
            await asyncio.to_thread(obs.provider.force_flush)
            assert any(s.name=='orders.persist' for s in exp.get_finished_spans())

@pytest.mark.asyncio
async def test_templates_bound_cardinality():
    app=FastAPI()
    @app.get('/api/v1/orders/{order_id}')
    async def get(order_id:str):return {'ok':True}
    exp=InMemorySpanExporter();install(app,'order-service',exp)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
            first=str(uuid4());second=str(uuid4())
            await h.get('/api/v1/orders/'+first);await h.get('/api/v1/orders/'+second)
            for path in ('/unknown-one','/unknown-two'):await h.get(path)
            metrics=(await h.get('/metrics')).text
            assert first not in metrics and second not in metrics and '/unknown-one' not in metrics
            assert 'handler="/api/v1/orders/{order_id}"' in metrics and 'status="404"' in metrics

@pytest.mark.asyncio
async def test_w3c_parent_and_log_correlation_without_credentials():
    app=FastAPI()
    @app.get('/api/v1/users')
    async def get():return {'ok':True}
    exp=InMemorySpanExporter();obs=install(app,'users-service',exp)
    captured=io.StringIO();handler=logging.StreamHandler(captured);handler.setFormatter(JsonFormatter());obs.logger.addHandler(handler)
    trace_id=uuid4().hex;parent='00f067aa0ba902b7'
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
                await h.get('/api/v1/users?token=private-query',headers={'traceparent':f'00-{trace_id}-{parent}-01','Authorization':'Bearer private-jwt','X-Admin-Key':'private-admin'})
                await asyncio.to_thread(obs.provider.force_flush)
                servers=[s for s in exp.get_finished_spans() if s.kind==trace.SpanKind.SERVER]
                assert servers and format(servers[0].context.trace_id,'032x')==trace_id and format(servers[0].parent.span_id,'016x')==parent
                event=json.loads(captured.getvalue());assert event['trace_id']==trace_id and event['span_id']==format(servers[0].context.span_id,'016x')
                assert 'private-' not in captured.getvalue()
                assert not any('authorization' in k.lower() or 'x_admin_key' in k.lower() for k in servers[0].attributes)
    finally:obs.logger.removeHandler(handler)

@pytest.mark.asyncio
async def test_multiple_factories_have_separate_registries_and_resources():
    apps=[]
    for name in ('order-service','inventory-service','users-service'):
        app=FastAPI();obs=install(app,name,InMemorySpanExporter());apps.append((app,obs))
        assert obs.provider.resource.attributes['service.name']==name
    assert len({id(o.registry) for _,o in apps})==3
    for app,obs in apps:await asyncio.to_thread(obs.provider.shutdown)

@pytest.mark.asyncio
async def test_install_is_idempotent():
    app=FastAPI();first=install(app,'users-service',InMemorySpanExporter());assert install(app,'users-service') is first
    await asyncio.to_thread(first.provider.shutdown)

@pytest.mark.asyncio
async def test_httpx_propagates_context_across_worker_thread():
    from types import SimpleNamespace
    from shared.observability.context import business_span
    seen=[]
    def remote(request):seen.append(request.headers.get('traceparent'));return httpx.Response(200,json={'ok':True})
    client=httpx.Client(transport=httpx.MockTransport(remote));app=FastAPI();app.state.inventory_client=SimpleNamespace(http=client)
    @app.get('/api/v1/orders/check-stock')
    async def get():
        with business_span('inventory.check'):await asyncio.to_thread(client.get,'http://inventory/api/v1/products/demo')
        return {'ok':True}
    exp=InMemorySpanExporter();obs=install(app,'order-service',exp);tid=uuid4().hex
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
                assert (await h.get('/api/v1/orders/check-stock',headers={'traceparent':f'00-{tid}-00f067aa0ba902b7-01'})).status_code==200
                assert seen and seen[0].split('-')[1]==tid
                await asyncio.to_thread(obs.provider.force_flush)
                assert any(s.kind==trace.SpanKind.CLIENT for s in exp.get_finished_spans())
    finally:client.close()

@pytest.mark.parametrize('version',['9.0.0','9.1.0'])
def test_telemetry_uses_deployed_release_version(monkeypatch,version):
    from shared.observability.application import Observation
    monkeypatch.setenv('APP_VERSION',version)
    obs=Observation('users-service',InMemorySpanExporter())
    try:assert obs.provider.resource.attributes['service.version']==version
    finally:obs.provider.shutdown()
