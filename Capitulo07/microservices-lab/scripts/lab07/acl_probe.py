"""Executed inside an application pod: exact Kubernetes identity, no root token."""
import os
import sys
from shared.vault.client import VaultManager
import hvac
manager=VaultManager.from_env()
try:
    manager.refresh()
    assert manager.snapshot()['admin_key']
    for service in ('order-service','inventory-service','users-service'):
        if service==manager.role:continue
        try:manager.client.secrets.kv.v2.read_secret_version(service,mount_point='secret',raise_on_deleted_version=True)
        except hvac.exceptions.Forbidden:continue
        raise RuntimeError('Cross-service read was unexpectedly permitted')
    try:manager.client.secrets.kv.v2.create_or_update_secret(manager.path,{'admin_key':'MUST-NOT-WRITE'},mount_point='secret')
    except hvac.exceptions.Forbidden:pass
    else:raise RuntimeError('Application write was unexpectedly permitted')
    print(manager.role+': own read allowed; two foreign reads and own write denied')
finally:
    if manager.client.token:manager.client.auth.token.revoke_self()
