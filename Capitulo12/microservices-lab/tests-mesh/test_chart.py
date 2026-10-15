from pathlib import Path
import json,os,subprocess,yaml,pytest
R=Path(__file__).resolve().parents[1];H=os.getenv('HELM_BIN','helm');A='sha256:'+'a'*64;B='sha256:'+'b'*64
@pytest.mark.parametrize('svc,variant',[('order-service','v2'),('inventory-service','green')])
def test_variant_is_owned_by_same_release_with_disjoint_selector(svc,variant):
    cmd=[H,'template',svc,str(R/'helm/msvc-chart'),'-n','microservices','-f',str(R/f'helm/values/{svc}.yaml'),'-f',str(R/f'helm/values/lab10-{svc}.yaml'),'--set','image.digest='+A,'--set','mesh.extra.enabled=true','--set','mesh.extra.digest='+B]
    docs=list(yaml.safe_load_all(subprocess.check_output(cmd,text=True)));ds=[o for o in docs if o['kind']=='Deployment'];assert len(ds)==2
    main=next(d for d in ds if d['metadata']['name']==svc);extra=next(d for d in ds if d['metadata']['name']==svc+'-'+variant)
    assert main['spec']['selector']['matchLabels']=={'app':svc}
    assert extra['spec']['selector']['matchLabels']=={'app':svc+'-'+variant}
    for d in ds:
        p=d['spec']['template']['spec'];c=p['containers'][0]
        assert p['serviceAccountName']==svc and p['securityContext']['fsGroup']==10001
        assert not p['automountServiceAccountToken'] and c['command'][2]=='shared.vault.launcher'
        assert d['spec']['template']['metadata']['labels']['sidecar.istio.io/inject']=='true'
        assert not {'VAULT_TOKEN','ORDER_SERVICE_CLIENT_SECRET','EVENTSTORE_ADMIN_KEY','EVENTSTORE_DATABASE_URL'} & {e['name'] for e in c['env']}
    assert next(o for o in docs if o['kind']=='Service')['spec']['selector']=={'lab10-service':svc}
    env={e['name']:e.get('value') for e in extra['spec']['template']['spec']['containers'][0]['env']}
    assert env['LAB10_VARIANT']==variant and env['APP_VERSION']=='10.1.0'
    assert extra['spec']['template']['spec']['containers'][0]['image'].endswith('@'+B)
@pytest.mark.parametrize('pair',[(90,10),(50,50),(0,100)])
def test_routes_weights_boundaries_and_single_mtls_rule(pair):
    docs=list(yaml.safe_load_all((R/f'istio/routes-{pair[0]}-{pair[1]}.yaml').read_text()))
    ingress=docs[0];order=ingress['spec']['http'][0]
    assert ingress['spec']['hosts']==['microservices.local']
    assert [r['weight'] for r in order['route']]==list(pair)
    assert order['match']==[{'uri':{'exact':'/api/v1/orders'}},{'uri':{'prefix':'/api/v1/orders/'}}]
    assert order['retries']['attempts']==0
    green=ingress['spec']['http'][1]
    assert all(m['headers']['x-version']['exact']=='green' for m in green['match'])
    assert all(r['destination']['subset']=='green' for r in green['route'])
    drs=list(yaml.safe_load_all((R/'istio/destination-rules.yaml').read_text()))
    assert len(drs)==3 and len({d['spec']['host'] for d in drs})==3
    assert all(d['spec']['trafficPolicy']['tls']['mode']=='ISTIO_MUTUAL' for d in drs)
def test_metrics_extend_same_stack_and_do_not_double_count_reporters():
    output=subprocess.check_output([H,'template','lab08-observability',str(R/'observability/chart'),'-n','observability','--set','mesh.enabled=true'],text=True)
    ds=list(yaml.safe_load_all(output));cm=next(d for d in ds if d['kind']=='ConfigMap' and d['metadata']['name']=='lab08-prometheus')
    config=yaml.safe_load(cm['data']['prometheus.yaml']);job=config['scrape_configs'][0]
    assert job['metrics_path']=='/stats/prometheus' and len(job['static_configs'])==5
    services=[d for d in ds if d['kind']=='Service' and d['metadata']['name'].endswith('-metrics')]
    assert len(services)==5 and all(s['spec']['ports'][0]['targetPort']==15020 for s in services)
    dash=json.loads((R/'observability/chart/files/dashboard-mesh.json').read_text())
    assert len(dash['panels'])==5
    for p in dash['panels']:
        q=p['targets'][0]['expr']
        if 'istio_' in q:assert 'reporter="destination"' in q
    assert dash['panels'][2]['targets'][0]['expr'].endswith('/ 1000')
    graf=next(d for d in ds if d['kind']=='Deployment' and d['metadata']['name']=='grafana')
    assert any(m['mountPath'].endswith('/mesh.json') for m in graf['spec']['template']['spec']['containers'][0]['volumeMounts'])
