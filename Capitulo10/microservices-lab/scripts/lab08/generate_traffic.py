import argparse
import time
import httpx
from common import token,headers,GATEWAY

def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=30);p.add_argument('--fault',action='store_true');p.add_argument('--users-url',default='http://localhost:8003');a=p.parse_args()
    if not 1<=a.seconds<=600:p.error('Use 1..600 seconds')
    start=time.monotonic();next_refresh=0;access=None;calls=0
    with httpx.Client(timeout=10,trust_env=False) as h:
        while time.monotonic()-start<a.seconds:
            if time.monotonic()>=next_refresh:access=token(admin=True);next_refresh=time.monotonic()+60
            hs=headers(access)
            if a.fault:
                # Direct authenticated backend test avoids the Gateway's circuit/rate policy.
                r=h.get(a.users_url+'/api/v1/users/observability/probe',headers=hs,params={'delay_ms':750,'fail':'true' if calls%5==0 else 'false'})
                expected=500 if calls%5==0 else 200
                if r.status_code!=expected:raise RuntimeError('Unexpected probe status')
            else:
                for path in ('orders','products','users'):
                    r=h.get(GATEWAY+'/api/v1/'+path,headers=hs);r.raise_for_status()
            calls+=1;time.sleep(1)
    print('Traffic completed:',calls,'cycles; controlled fault' if a.fault else 'healthy gateway traffic')

if __name__=='__main__':main()
