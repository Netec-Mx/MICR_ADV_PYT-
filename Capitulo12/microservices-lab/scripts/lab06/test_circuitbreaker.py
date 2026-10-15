"""Dedicated chaos router, no rate limiter, backend marker distinguishes 500/503."""
import time
import httpx
from common import GATEWAY,token,headers,check
PATH='/api/v1/users/fail/simulate'
def test():
    with httpx.Client(base_url=GATEWAY,headers=headers(token()),timeout=5,trust_env=False) as h:
        # A previous run may still be recovering. Wait at most 15 s for a healthy backend response.
        deadline=time.monotonic()+15
        while True:
            r=h.get(PATH,params={'fail':'false'})
            if r.status_code==200 and r.headers.get('X-Lab-Backend')=='users-service':break
            check(r.status_code==503,'Router chaos ausente o respuesta inesperada')
            check(time.monotonic()<deadline,'Circuito no disponible antes de prueba');time.sleep(.2)
        saw_backend_error=False;saw_open=False
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            r=h.get(PATH,params={'fail':'true'})
            if r.status_code==500:
                check(r.headers.get('X-Lab-Backend')=='users-service','500 no proviene del backend')
                saw_backend_error=True
            elif r.status_code==503:
                check('X-Lab-Backend' not in r.headers,'503 ambiguo: tiene marcador backend')
                saw_open=True;break
            else:raise RuntimeError(f'Chaos: HTTP {r.status_code}; no se admite 429/401/403 como apertura')
            time.sleep(.12)
        check(saw_backend_error and saw_open,'No se demostró fallo backend y apertura edge')
        r=h.get(PATH,params={'fail':'false'})
        check(r.status_code==503 and 'X-Lab-Backend' not in r.headers,'No se bloqueó una respuesta backend saludable')
        check(h.get('/api/v1/products').status_code==200,'Circuito chaos afectó otro router')
        deadline=time.monotonic()+15;successes=0
        while time.monotonic()<deadline:
            r=h.get(PATH,params={'fail':'false'})
            check(r.status_code in [200,503],f'Recuperación inesperada: {r.status_code}')
            if r.status_code==200:
                check(r.headers.get('X-Lab-Backend')=='users-service','200 sin backend')
                successes+=1
                if successes>=5:break
            else:successes=0
            time.sleep(.2)
        check(successes>=5,'No hay recuperación estable')
        print('APROBADO circuit breaker: backend 500 -> edge 503 -> bloqueo de petición saludable -> recuperación 200.')
if __name__=='__main__':test()
