# Decisiones — Laboratorio 5 (acumulativo)

- Conservar CQRS, Event Store, proyecciones, snapshots y outbox del laboratorio 3.
- Consultar el contrato real de Inventario: UUID y stock_quantity.
- Usar PyBreaker 1.2.0 mediante API pública síncrona en asyncio.to_thread;
  documentar serialización por RLock y límites de una sola réplica.
- Circuito envuelve los tres intentos Tenacity: un fallo por operación lógica.
- Semáforo limita trabajos admitidos; la cancelación no libera un worker activo.
- Disponibilidad desconocida usa null; no se inventa stock positivo ni -1.
- Conocido insuficiente devuelve 409 antes de toda escritura. Desconocido permite
  pedido pending con precheck deferred y reserva autoritativa por Kafka.
- Sumar líneas repetidas por producto antes de consultar disponibilidad.
- Mock en otro puerto y namespace; prueba half-open automática sin reset.
- Reset requiere X-Admin-Key; limpieza de tests por prefijo, sin FLUSHDB.
- No saga, reserva síncrona ni cambios de contratos de integración.

## Seguridad del laboratorio 5

- Mantener rutas, CQRS/EventStore, Kafka/Redis y resiliencia.
- Validar RS256, issuer público, audiencia por recurso, exp/iat/sub y access token Bearer.
- Exigir rol y scope conjuntamente; mantener X-Admin-Key adicional en operaciones administrativas existentes.
- Usuarios con Authorization Code + PKCE; servicios con Client Credentials y rol mínimo.
- Client role scopes explícitos; no usar fullScopeAllowed ni password grant.
- Un fallo de autenticación de servicio bloquea el pedido sin eventos/outbox y no admite fallback.
- Usar base de Keycloak separada, import declarativo y caché JWKS limitada.
- Las pruebas generadas de las factories históricas sin auth usan contratos legacy. Los contratos actuales documentan Bearer; JWT se cubre con pruebas dedicadas y Keycloak real.
