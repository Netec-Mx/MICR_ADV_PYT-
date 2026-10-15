# Decisiones de implementación

1. Mantener `/api/v1/orders`, estado inicial pending, UUID y precios con dos
   decimales. La creación sigue respondiendo 201 porque el estado de consulta se
   confirma con la transacción.
2. Separar eventos internos de contratos de integración. Una creación produce
   dos filas de outbox con el mismo event_id y tópicos/esquemas diferentes.
3. Usar una sola transacción para evento, proyección, snapshot y outbox.
4. Serializar escrituras del mismo agregado con advisory lock y comprobar
   expected_version. Añadir unicidad de agregado/versión como defensa adicional.
5. Usar el mismo reducer para ejecución, snapshot + tail y replay completo.
   Leer snapshot y tail con REPEATABLE READ; rechazar huecos y tipos desconocidos.
6. Guardar snapshots en cada múltiplo de 10 incluso dentro de un lote.
7. Reconstruir las proyecciones con POST administrativo y bloqueo global
   exclusivo frente a escrituras. Lectores conservan la vista confirmada.
8. Publicar mediante un relay secuencial activo protegido por advisory lock.
   Confirmar sent_at después del ack; admitir repetición tras un crash.
9. Mantener rol de migración separado de order_app y triggers que cubren también
   TRUNCATE. Un superusuario capaz de quitar esos controles queda fuera del modelo.
10. Conservar el factory antiguo para regresión de los laboratorios 1/2.
    `EVENTSTORE_ENABLED=true` selecciona la aplicación CQRS. Las pruebas legacy
    leen el contrato archivado en `contracts/legacy`; el contrato principal
    corresponde a CQRS.
11. No implantar saga, liberación de stock, reservas por ítems agregados,
    migración automática de pedidos en memoria ni deduplicación indefinida.
12. Usar credenciales didácticas explícitas y Python 3.12 con requisitos fijados.
