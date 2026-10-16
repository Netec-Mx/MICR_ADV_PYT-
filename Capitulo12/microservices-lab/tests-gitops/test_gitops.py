import importlib.util,json,subprocess
from pathlib import Path
import pytest,yaml
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lab11gitops',ROOT/'scripts/lab11/gitops.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

@pytest.fixture
def repo(tmp_path):
    r=tmp_path/'repo';r.mkdir();remote=tmp_path/'remote.git'
    g.run('git','init','--bare',remote);g.git(r,'init','-b','main')
    g.git(r,'config','user.name','Test');g.git(r,'config','user.email','test@example.invalid')
    v=yaml.safe_load((ROOT/'helm/msvc-chart/values.yaml').read_text());v['image']['digest']='sha256:'+'a'*64
    (r/g.VALUES).parent.mkdir(parents=True);g.save(r,v)
    g.git(r,'add','.');g.git(r,'commit','-m','baseline');g.git(r,'remote','add','origin',remote);g.git(r,'push','-u','origin','main')
    return r

def promote(repo,monkeypatch):
    monkeypatch.setattr(g,'render',lambda repo:'valid')
    monkeypatch.setattr(g,'smoke',lambda repo:None)
    return g.update(repo,'ghcr.io/demo/lab11-order-service','sha256:'+'b'*64,'11.0.0','f'*40)

def test_promotion_and_git_revert_restore_previous_digest(repo,monkeypatch):
    sha=promote(repo,monkeypatch)
    assert g.values(repo)['image']['digest']=='sha256:'+'b'*64
    restored=g.revert(repo,sha)
    assert restored!=sha and g.values(repo)['image']['digest']=='sha256:'+'a'*64
    assert g.git(repo,'rev-parse','origin/main')==restored

def test_revert_refuses_concurrent_remote_update(repo,tmp_path,monkeypatch):
    sha=promote(repo,monkeypatch);other=tmp_path/'other';g.run('git','clone','--branch','main',str(repo.parent/'remote.git'),other)
    g.git(other,'config','user.name','Other');g.git(other,'config','user.email','other@example.invalid');(other/'README.md').write_text('later work')
    g.git(other,'add','.');g.git(other,'commit','-m','later');g.git(other,'push')
    with pytest.raises(ValueError,match='Concurrent'):g.revert(repo,sha)
    assert g.values(repo)['image']['digest']=='sha256:'+'b'*64

def test_revert_refuses_unrelated_file_changes(repo,monkeypatch):
    monkeypatch.setattr(g,'render',lambda repo:'valid');(repo/'other').write_text('unrelated')
    g.git(repo,'add','.');g.git(repo,'commit','-m','unrelated');g.git(repo,'push')
    with pytest.raises(ValueError,match='single values'):g.revert(repo,g.git(repo,'rev-parse','HEAD'))

@pytest.mark.parametrize('image,digest,version,source',[('localhost:5000/order-service','sha256:'+'b'*64,'11.0.0','a'*40),('ghcr.io/demo/lab11-order-service','latest','11.0.0','a'*40),('ghcr.io/demo/lab11-order-service','sha256:'+'b'*64,'bad','a'*40),('ghcr.io/demo/lab11-order-service','sha256:'+'b'*64,'11.0.0','a'*7)])
def test_promotion_rejects_nonimmutable_or_invalid_metadata(repo,image,digest,version,source):
    with pytest.raises(ValueError):g.update(repo,image,digest,version,source)

def test_update_rejects_dirty_repository(repo,monkeypatch):
    (repo/'dirty').write_text('x')
    with pytest.raises(ValueError,match='clean'):promote(repo,monkeypatch)

@pytest.mark.parametrize('sync,health,revision,expected',[('Synced','Healthy','a',True),('Synced','Healthy','b',False),('OutOfSync','Healthy','a',False),('Synced','Degraded','a',False)])
def test_wait_requires_exact_revision_and_both_statuses(sync,health,revision,expected):
    assert g.healthy({'status':{'sync':{'status':sync,'revision':revision},'health':{'status':health}}},'a') is expected

def test_failure_watch_automatically_reverts_then_reports_failure(repo,monkeypatch):
    sha=promote(repo,monkeypatch);answers=iter([False,True]);monkeypatch.setattr(g,'wait',lambda *a:next(answers))
    with pytest.raises(RuntimeError,match='automatic Git revert'):g.watch(repo,sha,1)
    assert g.values(repo)['image']['digest']=='sha256:'+'a'*64

def test_healthy_watch_does_not_revert(repo,monkeypatch):
    sha=promote(repo,monkeypatch);monkeypatch.setattr(g,'wait',lambda *a:True)
    g.watch(repo,sha,1);assert g.git(repo,'rev-parse','HEAD')==sha

def test_workflow_keeps_gates_before_publication_and_uses_image_artifact():
    w=yaml.load((ROOT/'.github/workflows/lab11-ci-cd.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'push','pull_request','workflow_dispatch'}
    assert w['jobs']['publish']['needs']=='quality'
    quality=w['jobs']['quality']['steps'];publish=w['jobs']['publish']['steps']
    text='\n'.join(s.get('run','') for s in quality)
    assert '--exit-code 1' in text and '--ignore-unfixed' not in text
    assert 'docker push' not in text
    assert "github.event_name != 'pull_request'" in w['jobs']['publish']['if']
    assert any('docker load' in s.get('run','') for s in publish)
    assert not any('kubectl' in s.get('run','') for s in publish)
    for stage in [quality,publish]:
        for s in stage:
            if 'uses' in s:assert len(s['uses'].split('@')[1])==40


def test_smoke_failure_reverts_even_when_readiness_is_healthy(repo,monkeypatch):
    sha=promote(repo,monkeypatch);monkeypatch.setattr(g,'wait',lambda *a:True)
    def fail(repo):raise subprocess.CalledProcessError(1,['smoke'])
    monkeypatch.setattr(g,'smoke',fail)
    with pytest.raises(g.DeploymentRecovered):g.watch(repo,sha,1)
    assert g.values(repo)['image']['digest']=='sha256:'+'a'*64

def test_failed_recovery_is_not_reported_as_healthy(repo,monkeypatch):
    sha=promote(repo,monkeypatch);monkeypatch.setattr(g,'wait',lambda *a:False)
    with pytest.raises(RuntimeError,match='recovery is not healthy') as error:g.watch(repo,sha,1)
    assert not isinstance(error.value,g.DeploymentRecovered)

def test_prepare_preserves_vault_and_variant_registry_and_scopes_argo(tmp_path,monkeypatch):
    import shutil,os
    helm=os.environ.get('HELM_BIN','helm')
    import shutil as sh
    if not sh.which(helm):pytest.skip('Helm required for real prepare render')
    monkeypatch.setenv('PATH',str(Path(helm).resolve().parent)+os.pathsep+os.environ['PATH'])
    report=tmp_path/'reports';report.mkdir();monkeypatch.setattr(g,'REPORT',report)
    schema=Path(os.environ.get('KUBERNETES_SCHEMA_CACHE',ROOT/'reports/lab11/kubernetes-1.35.8.json'))
    if schema.exists():shutil.copy(schema,report/'kubernetes-1.35.8.json')
    v=yaml.safe_load((ROOT/'helm/msvc-chart/values.yaml').read_text())
    v['env']=yaml.safe_load((ROOT/'helm/values/order-service.yaml').read_text())['env']
    v['image']['digest']='sha256:'+'a'*64;v['mesh'].update(enabled=True,variant='v1')
    v['mesh']['extra'].update(enabled=True,digest='sha256:'+'b'*64)
    original=g.run
    def run(*args,**kwargs):
        if args[0]=='helm' and 'status' in args:return json.dumps({'info':{'status':'deployed'},'version':4})
        if args[0]=='helm' and 'get' in args and 'values' in args:return yaml.safe_dump(v)
        return original(*args,**kwargs)
    monkeypatch.setattr(g,'run',run)
    for key,value in {'GIT_AUTHOR_NAME':'Test','GIT_AUTHOR_EMAIL':'test@example.invalid','GIT_COMMITTER_NAME':'Test','GIT_COMMITTER_EMAIL':'test@example.invalid'}.items():monkeypatch.setenv(key,value)
    url='https://github.com/demo/ms-gitops-repo.git';repo=tmp_path/'prepared'
    g.prepare(repo,url)
    current=g.values(repo)
    assert current['env']==v['env'] and current['replicaCount']==2
    assert current['mesh']['extra']['repository']=='localhost:5000/order-service'
    assert yaml.safe_load((report/'before-values.yaml').read_text())['replicaCount']==1
    project,app=list(yaml.safe_load_all((report/'argo.yaml').read_text()))
    assert 'finalizers' not in app['metadata'] and not app['spec']['syncPolicy']['automated']['prune']
    assert app['spec']['source']['helm']['releaseName']=='order-service'
    assert project['spec']['sourceRepos']==[url] and project['spec']['destinations'][0]['namespace']=='microservices'
    assert g.git(repo,'status','--porcelain')==''
