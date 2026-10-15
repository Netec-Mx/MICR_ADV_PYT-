import pytest,httpx
from fastapi import FastAPI,HTTPException
from shared.mesh.application import install,VariantHeaderMiddleware
@pytest.mark.asyncio
@pytest.mark.parametrize('variant,version',[('v1','10.0.0'),('v2','10.1.0'),('blue','10.0.0'),('green','10.1.0'),('stable','10.0.0')])
async def test_server_identity_headers_do_not_change_business_or_authorization(monkeypatch,variant,version):
    monkeypatch.setenv('LAB10_VARIANT',variant);monkeypatch.setenv('APP_VERSION',version)
    app=FastAPI()
    @app.get('/business')
    async def business():return {'id':'same-contract','total':'20.00'}
    @app.get('/protected')
    async def protected():raise HTTPException(status_code=401,detail='Not authenticated')
    install(app);install(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as h:
        response=await h.get('/business',headers={'X-Lab-Variant':'forged'})
        assert response.json()=={'id':'same-contract','total':'20.00'}
        assert response.headers['X-Lab-Variant']==variant and response.headers['X-Lab-Version']==version
        assert (await h.get('/protected')).status_code==401
@pytest.mark.parametrize('variant,version',[('invalid','10.0.0'),('v1','secret\nheader')])
def test_invalid_metadata_rejected(variant,version):
    with pytest.raises(ValueError):VariantHeaderMiddleware(None,variant,version)
