import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

@pytest.mark.asyncio
async def test_invalid_sku_is_rejected():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.post("/api/v1/products", json={
            "name": "Producto", "sku": "invalid sku!", "stock_quantity": 10})
    assert response.status_code == 422
