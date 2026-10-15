from shared.observability.context import business_span,order_created
from app.domain.order_aggregate import OrderAggregate
from app.eventstore.store import VersionConflict
from app.services.order_service import OrderNotFound

class OrderCommands:
    def __init__(self,store):self.store=store
    async def create(self,payload):
        event=OrderAggregate.creation(payload)
        with business_span('orders.persist',**{'order.item_count':len(payload.items)}):
            result=await self.store.append_events(event.aggregate_id,[event],0)
        order_created()
        return result
    async def change(self,order_id,kind,payload=None,expected_version=None):
        aggregate=await self.store.load(order_id)
        if aggregate.order is None:raise OrderNotFound()
        if expected_version is not None and expected_version != aggregate.version:
            raise VersionConflict('Versión enviada por el cliente obsoleta')
        if kind=='status':event=aggregate.change_status(payload.new_status)
        elif kind=='cancel':event=aggregate.cancel(payload.reason if payload else '')
        elif kind=='item':event=aggregate.add_item(payload)
        else:raise ValueError('Comando desconocido')
        return await self.store.append_events(order_id,[event],aggregate.version)
