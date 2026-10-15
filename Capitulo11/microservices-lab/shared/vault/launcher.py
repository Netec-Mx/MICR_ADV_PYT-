"""Bootstrap before importing settings/creating pools, then start one ASGI worker."""
import argparse
import importlib
import os
import sys
import uvicorn
from .client import VaultManager,VaultUnavailable
from .application import install

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    try:
        manager=VaultManager.from_env();manager.refresh()
        snapshot=manager.snapshot()
        if manager.role=='order-service':
            os.environ['EVENTSTORE_DATABASE_URL']=snapshot['database_url']
            os.environ['EVENTSTORE_ADMIN_KEY']=snapshot['admin_key']
            os.environ['ORDER_SERVICE_CLIENT_SECRET']=snapshot['service_client_secret']
        app=importlib.import_module('app.main').app
        install(app,manager)
        if os.getenv('LAB10_VARIANT'):
            from shared.mesh.application import install as identify
            identify(app)
        if os.getenv('OBSERVABILITY_ENABLED','false').lower()=='true':
            from shared.observability.application import install as observe
            observe(app,manager.role)
    except Exception:
        # Never emit exception representations containing URLs, JWTs or credentials.
        print('Vault bootstrap failed; verify identity, policy and required keys.',file=sys.stderr)
        raise SystemExit(1) from None
    uvicorn.run(app,host='0.0.0.0',port=args.port,workers=1,access_log=False)

if __name__=='__main__':main()
