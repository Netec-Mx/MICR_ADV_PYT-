from uuid import uuid4
import httpx,pytest
from shared.auth.token_client import ServiceTokenClient,ServiceAuthenticationError
from test_resilience import redis_namespace,make_client,response

@pytest.mark.asyncio
async def test_service_bearer_refresh_once_after_401(make_client):
    issued=[];seen=[]
    def issue(request):
        issued.append(1)
        return httpx.Response(200,json={'access_token':'token-'+str(len(issued)),'token_type':'Bearer','expires_in':300})
    provider=ServiceTokenClient('http://issuer/token','orders','secret',transport=httpx.MockTransport(issue))
    def handler(request):
        seen.append(request.headers.get('Authorization'))
        return httpx.Response(401) if len(seen)==1 else response(request)
    client=make_client(handler,token_client=provider)
    result=await client.check_stock(uuid4())
    assert result.available is True and result.attempts==2
    assert seen==['Bearer token-1','Bearer token-2'] and len(issued)==2

@pytest.mark.parametrize('status',[401,403])
@pytest.mark.asyncio
async def test_repeated_denial_does_not_trip_or_degrade(make_client,status):
    issued=[];seen=[]
    provider=ServiceTokenClient('http://issuer/token','orders','secret',transport=httpx.MockTransport(
        lambda request:(issued.append(1) or httpx.Response(200,json={'access_token':'token-'+str(len(issued)),'token_type':'Bearer','expires_in':300}))))
    def handler(request):seen.append(1);return httpx.Response(status)
    client=make_client(handler,token_client=provider,fail_max=1)
    with pytest.raises(ServiceAuthenticationError):await client.check_stock(uuid4())
    assert len(seen)==(2 if status==401 else 1)
    assert client.registry.status()['state']=='closed'

@pytest.mark.asyncio
async def test_token_acquisition_failure_never_sends_get(make_client):
    seen=[]
    provider=ServiceTokenClient('http://issuer/token','orders','secret',transport=httpx.MockTransport(lambda request:httpx.Response(401)))
    client=make_client(lambda request:(seen.append(1) or response(request)),token_client=provider)
    with pytest.raises(ServiceAuthenticationError):await client.check_stock(uuid4())
    assert not seen and client.bulkhead.active_calls==0
