import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

@pytest.mark.asyncio
async def test_create_order_async():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.post("/api/v1/orders", json={
            "customer_id": "11111111-1111-1111-1111-111111111111",
            "items": [{"product_id": "22222222-2222-2222-2222-222222222222",
                       "quantity": 2, "unit_price": "25.50"}]})
    assert response.status_code == 201
    assert response.json()["total"] == "51.00"
