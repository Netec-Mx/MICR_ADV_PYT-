"""Non-secret server-side variant identity. Never trust a request header for identity."""
import os,re
class VariantHeaderMiddleware:
    def __init__(self,app,variant,version):
        if variant not in ('v1','v2','blue','green','stable'):raise ValueError('Invalid LAB10_VARIANT')
        if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):raise ValueError('Invalid APP_VERSION')
        self.app=app;self.variant=variant.encode();self.version=version.encode()
    async def __call__(self,scope,receive,send):
        async def wrapped(message):
            if message['type']=='http.response.start':
                message=dict(message);message['headers']=[(k,v) for k,v in message.get('headers',[]) if k.lower() not in (b'x-lab-variant',b'x-lab-version')]
                message['headers']+= [(b'x-lab-variant',self.variant),(b'x-lab-version',self.version)]
            await send(message)
        await self.app(scope,receive,wrapped if scope['type']=='http' else send)
def install(app):
    if not hasattr(app.state,'lab10_variant'):
        variant=os.environ['LAB10_VARIANT'];version=os.environ['APP_VERSION']
        app.add_middleware(VariantHeaderMiddleware,variant=variant,version=version)
        app.state.lab10_variant=variant
