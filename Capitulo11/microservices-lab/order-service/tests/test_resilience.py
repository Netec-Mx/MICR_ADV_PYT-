import asyncio,os,time,threading
from uuid import uuid4
import httpx,pytest,pytest_asyncio,redis
from tenacity import wait_random_exponential
from app.clients.inventory_client import InventoryClient
from shared.resilience.retry_policies import retry_policy,TransientInventoryError
from shared.resilience import BulkheadSemaphore,BulkheadFullError,CircuitBreakerRegistry

@pytest.fixture
def redis_namespace():
    url=os.getenv('REDIS_TEST_URL')
    if not url:pytest.skip('Define REDIS_TEST_URL para probar el estado real del circuito')
    connection=redis.Redis.from_url(url)
    connection.ping()
    namespace='lab04:test:'+uuid4().hex
    yield url,namespace
    keys=list(connection.scan_iter(match=namespace+':*'))
    if keys:connection.delete(*keys)
    connection.close()

@pytest_asyncio.fixture
async def make_client(redis_namespace):
    url,namespace=redis_namespace
    clients=[]
    def factory(handler,**kwargs):
        client=InventoryClient(redis_url=url,namespace=namespace,
             transport=httpx.MockTransport(handler),retry_multiplier=0,retry_max_wait=0,**kwargs)
        clients.append(client);return client
    yield factory
    for client in clients:await client.close()

def response(request,stock=10):
    return httpx.Response(200,json={'id':request.url.path.split('/')[-1],'stock_quantity':stock})

@pytest.mark.asyncio
async def test_reads_actual_inventory_route_and_quantity(make_client):
    paths=[]
    def handler(request):paths.append(request.url.path);return response(request,12)
    client=make_client(handler)
    product_id=uuid4();result=await client.check_stock(product_id)
    assert result.quantity==12 and result.available is True and result.attempts==1
    assert paths==[f'/api/v1/products/{product_id}']

@pytest.mark.asyncio
async def test_two_transient_failures_then_success(make_client):
    attempts=[]
    def handler(request):
        attempts.append(1)
        return httpx.Response(503) if len(attempts)<3 else response(request)
    client=make_client(handler)
    result=await client.check_stock(uuid4())
    assert result.available is True and result.attempts==3
    assert client.registry.status()['fail_counter']==0

@pytest.mark.parametrize('status',[408,429,500,502,503,504])
@pytest.mark.asyncio
async def test_transient_response_retries_three_times(make_client,status):
    client=make_client(lambda request:httpx.Response(status))
    result=await client.check_stock(uuid4())
    assert result.available is None and result.quantity is None and result.attempts==3
    assert client.registry.status()['fail_counter']==1

@pytest.mark.parametrize('status',[400,401,403,404,422,501])
@pytest.mark.asyncio
async def test_non_retryable_response_attempted_once(make_client,status):
    client=make_client(lambda request:httpx.Response(status))
    result=await client.check_stock(uuid4())
    assert result.attempts==1
    if status==404:
        assert result.available is False and result.quantity==0
        assert client.registry.status()['fail_counter']==0
    else:assert result.available is None and result.reason=='invalid_upstream_response'

@pytest.mark.parametrize('body',[{'stock_quantity':-1},{'stock_quantity':'10'},{'quantity':10}])
@pytest.mark.asyncio
async def test_invalid_body_is_unknown_not_available(make_client,body):
    def handler(request):return httpx.Response(200,json={'id':request.url.path.split('/')[-1],**body})
    result=await make_client(handler).check_stock(uuid4())
    assert result.available is None and result.quantity is None and result.attempts==1

@pytest.mark.asyncio
async def test_timeouts_are_retried(make_client):
    def handler(request):raise httpx.ReadTimeout('injected',request=request)
    result=await make_client(handler).check_stock(uuid4())
    assert result.attempts==3 and result.reason=='upstream_unavailable'

@pytest.mark.asyncio
async def test_breaker_counts_logical_failures_and_blocks_http(make_client):
    calls=[]
    client=make_client(lambda request:(calls.append(1) or httpx.Response(503)),fail_max=3,reset_timeout=10)
    for _ in range(3):await client.check_stock(uuid4())
    state=client.registry.status()
    assert state['state']=='open' and state['fail_counter']==3 and len(calls)==9
    result=await client.check_stock(uuid4())
    assert result.reason=='circuit_open' and result.attempts==0 and len(calls)==9

@pytest.mark.asyncio
async def test_recovers_via_half_open_without_manual_reset(make_client):
    healthy=False
    client=make_client(lambda request:response(request) if healthy else httpx.Response(503),fail_max=1,reset_timeout=1)
    await client.check_stock(uuid4())
    assert client.registry.status()['state']=='open'
    healthy=True
    await asyncio.sleep(1.1)
    result=await client.check_stock(uuid4())
    state=client.registry.status()
    assert result.available is True and state['state']=='closed' and state['fail_counter']==0
    assert {'from':'open','to':'half-open'} in state['transitions']
    assert {'from':'half-open','to':'closed'} in state['transitions']

@pytest.mark.asyncio
async def test_failed_half_open_probe_reopens(make_client):
    client=make_client(lambda request:httpx.Response(503),fail_max=1,reset_timeout=1)
    await client.check_stock(uuid4());await asyncio.sleep(1.1)
    result=await client.check_stock(uuid4())
    state=client.registry.status()
    assert result.available is None and state['state']=='open'
    assert {'from':'half-open','to':'open'} in state['transitions']

@pytest.mark.asyncio
async def test_state_survives_new_client_with_same_namespace(make_client):
    first=make_client(lambda request:httpx.Response(503),fail_max=1,reset_timeout=10)
    await first.check_stock(uuid4());await first.close()
    second=make_client(lambda request:response(request),fail_max=1,reset_timeout=10)
    result=await second.check_stock(uuid4())
    assert result.attempts==0 and second.registry.status()['state']=='open'
    await second.reset()
    assert (await second.check_stock(uuid4())).available is True

@pytest.mark.asyncio
async def test_cancelled_caller_keeps_worker_slot_and_event_loop_runs(make_client):
    entered=threading.Event();finish=threading.Event()
    def handler(request):entered.set();finish.wait(3);return response(request)
    client=make_client(handler,max_concurrent=1,acquire_timeout=.03)
    task=asyncio.create_task(client.check_stock(uuid4()))
    for _ in range(100):
        if entered.is_set():break
        await asyncio.sleep(.01)
    assert entered.is_set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert client.bulkhead.active_calls==1
    assert (await client.check_stock(uuid4())).reason=='bulkhead_full'
    finish.set()
    await client.close()
    assert client.bulkhead.active_calls==0

@pytest.mark.asyncio
async def test_burst_rejects_jobs_and_releases_all_slots(make_client):
    def handler(request):time.sleep(.15);return response(request)
    client=make_client(handler,max_concurrent=2,acquire_timeout=.02)
    results=await asyncio.gather(*[client.check_stock(uuid4()) for _ in range(8)])
    assert sum(result.reason=='bulkhead_full' for result in results)==6
    assert client.bulkhead.stats['peak_active']==2 and client.bulkhead.active_calls==0

@pytest.mark.asyncio
async def test_redis_outage_returns_explicit_unknown():
    calls=[]
    client=InventoryClient(redis_url='redis://127.0.0.1:1/1',
        transport=httpx.MockTransport(lambda request:(calls.append(1) or response(request))))
    try:
        result=await client.check_stock(uuid4())
        assert result.reason=='resilience_storage_unavailable' and result.available is None
        assert result.attempts==0 and not calls
    finally:await client.close()

@pytest.mark.asyncio
async def test_programming_error_is_not_hidden(make_client):
    def handler(request):raise RuntimeError('programming bug')
    client=make_client(handler)
    with pytest.raises(RuntimeError,match='programming bug'):await client.check_stock(uuid4())
    assert client.bulkhead.active_calls==0

def test_exponential_jitter_bounds_without_wall_clock_flakiness():
    policy=retry_policy(attempts=3,multiplier=.1,max_wait=.5,sleep=lambda seconds:waits.append(seconds))
    waits=[];calls=[]
    def failing():calls.append(1);raise TransientInventoryError()
    with pytest.raises(TransientInventoryError):policy(failing)
    assert len(calls)==3 and len(waits)==2
    assert 0<=waits[0]<=.1 and 0<=waits[1]<=.2

@pytest.mark.asyncio
async def test_bulkhead_acquisition_cancellation_does_not_leak():
    bulkhead=BulkheadSemaphore('test',1,1)
    await bulkhead.acquire()
    task=asyncio.create_task(bulkhead.acquire());await asyncio.sleep(.01);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    bulkhead.release()
    await bulkhead.acquire();bulkhead.release()
    assert bulkhead.active_calls==0
