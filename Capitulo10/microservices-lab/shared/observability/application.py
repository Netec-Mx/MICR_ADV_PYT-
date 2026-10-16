import asyncio
import os
import socket
from contextlib import asynccontextmanager
from prometheus_client import CollectorRegistry,Counter,Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased,ALWAYS_ON
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from .logging import RequestLogMiddleware,request_logger

BUCKETS=(.005,.01,.025,.05,.1,.25,.5,.75,1,2.5,5,10)

class Observation:
    def __init__(self,service,exporter=None):
        self.service=service
        self.registry=CollectorRegistry()
        self.requests=Counter('http_requests_total','HTTP requests excluding health and metrics',
            ['service','method','handler','status'],registry=self.registry)
        self.duration=Histogram('http_request_duration_seconds','HTTP request duration',
            ['service','method','handler'],buckets=BUCKETS,registry=self.registry)
        self.orders=Counter('business_orders_created_total','Orders successfully committed',
            ['service'],registry=self.registry).labels(service)
        resource=Resource.create({'service.name':service,'service.version':os.getenv('APP_VERSION','8.0.0'),
            'service.instance.id':os.getenv('POD_NAME',socket.gethostname()),'deployment.environment.name':'lab'})
        self.provider=TracerProvider(resource=resource,sampler=ParentBased(ALWAYS_ON))
        exporter=exporter if exporter is not None else OTLPSpanExporter(
            endpoint=os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'],insecure=True,timeout=2)
        self.provider.add_span_processor(BatchSpanProcessor(exporter,max_queue_size=2048,
            max_export_batch_size=256,schedule_delay_millis=1000,export_timeout_millis=3000))
        self.tracer=self.provider.get_tracer('microservices.lab08');self.logger=request_logger(service)

    def metric(self,info):
        labels=(self.service,info.method,info.modified_handler,info.modified_status)
        self.requests.labels(*labels).inc()
        self.duration.labels(*labels[:3]).observe(info.modified_duration)

def install(app,service,exporter=None):
    if hasattr(app.state,'observability'):return app.state.observability
    observation=Observation(service,exporter);app.state.observability=observation
    Instrumentator(registry=observation.registry,should_group_status_codes=False,
        should_ignore_untemplated=False,excluded_handlers=['^/metrics$','^/health(?:/.*)?$']).add(observation.metric).instrument(app).expose(app,include_in_schema=False)
    app.add_middleware(RequestLogMiddleware,observation=observation)
    # Only W3C TraceContext; no arbitrary baggage/header/body collection.
    set_global_textmap(TraceContextTextMapPropagator())
    FastAPIInstrumentor.instrument_app(app,tracer_provider=observation.provider,
        excluded_urls='.*?/health(?:/.*)?$,.*?/metrics$',
        http_capture_headers_server_request=[],http_capture_headers_server_response=[],
        http_capture_headers_sanitize_fields=['.*'])
    http=getattr(getattr(app.state,'inventory_client',None),'http',None)
    if http is not None:HTTPXClientInstrumentor.instrument_client(http,tracer_provider=observation.provider)
    original=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original(application):yield
        finally:
            if http is not None:HTTPXClientInstrumentor.uninstrument_client(http)
            await asyncio.to_thread(observation.provider.shutdown)
    app.router.lifespan_context=lifespan
    return observation
