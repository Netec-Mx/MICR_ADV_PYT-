#!/usr/bin/env python3
import json,time
from gitops import k
before=json.loads(k('-n','microservices','get','deployment','order-service','-o','json'))
assert before['spec']['replicas']==2,'Desired baseline must have two replicas'
k('-n','microservices','scale','deployment/order-service','--replicas=3')
end=time.monotonic()+240
while time.monotonic()<end:
    d=json.loads(k('-n','microservices','get','deployment','order-service','-o','json'))
    if d['spec']['replicas']==2 and d['status'].get('observedGeneration',0)>=d['metadata']['generation'] and d['status'].get('readyReplicas')==2:
        print('Self-healing verified: desired + ready replicas restored to 2');break
    time.sleep(5)
else:raise RuntimeError('Self-healing did not restore the desired state')
