import json,yaml
from pathlib import Path
from common import ROOT,SERVICES

def main():
    for svc in SERVICES:
        base=yaml.safe_load((ROOT/f'reports/lab09/10.0.0/{svc}-image.yaml').read_text())
        assert base['appVersion']=='10.0.0'
        if svc!='users-service':
            extra=yaml.safe_load((ROOT/f'reports/lab09/10.1.0/{svc}-image.yaml').read_text())
            assert extra['appVersion']=='10.1.0'
            variant='v2' if svc=='order-service' else 'green'
            base['mesh']={'extra':{'enabled':True,'variant':variant,'digest':extra['image']['digest'],'appVersion':extra['appVersion']}}
        (ROOT/f'reports/lab10/{svc}-images.yaml').write_text(yaml.safe_dump(base,sort_keys=False))
if __name__=='__main__':main()
