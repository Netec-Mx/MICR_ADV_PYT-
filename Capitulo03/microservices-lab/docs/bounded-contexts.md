# Contextos de negocio — continuidad hasta el laboratorio 3

| Contexto | Responsabilidad | Persistencia |
|---|---|---|
| Pedidos | Ítems, importes Decimal, transiciones, historial y consultas CQRS | PostgreSQL: eventos, proyección, snapshots y outbox |
| Inventario | Productos, stock, reservas completas y resultados idempotentes | Redis con persistencia AOF |

Pedidos publica `orders.created` con el contrato del laboratorio 2, sin precios.
Inventario reserva el lote completo y publica `StockReserved` o
`StockReservationFailed`. No se comparten modelos de dominio ni tablas.

Los eventos internos de Pedidos se definen en `app/domain/events.py` y se publican
en `order-events`; los de integración permanecen en `shared/events.py`.
Cambiar estado/cancelar/agregar ítems no dispara nuevas reservas ni liberaciones.
La confirmación es manual; no se incorpora una saga en este laboratorio.

La proyección se actualiza síncronamente junto al evento. Kafka se entrega de
forma eventual mediante outbox. Las consultas leen solo la proyección y los
comandos reconstruyen el agregado desde snapshot + cola de eventos.
