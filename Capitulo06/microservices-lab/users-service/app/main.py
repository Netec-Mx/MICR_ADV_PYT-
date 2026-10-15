"""Read-only teaching service. Keycloak remains the identity provider.
Failure endpoint is isolated by a higher-priority gateway router.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI,Depends,HTTPException,Query
from fastapi.responses import JSONResponse
from shared.auth import configure_auth
from shared.auth.dependencies import permission
require_users_read=permission('user:read','users.read')
USERS=[{'id':1,'username':'admin-user','role':'operator'},
       {'id':2,'username':'readonly-user','role':'viewer'}]
def create_app(auth=False,jwt_validator=None):
    @asynccontextmanager
    async def lifespan(app):
        yield
        if app.state.jwt_validator:await app.state.jwt_validator.close()
    app=FastAPI(title='Users Demo Service',version='6.0.0',lifespan=lifespan)
    configure_auth(app,'users-api',auth,jwt_validator)
    @app.get('/health')
    async def health():return {'status':'healthy','service':'users-service','demo':True}
    @app.get('/api/v1/users/fail/simulate',dependencies=[Depends(require_users_read)])
    async def simulate(fail:bool=Query(True)):
        return JSONResponse(status_code=500 if fail else 200,
            content={'service':'users-service','demo':True,'simulated_failure':fail},
            headers={'X-Lab-Backend':'users-service'})
    @app.get('/api/v1/users',dependencies=[Depends(require_users_read)])
    async def users():return {'users':USERS,'total':len(USERS),'demo':True}
    @app.get('/api/v1/users/{user_id}',dependencies=[Depends(require_users_read)])
    async def user(user_id:int):
        for item in USERS:
            if item['id']==user_id:return {**item,'demo':True}
        raise HTTPException(404,'User not found')
    return app
app=create_app(auth=os.getenv('AUTH_ENABLED','false').lower()=='true')
