from uuid import uuid4
import pytest
from app.schemas.product import ProductCreate, StockReservationCreate
from app.services.inventory_service import InventoryService, ProductNotFound, InsufficientStock

def fixture_service(stock=5):
    service = InventoryService()
    product = service.add_product(ProductCreate(name="Sensor", sku="SNS-001", stock_quantity=stock))
    return service, product

def payload(product_id, quantity):
    return StockReservationCreate(product_id=product_id, order_id=uuid4(), quantity=quantity)

@pytest.mark.parametrize("quantity,remaining", [(3,2),(5,0)])
def test_reserve_success(quantity, remaining):
    service, product = fixture_service()
    reservation = service.create_reservation(payload(product.id, quantity))
    assert reservation.quantity == quantity
    assert reservation.status == "pending"
    assert service.get_product(product.id).stock_quantity == remaining
    assert service.reservation_count() == 1

def test_insufficient_stock_preserves_state():
    service, product = fixture_service()
    before = service.get_product(product.id)
    with pytest.raises(InsufficientStock):
        service.create_reservation(payload(product.id, 6))
    assert service.get_product(product.id) == before
    assert service.reservation_count() == 0

def test_missing_product_preserves_state():
    service, product = fixture_service()
    with pytest.raises(ProductNotFound):
        service.create_reservation(payload(uuid4(), 1))
    assert service.get_product(product.id).stock_quantity == 5
    assert service.reservation_count() == 0

def test_consecutive_reservations():
    service, product = fixture_service()
    service.create_reservation(payload(product.id, 3))
    with pytest.raises(InsufficientStock):
        service.create_reservation(payload(product.id, 3))
    assert service.get_product(product.id).stock_quantity == 2
    assert service.reservation_count() == 1
