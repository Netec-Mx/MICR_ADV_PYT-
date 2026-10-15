"""Burst test with bounded parallelism, real errors and nonzero failure exit."""
import asyncio,collections,time
import httpx
from common import GATEWAY,token,headers,check
async def test():
    hs=headers(token());gate=asyncio.Semaphore(20)
    start=time.monotonic()
    async with httpx.AsyncClient(base_url=GATEWAY,headers=hs,timeout=5,trust_env=False) as h:
        async def call():
            async with gate:return (await h.get('/api/v1/users')).status_code
        results=collections.Counter(await asyncio.gather(*[call() for _ in range(80)]))
        duration=time.monotonic()-start
        check(set(results)<={200,429},f'Respuestas inesperadas: {dict(results)}')
        check(results[200]>0 and results[429]>0,f'Faltan éxitos o rechazo: {dict(results)}')
        check((await h.get('/api/v1/products')).status_code==200,'Límite Users afectó Inventory')
        await asyncio.sleep(2)
        check((await h.get('/api/v1/users')).status_code==200,'Bucket no se repone')
        print(f'APROBADO rate limiting: {dict(results)}; duración {duration:.2f}s; aislamiento y reposición comprobados.')
if __name__=='__main__':asyncio.run(test())
