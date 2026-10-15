"""Authenticated, read-only traffic. Never treat errors or missing headers as variant success."""
import argparse,json,time,math
from collections import Counter
import httpx
from common import token,GATEWAY,HOST,ROOT

def check_distribution(counts,n,v2_percent):
    assert n>=200,'At least 200 requests required'
    assert sum(counts.values())==n and set(counts)<= {'v1','v2'},counts
    p=v2_percent/100;observed=counts.get('v2',0)/n
    if p in (0,1):assert observed==p,(counts,p)
    else:
        # Four standard deviations plus a small convergence allowance, not an exact quota.
        tolerance=max(.04,4*math.sqrt(p*(1-p)/n))
        assert abs(observed-p)<=tolerance,(counts,p,tolerance)
        assert counts.get('v1',0)>0 and counts.get('v2',0)>0,counts
    return observed

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['canary','bluegreen','warmup']);parser.add_argument('--v2-percent',type=int,choices=[0,10,50,100],default=10);parser.add_argument('--requests',type=int,default=400);parser.add_argument('--seconds',type=int,default=45);a=parser.parse_args()
    access=token(admin=True);counts=Counter();records=[]
    with httpx.Client(base_url=GATEWAY,timeout=15,trust_env=False) as h:
        def call(path,extra=None):
            hs={'Host':HOST,'Authorization':'Bearer '+access,'Connection':'close'};hs.update(extra or {})
            resp=h.get(path,headers=hs);assert resp.status_code==200,(resp.status_code,resp.text[:200])
            resp.json();variant=resp.headers.get('X-Lab-Variant');version=resp.headers.get('X-Lab-Version')
            assert variant and version,'Real application identity headers missing'
            assert version==('10.1.0' if variant in ('v2','green') else '10.0.0'),(variant,version)
            return variant
        if a.mode=='warmup':
            assert 30<=a.seconds<=120
            start=time.monotonic()
            while time.monotonic()-start<a.seconds:
                if time.monotonic()-start>50:access=token(admin=True)
                call('/api/v1/orders');call('/api/v1/products',{'x-version':'green'});call('/api/v1/products');call('/api/v1/users')
                time.sleep(.25)
            report={'duration_seconds':a.seconds,'purpose':'Seed both Orders variants and both Inventory variants over multiple scrape intervals'}
        elif a.mode=='canary':
            for index in range(a.requests):
                if index and index%100==0:access=token(admin=True)
                counts[call('/api/v1/orders')]+=1
            observed=check_distribution(counts,a.requests,a.v2_percent)
            report={'expected_v2_percent':a.v2_percent,'requests':a.requests,'counts':dict(counts),'observed_v2_percent':100*observed}
        else:
            for header,expected in [(None,'blue'),('blue','blue'),('green','green'),('unknown','blue')]:
                for _ in range(10):
                    actual=call('/api/v1/products',{'x-version':header} if header else None)
                    assert actual==expected,(header,actual,expected)
                records.append({'header':header,'expected':expected,'verified':10})
            report={'cases':records}
    out=ROOT/'reports/lab10'/f'{a.mode}-{a.v2_percent if a.mode=="canary" else "headers"}.json'
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
