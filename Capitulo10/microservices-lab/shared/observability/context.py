from contextvars import ContextVar
from contextlib import contextmanager
from opentelemetry.trace import Status,StatusCode
active_observability=ContextVar('active_observability',default=None)

@contextmanager
def business_span(name,**attributes):
    observation=active_observability.get()
    if observation is None:
        yield None;return
    with observation.tracer.start_as_current_span(name,record_exception=False,set_status_on_exception=False,attributes=attributes) as span:
        try:yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute('error.type',type(exc).__name__)
            raise

def order_created():
    observation=active_observability.get()
    if observation:observation.orders.inc()
