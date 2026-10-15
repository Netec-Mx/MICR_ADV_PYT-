"""One fault at a time, scoped cleanup and measured UTC timeline."""
import argparse,json,os,subprocess,time,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def cmd(*args,**kwargs):return subprocess.run(args,check=True,text=True,**kwargs)
def read(*args):return subprocess.check_output(args,text=True)
def now():return datetime.now(timezone.utc).isoformat()
def cluster_ready():
 for service in ('order-service','order-service-v2','inventory-service','inventory-service-green','users-service'):
  cmd('kubectl','-n','microservices','rollout','status','deployment/'+service,'--timeout=120s',stdout=subprocess.DEVNULL)
 pods=json.loads(read('kubectl','-n','microservices','get','pods','-l','app=order-service','-o','json'))['items']
 if len(pods)<2:raise RuntimeError('Se requieren al menos dos réplicas Orders v1')
 argo=json.loads(read('kubectl','-n','argocd','get','application','lab11-orders','-o','json'))['status']
 if argo['sync']['status']!='Synced' or argo['health']['status']!='Healthy':raise RuntimeError('Argo debe estar Synced/Healthy')
def main():
 a=argparse.ArgumentParser();a.add_argument('fault',choices=['pod-kill','network-delay','redis-partition','cpu-stress']);args=a.parse_args()
 os.chdir(ROOT)
 if read('kubectl','config','current-context').strip()!='msvc-gateway':raise RuntimeError('Contexto requerido: msvc-gateway')
 run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6];out=ROOT/'reports/lab12'/run;out.mkdir(parents=True)
 import yaml
 manifest=yaml.safe_load((ROOT/'chaos/lab12'/f'{args.fault}.yaml').read_text());kind=manifest['kind'];name=manifest['metadata']['name'];resource=f'{kind}/{name}'
 manifest['metadata']['labels']['run-id']=run
 lock={'apiVersion':'v1','kind':'ConfigMap','metadata':{'namespace':'chaos-testing','name':'lab12-run-lock'},'data':{'run_id':run}}
 cmd('kubectl','create','-f','-',input=json.dumps(lock),stdout=subprocess.DEVNULL)
 timeline={'run_id':run,'fault':args.fault};proc=None;clean=False;applied=False
 def event(key):timeline[key]=now();(out/'timeline.json').write_text(json.dumps(timeline,indent=2))
 def pause(seconds):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   if proc and proc.poll() is not None:raise RuntimeError('k6 terminó antes del experimento')
   time.sleep(min(1,end-time.monotonic()))
 try:
  active=read('kubectl','-n','chaos-testing','get','podchaos,networkchaos,stresschaos','-o','json')
  if json.loads(active)['items']:raise RuntimeError('Existe otro experimento; no se acumulan fallos')
  cluster_ready()
  cmd('python','scripts/lab12/contracts.py',str(out/'baseline-contracts'))
  (out/'pods-before.json').write_text(read('kubectl','-n','microservices','get','pods','-o','json'))
  env={**os.environ,'RUN_ID':run,'PROFILE':'chaos','WORKLOAD':'mixed','REPORT_DIR':str(out)}
  with (out/'k6.log').open('w') as log:
   proc=subprocess.Popen(['bash','scripts/lab12/load.sh'],env=env,stdout=log,stderr=subprocess.STDOUT);event('load_started');pause(60)
   # Confirm application requests are actually being sampled before injecting.
   if not (out/'samples.json').exists() or 'lab12_errors' not in (out/'samples.json').read_text():raise RuntimeError('Sin tráfico de negocio: no inyectar')
   from analyze import summarize
   baseline=summarize((out/'samples.json').read_text().rsplit('\n',1)[0].splitlines())
   if len(baseline)!=2 or any(x['requests']<10 or x['bad'] for x in baseline):raise RuntimeError('Baseline insuficiente o con errores: no inyectar')
   event('injection_requested');applied=True
   cmd('kubectl','create','-f','-',input=json.dumps(manifest),stdout=subprocess.DEVNULL)
   deadline=time.monotonic()+45
   while True:
    status=json.loads(read('kubectl','-n','chaos-testing','get',resource,'-o','json'))
    (out/'chaos-status.json').write_text(json.dumps(status,indent=2))
    if any(c.get('type')=='AllInjected' and c.get('status')=='True' for c in status.get('status',{}).get('conditions',[])):break
    if time.monotonic()>deadline:raise RuntimeError('Inyección no confirmada en 45 s')
    pause(1)
   event('injection_observed')
   contract=subprocess.run(['python','scripts/lab12/contracts.py',str(out/'during-contracts'),'--during-chaos','--schema-dir',str(out/'baseline-contracts')],text=True)
   timeline['contract_exit']=contract.returncode
   # For long contract timeouts the CR duration may already have restored traffic.
   pause(15 if args.fault=='pod-kill' else 45)
   cmd('kubectl','-n','chaos-testing','delete',resource,'--wait=true','--timeout=90s');clean=True;event('cleanup_confirmed')
   code=proc.wait(timeout=360);timeline['k6_exit']=code;event('load_completed')
   if code not in (0,99):raise RuntimeError(f'k6 error operativo: {code}')
  cluster_ready();event('pods_and_argo_recovered')
  (out/'pods-after.json').write_text(read('kubectl','-n','microservices','get','pods','-o','json'))
  cmd('python','scripts/lab12/contracts.py',str(out/'recovery-contracts'))
  cmd('bash','scripts/lab12/load.sh',env={**os.environ,'RUN_ID':run+'-recovery','PROFILE':'smoke','REPORT_DIR':str(out/'recovery')})
  cmd('python','scripts/lab12/analyze.py',str(out))
  if timeline.get('contract_exit'):raise RuntimeError('Se detectaron violaciones de contrato; revisar informe')
 except BaseException as exc:
  timeline['runner_error']=str(exc);event('runner_failed');raise
 finally:
  if applied and not clean:
   try:
    current=json.loads(read('kubectl','-n','chaos-testing','get',resource,'--ignore-not-found','-o','json') or '{}')
    if current and current.get('metadata',{}).get('labels',{}).get('run-id')!=run:raise RuntimeError('El recurso no pertenece a esta ejecución')
    cmd('kubectl','-n','chaos-testing','delete',resource,'--ignore-not-found','--wait=true','--timeout=90s');clean=True;event('cleanup_confirmed')
   except Exception:print('Recuperación no confirmada; conservar lock, revisar CR/finalizers y detener la sesión')
  if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=15)
  event('runner_finished')
  if (out/'samples.json').exists():
   report=subprocess.run(['python','scripts/lab12/analyze.py',str(out)],text=True)
   if report.returncode:print('Informe no generado; conservar muestras y completar manualmente')
  if not applied or clean:cmd('kubectl','-n','chaos-testing','delete','configmap','lab12-run-lock','--wait=true')
 print(out)
if __name__=='__main__':main()
