import httpx,pytest
from app.cqrs_app import create_cqrs_app

@pytest.mark.asyncio
async def test_release_uses_configured_version_without_uuid_route_collision(monkeypatch):
    monkeypatch.setenv('APP_VERSION','11.1.0')
    app=create_cqrs_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get('/api/v1/orders/release')
        assert r.status_code==200 and r.json()=={'service':'order-service','version':'11.1.0'}
    await app.state.store.engine.dispose()

@pytest.mark.asyncio
async def test_release_requires_jwt_in_course_mode(monkeypatch):
    monkeypatch.setenv('AUTH_ISSUER','http://localhost:18081/realms/microservices-lab')
    monkeypatch.setenv('AUTH_JWKS_URL','http://localhost:18081/realms/microservices-lab/protocol/openid-connect/certs')
    app=create_cqrs_app(auth=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get('/api/v1/orders/release')
        assert r.status_code==401
    await app.state.jwt_validator.close();await app.state.store.engine.dispose()
