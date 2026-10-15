#!/usr/bin/env python3
"""Small GitOps commands; deployment authority remains with Argo CD."""
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'reports/lab11'
CONTEXT=os.getenv('KUBE_CONTEXT','msvc-gateway')
VALUES=Path('charts/order-service/values.yaml')
def run(*args,cwd=None):return subprocess.check_output([str(a) for a in args],cwd=cwd,text=True).strip()
def k(*args):return run('kubectl','--context',CONTEXT,*args)
def git(repo,*args):return run('git','-C',repo,*args)
def values(repo):return yaml.safe_load((Path(repo)/VALUES).read_text())
def save(repo,v):(Path(repo)/VALUES).write_text(yaml.safe_dump(v,sort_keys=False))
def render(repo):
    chart=Path(repo)/'charts/order-service'
    run('helm','lint',chart)
    out=run('helm','template','order-service',chart,'-n','microservices')
    REPORT.mkdir(parents=True,exist_ok=True);p=REPORT/'rendered.yaml';p.write_text(out+'\n')
    run(os.sys.executable,ROOT/'scripts/lab11/validate-render.py',p,REPORT/'kubernetes-1.35.8.json')
    return out

def prepare(repo,url):
    if not re.fullmatch(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?',url):raise ValueError('Use a credential-free GitHub HTTPS URL')
    repo=Path(repo).resolve();repo.mkdir(parents=True,exist_ok=True)
    if any(repo.iterdir()):raise ValueError('Use an empty destination; refusing overwrite or reinitialization')
    before=json.loads(run('helm','--kube-context',CONTEXT,'status','order-service','-n','microservices','-o','json'))
    if before['info']['status']!='deployed':raise ValueError('Lab10 Orders release must be deployed')
    v=yaml.safe_load(run('helm','--kube-context',CONTEXT,'get','values','order-service','-n','microservices','--all','-o','yaml'))
    if not v['mesh']['enabled'] or not v['mesh']['extra']['enabled']:raise ValueError('Complete Lab10 first')
    forbidden={'VAULT_TOKEN','EVENTSTORE_DATABASE_URL','EVENTSTORE_ADMIN_KEY','ORDER_SERVICE_CLIENT_SECRET'}
    if forbidden & v['env'].keys():raise ValueError('Secrets must stay in Vault')
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'before-values.yaml').write_text(yaml.safe_dump(v,sort_keys=False))
    (REPORT/'before-release.json').write_text(json.dumps(before,indent=2))
    # Keep v2 at its original registry when v1 moves to GHCR.
    v['mesh']['extra']['repository']=v['image']['repository'];v['replicaCount']=2
    v['imagePullSecrets']=[{'name':'lab11-ghcr-pull'}]
    shutil.copytree(ROOT/'helm/msvc-chart',repo/'charts/order-service');save(repo,v);render(repo)
    git(repo,'init','-b','main');git(repo,'add','charts');git(repo,'commit','-m','chore: adopt existing Lab10 Orders configuration')
    git(repo,'remote','add','origin',url)
    project={'apiVersion':'argoproj.io/v1alpha1','kind':'AppProject','metadata':{'name':'lab11','namespace':'argocd'},'spec':{'sourceRepos':[url],'destinations':[{'server':'https://kubernetes.default.svc','namespace':'microservices'}],'clusterResourceWhitelist':[],'namespaceResourceWhitelist':[{'group':'','kind':x} for x in ['Service','ConfigMap','ServiceAccount']]+[{'group':'apps','kind':'Deployment'}]}}
    app={'apiVersion':'argoproj.io/v1alpha1','kind':'Application','metadata':{'name':'lab11-orders','namespace':'argocd'},'spec':{'project':'lab11','source':{'repoURL':url,'targetRevision':'main','path':'charts/order-service','helm':{'releaseName':'order-service'}},'destination':{'server':'https://kubernetes.default.svc','namespace':'microservices'},'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True,'allowEmpty':False},'retry':{'limit':3,'backoff':{'duration':'5s','factor':2,'maxDuration':'1m'}}}}}
    (REPORT/'argo.yaml').write_text(yaml.safe_dump_all([project,app],sort_keys=False))
    print('Prepared. Push main, configure repository credentials if private, then apply reports/lab11/argo.yaml.')

def update(repo,image,digest,version,source_sha):
    if not re.fullmatch(r'ghcr.io/[a-z0-9][a-z0-9-]*/lab11-order-service',image):raise ValueError('Invalid GHCR image')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Invalid digest')
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid version')
    if not re.fullmatch(r'[a-f0-9]{40}',source_sha):raise ValueError('Full application commit SHA required')
    if git(repo,'status','--porcelain'):raise ValueError('GitOps worktree must be clean')
    v=values(repo);v['image']['repository']=image;v['image']['digest']=digest;v['appVersion']=version
    save(repo,v);render(repo)
    if not git(repo,'diff','--',VALUES):return git(repo,'rev-parse','HEAD')
    git(repo,'add',VALUES);git(repo,'commit','-m',f'chore: deploy Orders {version}\n\nApplication-SHA: {source_sha}')
    git(repo,'push','origin','HEAD:main');return git(repo,'rev-parse','HEAD')

def healthy(app,sha):
    s=app.get('status',{})
    return s.get('sync',{}).get('revision')==sha and s.get('sync',{}).get('status')=='Synced' and s.get('health',{}).get('status')=='Healthy'

def wait(sha,timeout=900):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app=json.loads(k('-n','argocd','get','application','lab11-orders','-o','json'))
        if healthy(app,sha):return True
        time.sleep(5)
    return False

def revert(repo,sha):
    # No force-push and no reversal of someone else's later deployment.
    if git(repo,'status','--porcelain'):raise ValueError('Dirty GitOps worktree')
    git(repo,'fetch','origin','main')
    if git(repo,'rev-parse','origin/main')!=sha or git(repo,'rev-parse','HEAD')!=sha:raise ValueError('Concurrent GitOps change: automatic revert refused')
    parent=git(repo,'rev-parse',sha+'^')
    changed=git(repo,'diff','--name-only',parent,sha).splitlines()
    if changed!=[str(VALUES)]:raise ValueError('Automatic revert accepts only a single values change')
    git(repo,'revert','--no-edit',sha);render(repo);git(repo,'push','origin','HEAD:main')
    return git(repo,'rev-parse','HEAD')

def smoke(repo):
    run(os.sys.executable,ROOT/'scripts/lab11/smoke.py',repo)

class DeploymentRecovered(RuntimeError):pass

def watch(repo,sha,timeout):
    if wait(sha,timeout):
        try:
            smoke(repo);print('Synced + Healthy + authenticated smoke at intended Git SHA');return
        except subprocess.CalledProcessError:
            print('Application readiness passed but authenticated smoke failed; reverting Git')
    restored=revert(repo,sha)
    if not wait(restored,timeout):raise RuntimeError('Git reverted but recovery is not healthy: investigate')
    raise DeploymentRecovered('Deployment failed; automatic Git revert restored the previous configuration')

def monitor(repo):
    # Start only at an already healthy baseline. Keep this observer running locally.
    sha=git(repo,'rev-parse','HEAD')
    if not wait(sha,900):raise RuntimeError('Initial adoption must be healthy before monitoring')
    print('Monitoring Git main; automatic recovery enabled',flush=True)
    while True:
        git(repo,'fetch','origin','main')
        remote=git(repo,'rev-parse','origin/main')
        if remote!=sha:
            git(repo,'merge','--ff-only','origin/main')
            try:watch(repo,remote,900)
            except DeploymentRecovered as error:print(str(error),flush=True)
            sha=git(repo,'rev-parse','HEAD')
        time.sleep(5)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('prepare');q.add_argument('repo');q.add_argument('url')
    q=sub.add_parser('render');q.add_argument('repo')
    q=sub.add_parser('monitor');q.add_argument('repo')
    q=sub.add_parser('update');q.add_argument('repo');q.add_argument('image');q.add_argument('digest');q.add_argument('version');q.add_argument('source_sha')
    q=sub.add_parser('watch');q.add_argument('repo');q.add_argument('sha');q.add_argument('--timeout',type=int,default=900)
    q=sub.add_parser('wait');q.add_argument('sha');q.add_argument('--timeout',type=int,default=900)
    a=p.parse_args()
    if a.cmd=='prepare':prepare(a.repo,a.url)
    elif a.cmd=='render':render(a.repo)
    elif a.cmd=='monitor':monitor(a.repo)
    elif a.cmd=='update':print(update(a.repo,a.image,a.digest,a.version,a.source_sha))
    elif a.cmd=='watch':watch(a.repo,a.sha,a.timeout)
    elif not wait(a.sha,a.timeout):raise RuntimeError('Application did not reach exact revision + Healthy')
if __name__=='__main__':main()
