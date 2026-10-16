import json,time,yaml
from common import k,ROOT
# Use an existing pinned app image with Python, bypassing its application entrypoint.
PROGRAM=r"""
import urllib.request,urllib.error,http.client,socket,json
health='http://users-service.microservices.svc.cluster.local:8003/health'
control='http://keycloak.microservices.svc.cluster.local:8080/realms/microservices-lab/.well-known/openid-configuration'
assert urllib.request.urlopen(control,timeout=10).status==200
socket.getaddrinfo('users-service.microservices.svc.cluster.local',8003)
try:
 r=urllib.request.urlopen(health,timeout=10)
 print(json.dumps({'status':r.status,'transport_error':None}),flush=True)
except (urllib.error.URLError,ConnectionResetError,http.client.RemoteDisconnected,BrokenPipeError) as e:
 reason=getattr(e,'reason',e)
 print(json.dumps({'status':None,'transport_error':type(reason).__name__}),flush=True)
"""
def probe(name,mesh,image):
    pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'microservices','labels':{'sidecar.istio.io/inject':'true' if mesh else 'false'}},
        'spec':{'serviceAccountName':'lab10-probe','automountServiceAccountToken':False,'restartPolicy':'Never','containers':[{'name':'probe','image':image,'imagePullPolicy':'Always','command':['python','-c',PROGRAM]}]}}
    if mesh:pod['metadata']['annotations']={'proxy.istio.io/config':'{"holdApplicationUntilProxyStarts":true}'}
    # Regular sidecars keep a Job/Pod alive; wait for application termination, not Pod Succeeded.
    import subprocess
    subprocess.run(['kubectl','--context',__import__('common').CONTEXT,'apply','-f','-'],input=yaml.safe_dump(pod),text=True,check=True)
    for _ in range(90):
        p=json.loads(k('-n','microservices','get','pod',name,'-o','json'))
        cs=next((s for s in p.get('status',{}).get('containerStatuses',[]) if s['name']=='probe'),{})
        finished=cs.get('state',{}).get('terminated')
        if finished:
            assert finished['exitCode']==0,k('-n','microservices','logs',name,'-c','probe')
            return json.loads(k('-n','microservices','logs',name,'-c','probe').strip().splitlines()[-1])
        time.sleep(2)
    raise AssertionError('Probe startup/termination timeout, not proof of mTLS')
def main():
    import subprocess
    from common import CONTEXT
    image='localhost:5000/users-service@'+yaml.safe_load((ROOT/'reports/lab09/10.0.0/users-service-image.yaml').read_text())['image']['digest']
    sa={'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'lab10-probe','namespace':'microservices'},'automountServiceAccountToken':False}
    subprocess.run(['kubectl','--context',CONTEXT,'apply','-f','-'],input=yaml.safe_dump(sa),text=True,check=True)
    names=['lab10-plaintext-probe','lab10-mesh-probe']
    try:
        plain=probe(names[0],False,image);secure=probe(names[1],True,image)
        assert plain['status'] is None and plain['transport_error'] in ('ConnectionResetError','RemoteDisconnected','BrokenPipeError'),plain
        assert secure['status']==200 and secure['transport_error'] is None,secure
        report={'plaintext':plain,'mesh':secure,'control':'Keycloak plaintext reachable and destination DNS resolved in both probes'}
        (ROOT/'reports/lab10/mtls-probes.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
    finally:
        for name in names:k('-n','microservices','delete','pod',name,'--ignore-not-found=true','--wait=false')
        k('-n','microservices','delete','sa','lab10-probe','--ignore-not-found=true')
if __name__=='__main__':main()
