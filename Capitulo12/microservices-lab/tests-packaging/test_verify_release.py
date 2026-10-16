import copy,json
from pathlib import Path
import pytest,yaml
import verify_release as verifier
DIGEST='sha256:'+'a'*64
@pytest.fixture
def fake_cluster(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    p=Path('reports/lab09/9.1.0');p.mkdir(parents=True)
    (p/'users-service-image.yaml').write_text(yaml.safe_dump({'image':{'digest':DIGEST}}))
    values={'image':{'repository':'localhost:5000/users-service','digest':DIGEST},'appVersion':'9.1.0','replicaCount':1}
    image=values['image']['repository']+'@'+DIGEST
    deployment={'metadata':{'generation':2},'spec':{'template':{'spec':{'containers':[{'image':image}]}}},'status':{'observedGeneration':2}}
    pods=[{'metadata':{'name':'users-one'},'spec':{'containers':[{'image':image}]},'status':{'conditions':[{'type':'Ready','status':'True'}],'containerStatuses':[{'ready':True,'imageID':'containerd://sha256:config-digest'}]}}]
    runtime={'uid':10001,'version':'9.1.0'}
    status={'info':{'status':'deployed'}}
    def run(*args):
        if 'values' in args:return json.dumps(values)
        if 'status' in args:return json.dumps(status)
        raise AssertionError(args)
    def kube(*args):
        if args[0]=='exec':return json.dumps(runtime)
        if args[:2]==('get','deployment'):return json.dumps(deployment)
        if args[:2]==('get','pods'):return json.dumps({'items':pods})
        raise AssertionError(args)
    monkeypatch.setattr(verifier,'run',run);monkeypatch.setattr(verifier,'kube',kube)
    return values,deployment,pods,runtime,status

def test_published_digest_and_running_version_verified(fake_cluster):
    result=verifier.verify('users-service','9.1.0')
    assert result['digest']==DIGEST and result['pods']==['users-one']
@pytest.mark.parametrize('failure',['wrong_digest','not_ready','wrong_uid','wrong_version','unobserved','failed_release'])
def test_incomplete_or_wrong_deployment_cannot_pass(fake_cluster,failure):
    values,deployment,pods,runtime,status=fake_cluster
    if failure=='wrong_digest':values['image']['digest']='sha256:'+'b'*64
    elif failure=='not_ready':pods[0]['status']['conditions'][0]['status']='False'
    elif failure=='wrong_uid':runtime['uid']=0
    elif failure=='wrong_version':runtime['version']='9.0.0'
    elif failure=='unobserved':deployment['status']['observedGeneration']=1
    else:status['info']['status']='failed'
    with pytest.raises(AssertionError):verifier.verify('users-service','9.1.0')
