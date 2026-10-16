"""Fault injection only; port 8003, never replaces real Inventory/Kafka consumer."""
import asyncio
from uuid import UUID
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel,ConfigDict,Field

class MockConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    status_code:int=Field(200,ge=200,le=599)
    latency_seconds:float=Field(0,ge=0,le=5)
    fail_first:int=Field(0,ge=0,le=100)
    stock_quantity:int=Field(100,ge=0)
    malformed:bool=False

app=FastAPI(title='Inventory fault injector')
config=MockConfig()
request_count=active=peak_active=0

@app.get('/health')
async def health():return {'status':'healthy','service':'inventory-mock'}

@app.post('/admin/config')
async def configure(new:MockConfig):
    global config,request_count,peak_active
    if active:raise HTTPException(409,'Wait for active mock calls to finish')
    config=new;request_count=peak_active=0
    return config.model_dump()

@app.get('/admin/stats')
async def stats():return {'total_requests':request_count,'active':active,'peak_active':peak_active}

@app.get('/api/v1/products/{product_id}')
async def product(product_id:UUID):
    global request_count,active,peak_active
    request_count+=1;index=request_count
    local=config.model_copy()
    active+=1;peak_active=max(peak_active,active)
    try:
        if local.latency_seconds:await asyncio.sleep(local.latency_seconds)
        status=503 if index<=local.fail_first else local.status_code
        if status!=200:raise HTTPException(status,'Injected fault')
        if local.malformed:return {'id':str(product_id),'stock_quantity':-1}
        return {'id':str(product_id),'stock_quantity':local.stock_quantity}
    finally:active-=1
