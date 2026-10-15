# Decisiones — Laboratorio 6 (acumulativo)

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

## Gateway del laboratorio 6

- Conservar los servicios y persistencia reales de los labs 1–5 al desplegar Kubernetes; instancia de datos nueva en PVCs, sin afirmar migración automática de volúmenes Compose.
- Añadir Users como tercer backend didáctico, protegido por users-api / user:read / users.read. Keycloak sigue siendo el emisor de identidad.
- Fijar chart 41.7.0 / Traefik 3.7.14, verificar digest oficial y aplicar explícitamente CRDs en upgrades.
- Dashboard/API administrativa deshabilitados, Service ClusterIP y port-forward local; no cambiar /etc/hosts ni depender de IP minikube accesible desde el host Windows.
- AllowCrossNamespace false: rutas, servicios y middlewares están en microservices; el provider observa ese namespace.
- Cuotas 100/200/50 por minuto con bursts 20/40/10, token bucket y estado de una réplica. No afirmar ventanas fijas ni cuotas por usuario.
- Circuitos por router. Router de chaos prioritario sin rate limiter, con marcadores de backend y validación completa 500/503/recuperación; no introducir fallos en Orders ni modificar su circuito Redis.
- Rollout por componente y scripts estrictos; no contar pods Running ni aceptar sólo que exista un 503.
