"""Real HTTP chaos scenarios. Nonzero exit on any unmet condition.

Use ONLY with the chaos overlay (mock :8003); real Inventory remains :8002.
The script deliberately does not create orders against synthetic mock stock.
"""
import asyncio,os
from uuid import uuid4
import httpx

ORDER=os.getenv('CHAOS_ORDER_URL','http://localhost:8001')
MOCK=os.getenv('CHAOS_MOCK_URL','http://localhost:8003')
KEY=os.getenv('EVENTSTORE_ADMIN_KEY','lab-admin-key')

def check(condition,message):
    if not condition:raise RuntimeError(message)

async def main():
    async with httpx.AsyncClient(timeout=60,trust_env=False) as client:
        async def request(method,url,**kwargs):
            response=await client.request(method,url,**kwargs)
            check(response.status_code==200,f'{method} {url}: {response.status_code} {response.text}')
            return response.json()
        async def observe():return await request('GET',ORDER+'/health/circuit-breakers')
        async def stats():return await request('GET',MOCK+'/admin/stats')
        async def idle():
            for _ in range(100):
                if (await stats())['active']==0:return
                await asyncio.sleep(.05)
            raise RuntimeError('Mock still has active requests')
        async def config(**kwargs):
            await idle()
            return await request('POST',MOCK+'/admin/config',json=kwargs)
        async def reset():
            return await request('POST',ORDER+'/health/circuit-breakers/inventory-service/reset',
                                 headers={'X-Admin-Key':KEY})
        async def stock():
            return await request('GET',ORDER+'/api/v1/orders/check-stock/'+str(uuid4()))
        status=await observe();breaker=status['circuit_breakers']['inventory-service']
        check(':chaos:' in breaker['namespace'],'Use chaos namespace; refusing to alter normal circuit')
        threshold=breaker['fail_max'];cooldown=breaker['reset_timeout']
        slots=status['bulkheads']['inventory-service']['max_concurrent']
        check(threshold==3 and slots==3 and cooldown==3,'Use the supplied chaos configuration (3/3/3)')

        await reset();await config()
        result=await stock()
        check(result['available'] is True and result['quantity']==100 and result['attempts']==1,'Normal stock failed')
        print('APROBADO: operación normal')

        await config(fail_first=2)
        result=await stock()
        check(result['available'] is True and result['attempts']==3,'Retry did not recover on attempt 3')
        check((await stats())['total_requests']==3,'Unexpected retry count')
        print('APROBADO: dos errores transitorios y recuperación en intento 3')

        await config(status_code=503)
        for _ in range(threshold):
            result=await stock()
            check(result['available'] is None and result['quantity'] is None,'Fallback invented stock')
        status=await observe()
        check(status['circuit_breakers']['inventory-service']['state']=='open','Circuit did not open')
        before=(await stats())['total_requests']
        result=await stock()
        check(result['reason']=='circuit_open' and result['attempts']==0,'Open circuit attempted HTTP')
        check((await stats())['total_requests']==before==threshold*3,'Circuit/retry counts incorrect')
        print('APROBADO: apertura y rechazo sin HTTP adicional')

        await config()
        await asyncio.sleep(cooldown+1)
        result=await stock();status=await observe()
        transitions=status['circuit_breakers']['inventory-service']['transitions']
        check(result['available'] is True and status['circuit_breakers']['inventory-service']['state']=='closed','Recovery failed')
        check({'from':'open','to':'half-open'} in transitions and {'from':'half-open','to':'closed'} in transitions,'Missing actual half-open transition')
        print('APROBADO: recuperación automática half-open, sin reset manual')

        await reset();await config(latency_seconds=.8)
        result=await stock()
        check(result['available'] is None and result['attempts']==3,'Read timeout did not retry/degrade')
        await idle()
        print('APROBADO: timeout real HTTP y fallback desconocido')

        await reset();await config(status_code=404)
        result=await stock()
        check(result['available'] is False and result['quantity']==0 and result['attempts']==1,'404 incorrectly retried')
        check((await observe())['circuit_breakers']['inventory-service']['fail_counter']==0,'404 counted as system failure')
        print('APROBADO: 404 sin retry ni fallo del circuito')

        await reset();await config(latency_seconds=.2)
        results=await asyncio.gather(*[stock() for _ in range(slots+6)])
        rejected=sum(result['reason']=='bulkhead_full' for result in results)
        check(rejected>=6,'Bulkhead did not reject excess jobs')
        status=await observe();bulkhead=status['bulkheads']['inventory-service']
        check(bulkhead['active_calls']==0 and bulkhead['peak_active']<=slots,'Bulkhead slots leaked')
        check(all(result['available'] is True or result['reason']=='bulkhead_full' for result in results),'Unexpected burst outcome')
        print('APROBADO: bulkhead saturado, rechazos y liberación de slots')
        await config();await reset()
        print('LABORATORIO 4: 7 ESCENARIOS HTTP DE CAOS APROBADOS')

if __name__=='__main__':asyncio.run(main())
