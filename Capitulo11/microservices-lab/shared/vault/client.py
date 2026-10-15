"""One immutable KV snapshot per Kubernetes identity; never accepts a root token."""
import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4
import hvac
import requests
from hvac.api.auth_methods import Kubernetes

class VaultUnavailable(Exception):
    pass

class VaultManager:
    def __init__(self, client, role, path, jwt_file, required=('admin_key',),
                 mount='secret', poll=5, max_age=20, clock=time.monotonic):
        if not 0 < poll < max_age:
            raise ValueError('Require 0 < poll < max_age')
        self.client=client;self.role=role;self.path=path;self.jwt_file=Path(jwt_file)
        self.required=required;self.mount=mount;self.poll=poll;self.max_age=max_age;self.clock=clock
        self.lock=threading.RLock();self.io_lock=threading.Lock();self.data=None;self.version=0;self.fetched=0
        self.renew_at=0;self.token_expires=0;self.logins=0;self.renewals=0
        self.instance=str(uuid4());self.task=None;self.stopped=asyncio.Event()
        # hvac otherwise picks up VAULT_TOKEN from the operator's environment.
        self.client.token=None

    @classmethod
    def from_env(cls):
        if os.getenv('VAULT_TOKEN'):
            raise ValueError('VAULT_TOKEN is forbidden for application authentication')
        session=requests.Session();session.trust_env=False
        client=hvac.Client(url=os.environ['VAULT_ADDR'],token='',timeout=2,session=session)
        role=os.environ['VAULT_ROLE']
        required=('admin_key','database_url','service_client_secret') if role=='order-service' else ('admin_key',)
        return cls(client,role,os.environ['VAULT_SECRET_PATH'],
                   os.getenv('VAULT_JWT_FILE','/var/run/secrets/vault/token'),required,
                   poll=float(os.getenv('VAULT_POLL_SECONDS','5')),
                   max_age=float(os.getenv('VAULT_MAX_AGE_SECONDS','20')))

    def _set_lease(self, auth):
        ttl=auth['lease_duration']
        if not auth.get('renewable') or not isinstance(ttl,(int,float)) or ttl<=0:
            raise VaultUnavailable('Non-renewable or invalid token lease')
        now=self.clock();self.token_expires=now+ttl;self.renew_at=now+ttl*.5

    def _login(self):
        # Read again on every login: Kubernetes rotates the projected JWT file.
        try:jwt=self.jwt_file.read_text().strip()
        except OSError:raise VaultUnavailable('Service account JWT unavailable') from None
        if not jwt:raise VaultUnavailable('Missing service account JWT')
        result=Kubernetes(self.client.adapter).login(role=self.role,jwt=jwt)
        self._set_lease(result['auth']);self.logins+=1

    def refresh(self):
        with self.io_lock:
            try:
                if not self.client.token or self.clock()>=self.token_expires:self._login()
                elif self.clock()>=self.renew_at:
                    try:
                        result=self.client.auth.token.renew_self()
                        self._set_lease(result['auth']);self.renewals+=1
                    except (hvac.exceptions.Forbidden,hvac.exceptions.InvalidRequest):
                        self.client.token=None;self._login()
                result=self.client.secrets.kv.v2.read_secret_version(
                    path=self.path,mount_point=self.mount,raise_on_deleted_version=True)
                data=result['data']['data'];version=result['data']['metadata']['version']
                if (not isinstance(data,dict) or any(not isinstance(data.get(k),str) or not data[k].strip() for k in self.required)
                    or not isinstance(version,int) or isinstance(version,bool) or version<=0):
                    raise VaultUnavailable('Invalid secret schema')
                with self.lock:
                    self.data=MappingProxyType(dict(data));self.version=version;self.fetched=self.clock()
                return self.version
            except (hvac.exceptions.Forbidden,hvac.exceptions.Unauthorized,hvac.exceptions.InvalidRequest,hvac.exceptions.InvalidPath,
                    VaultUnavailable,KeyError,TypeError,ValueError) as exc:
                with self.lock:self.data=None
                self.client.token=None
                raise VaultUnavailable('Vault authentication or configuration rejected') from exc
            except (requests.RequestException,hvac.exceptions.VaultError) as exc:
                # Transport/5xx outages permit only the bounded last valid snapshot.
                raise VaultUnavailable('Vault temporarily unavailable') from exc

    def snapshot(self):
        with self.lock:
            if self.data is None or self.clock()-self.fetched>=self.max_age:
                raise VaultUnavailable('Vault configuration unavailable')
            return self.data

    def status(self):
        with self.lock:
            self.snapshot()
            return {'service':self.role,'version':self.version,'instance':self.instance,
                    'age_seconds':round(self.clock()-self.fetched,2),
                    'logins':self.logins,'renewals':self.renewals}

    async def run(self):
        while not self.stopped.is_set():
            try:await asyncio.to_thread(self.refresh)
            except VaultUnavailable:
                logging.getLogger('lab.vault').warning('vault_refresh_failed service=%s',self.role)
            try:await asyncio.wait_for(self.stopped.wait(),timeout=self.poll)
            except asyncio.TimeoutError:pass

    async def start(self):
        self.task=asyncio.create_task(self.run(),name='vault-refresh')

    async def stop(self):
        self.stopped.set()
        if self.task:await self.task
        def close():
            with self.io_lock:
                try:
                    if self.client.token:self.client.auth.token.revoke_self()
                except (requests.RequestException,hvac.exceptions.VaultError):pass
                self.data=None;self.client.token=None;self.client.adapter.session.close()
        await asyncio.to_thread(close)
