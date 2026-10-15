import os
from app.legacy_app import create_app
from app.cqrs_app import create_cqrs_app

if os.getenv('RESILIENCE_ENABLED','false').lower()=='true' and os.getenv('EVENTSTORE_ENABLED','false').lower()!='true':
    raise RuntimeError('Lab04 requiere EVENTSTORE_ENABLED=true junto con RESILIENCE_ENABLED=true')

# Legacy factory remains only for Lab 01/02 regression tests and explicit old mode.
if os.getenv('EVENTSTORE_ENABLED','false').lower()=='true':
    app=create_cqrs_app(messaging=os.getenv('MESSAGING_ENABLED','false').lower()=='true',
                        resilience=os.getenv('RESILIENCE_ENABLED','false').lower()=='true')
else:
    app=create_app(messaging=os.getenv('MESSAGING_ENABLED','false').lower()=='true')
