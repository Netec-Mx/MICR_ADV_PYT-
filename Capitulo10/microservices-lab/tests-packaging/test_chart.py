import json,os,shutil,subprocess
from pathlib import Path
import pytest,yaml
ROOT=Path(__file__).resolve().parents[1]
HELM=os.getenv('HELM_BIN','helm')
DIGEST='sha256:'+'a'*64
SERVICES={'order-service':8001,'inventory-service':8002,'users-service':8003}
@pytest.fixture(scope='module',autouse=True)
def helm_available():
    if not shutil.which(HELM):pytest.skip('Helm binary required')
def render(svc,*extra):
    return subprocess.run([HELM,'template',svc,str(ROOT/'helm/msvc-chart'),'-n','microservices','-f',str(ROOT/f'helm/values/{svc}.yaml'),'--set',f'image.digest={DIGEST}',*extra],capture_output=True,text=True)
@pytest.mark.parametrize('svc,port',SERVICES.items())
def test_chart_preserves_prior_identities_and_configuration(svc,port):
    result=render(svc);assert result.returncode==0,result.stderr
    objects=list(yaml.safe_load_all(result.stdout));assert len(objects)==4
    by_kind={o['kind']:o for o in objects};assert set(by_kind)=={'ServiceAccount','ConfigMap','Service','Deployment'}
    for o in objects:assert o['metadata']['namespace']=='microservices'
    d=by_kind['Deployment'];pod=d['spec']['template']['spec'];c=pod['containers'][0]
    prior=next(o for o in yaml.safe_load_all((ROOT/'k8s/lab08/50-apps.yaml').read_text()) if o['kind']=='Deployment' and o['metadata']['name']==svc)
    assert d['spec']['selector']==prior['spec']['selector'] # Immutable selector; no Helm instance label added.
    assert by_kind['Service']['spec']['selector']=={'app':svc}
    assert by_kind['Service']['spec']['ports'][0]['port']==port
    assert pod['serviceAccountName']==svc and not pod['automountServiceAccountToken']
    assert c['image']==f'localhost:5000/{svc}@{DIGEST}' and c['imagePullPolicy']=='Always'
    assert c['command']==['python','-m','shared.vault.launcher','--port',str(port)]
    env={v['name']:v for v in c['env']}
    for old in prior['spec']['template']['spec']['containers'][0]['env']:assert env[old['name']]==old
    assert pod['volumes'][0]['projected']['sources'][0]['serviceAccountToken']['audience']=='vault'
    assert pod['securityContext']['fsGroup']==c['securityContext']['runAsUser']==10001
    assert c['securityContext']['capabilities']['drop']==['ALL']
    assert not {'VAULT_TOKEN','EVENTSTORE_DATABASE_URL','ORDER_SERVICE_CLIENT_SECRET','EVENTSTORE_ADMIN_KEY'} & env.keys()
    # ConfigMap contains no operational secrets and excludes duplicated env values.
    assert by_kind['ConfigMap']['data']=={'APP_VERSION':'9.0.0','SERVICE_NAME':svc}
@pytest.mark.parametrize('args',[['--set','image.digest='],['--set','replicaCount=2'],['--set','env.AUTH_ENABLED=false'],['--set','env.VAULT_TOKEN=secret'],['--set','port=8003'],['--set','image.repository=localhost:5000/users-service']])
def test_invalid_or_unsafe_values_are_rejected(args):assert render('order-service',*args).returncode!=0
def test_namespace_must_match_vault_binding():assert render('order-service','-n','other').returncode!=0
def test_vault_role_must_match_identity():assert render('order-service','--set','env.VAULT_ROLE=users-service').returncode!=0
def test_config_checksum_changes_on_release_version():
    original=list(yaml.safe_load_all(render('users-service').stdout));updated=list(yaml.safe_load_all(render('users-service','--set-string','appVersion=9.1.0').stdout))
    get=lambda docs:next(o for o in docs if o['kind']=='Deployment')['spec']['template']['metadata']['annotations']['checksum/config']
    assert get(original)!=get(updated)
