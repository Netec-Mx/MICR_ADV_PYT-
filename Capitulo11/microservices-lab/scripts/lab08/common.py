import os
import sys
from pathlib import Path
import importlib.util
path=Path(__file__).resolve().parents[2]/'scripts/lab06/common.py'
spec=importlib.util.spec_from_file_location('lab06_common',path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
token,headers,GATEWAY,HOST,check=base.token,base.headers,base.GATEWAY,base.HOST,base.check
JAEGER=os.getenv('JAEGER_URL','http://localhost:16686')
PROMETHEUS=os.getenv('PROMETHEUS_URL','http://localhost:9090')
ALERTMANAGER=os.getenv('ALERTMANAGER_URL','http://localhost:9093')
GRAFANA=os.getenv('GRAFANA_URL','http://localhost:3000')
