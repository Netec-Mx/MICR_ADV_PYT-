"""Dedicated request logger: no bodies, credentials, query strings or exceptions."""
import json
import logging
import sys
from datetime import datetime,timezone
from opentelemetry import trace
from .context import active_observability

class JsonFormatter(logging.Formatter):
    def format(self,record):
        context=trace.get_current_span().get_span_context()
        return json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),
            'level':record.levelname,'event':'http_request_completed','service':record.service,
            'method':record.method,'route':record.route,'status':record.status,
            'trace_id':format(context.trace_id,'032x') if context.is_valid else None,
            'span_id':format(context.span_id,'016x') if context.is_valid else None},ensure_ascii=False)

def request_logger(service):
    logger=logging.getLogger('lab.requests.'+service)
    if not logger.handlers:
        handler=logging.StreamHandler(sys.stdout);handler.setFormatter(JsonFormatter());logger.addHandler(handler)
    logger.propagate=False;logger.setLevel(logging.INFO)
    return logger

class RequestLogMiddleware:
    def __init__(self,app,observation):self.app=app;self.observation=observation
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['path'] in ('/health','/metrics'):
            return await self.app(scope,receive,send)
        token=active_observability.set(self.observation);status=500
        async def capture(message):
            nonlocal status
            if message['type']=='http.response.start':status=message['status']
            await send(message)
        try:await self.app(scope,receive,capture)
        finally:
            route=scope.get('route')
            self.observation.logger.info('request',extra={'service':self.observation.service,
                'method':scope['method'],'route':getattr(route,'path','unmatched'),'status':status})
            active_observability.reset(token)
