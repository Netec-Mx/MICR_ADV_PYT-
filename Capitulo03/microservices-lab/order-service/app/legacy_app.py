import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.routers.orders import router
from app.services.order_service import OrderService
from shared.kafka import EventPublisher
from shared.health import HealthResponse, HEALTH_RESPONSES

logging.basicConfig(level=logging.INFO)

def create_app(messaging=False, publisher=None):
    @asynccontextmanager
    async def lifespan(application):
        if messaging:
            application.state.publisher = EventPublisher(
                os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"), "order-service-producer")
        try:
            yield
        finally:
            if messaging:
                await asyncio.to_thread(application.state.publisher.close)
    application = FastAPI(title="OrderService", version="2.0.0", lifespan=lifespan)
    application.state.service = OrderService()
    application.state.publisher = publisher
    application.include_router(router)
    @application.get("/health", response_model=HealthResponse, responses=HEALTH_RESPONSES)
    def health():
        if messaging:
            try:
                if not application.state.publisher.ready():
                    raise RuntimeError("Kafka no disponible")
            except Exception:
                return JSONResponse(status_code=503, content={"status":"unhealthy", "service":"order-service"})
        return {"status": "healthy", "service": "order-service"}
    return application

app = create_app(messaging=os.getenv("MESSAGING_ENABLED", "false").lower() == "true")
