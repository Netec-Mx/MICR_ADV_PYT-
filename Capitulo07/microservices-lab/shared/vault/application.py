import asyncio
import secrets
from contextlib import asynccontextmanager
from fastapi import APIRouter,Depends,Header,HTTPException
from fastapi.responses import JSONResponse
from shared.auth import require_ops_admin
from shared.auth.token_client import ServiceAuthenticationError
from .client import VaultUnavailable

def current_admin_key(app, fallback):
    manager=getattr(app.state,'vault_manager',None)
    return manager.snapshot()['admin_key'] if manager else fallback

def install(app,manager):
    if getattr(app.state,'jwt_validator',None) is None:
        raise ValueError('Vault profile requires JWT authentication')
    app.state.vault_manager=manager
    original=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        await manager.start()
        try:
            async with original(application):yield
        finally:await manager.stop()
    app.router.lifespan_context=lifespan
    @app.exception_handler(VaultUnavailable)
    async def unavailable(request,exc):
        return JSONResponse(status_code=503,content={'code':'VAULT_CONFIGURATION_UNAVAILABLE'})
    @app.middleware('http')
    async def readiness(request,call_next):
        # Protect business requests too: a Ready pod check alone is insufficient.
        try:manager.snapshot()
        except VaultUnavailable:
            return JSONResponse(status_code=503,content={'code':'VAULT_CONFIGURATION_UNAVAILABLE'})
        return await call_next(request)
    prefix={'order-service':'orders','inventory-service':'products','users-service':'users'}[manager.role]
    router=APIRouter(prefix='/api/v1/'+prefix+'/config',tags=['Vault'],dependencies=[Depends(require_ops_admin)])
    @router.get('/status')
    async def status():return manager.status()
    @router.post('/refresh')
    async def refresh(admin:str|None=Header(None,alias='X-Admin-Key')):
        if not admin or not secrets.compare_digest(admin.encode(),manager.snapshot()['admin_key'].encode()):
            raise HTTPException(403,'Invalid admin key')
        try:await asyncio.to_thread(manager.refresh)
        except VaultUnavailable:raise HTTPException(503,'Vault refresh unavailable')
        return manager.status()
    # Register before /{id} routes so static config paths cannot be parsed as UUIDs.
    app.router.routes[0:0]=router.routes
    client=getattr(getattr(app.state,'inventory_client',None),'token_client',None)
    if client:
        def secret_provider():
            try:return manager.snapshot()['service_client_secret']
            except VaultUnavailable:raise ServiceAuthenticationError('Service credential unavailable') from None
        client.secret_provider=secret_provider
