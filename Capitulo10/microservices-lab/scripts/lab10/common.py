import os,sys,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('lab10_base',ROOT/'scripts/lab06/common.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
token=base.token;HOST=base.HOST;GATEWAY=base.GATEWAY
CONTEXT=os.getenv('KUBE_CONTEXT','msvc-gateway')
SERVICES=('order-service','inventory-service','users-service')
EXPECTED={'order-service':['v1','v2'],'inventory-service':['blue','green'],'users-service':['stable']}
def k(*args):return subprocess.check_output(['kubectl','--context',CONTEXT,*args],text=True)
