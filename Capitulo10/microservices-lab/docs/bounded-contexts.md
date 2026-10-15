# Contextos de negocio — Laboratorio 4

| Contexto | Persistencia | Responsabilidad |
|---|---|---|
| Pedidos | PostgreSQL | Agregado, eventos, consultas CQRS, snapshots y outbox |
| Inventario | Redis DB 0 | Stock, reservas atómicas y resultados idempotentes |
| Resiliencia de Pedidos | Redis DB 1 | Estado de circuitos, namespace normal/caos |

Pedidos observa stock con GET; no modifica claves de Inventario. La creación
publica el mismo OrderCreated del lab 2 mediante outbox del lab 3. La reserva
real puede fallar aunque el precheck fuese suficiente; no se incorpora saga.

Mock en 8003 solo observa solicitudes sintéticas y no consume Kafka. No crear
pedidos durante el modo caos. Un estado desconocido permite diferir validación
y mantener pending, sin afirmar stock disponible ni reserva confirmada.

## Identidad y permisos del Lab 5

Keycloak emite access tokens. Cada API valida firma, issuer y audiencia y exige rol + scope. Orders obtiene su propio token inventory.read; no propaga el JWT del usuario a Inventory. Los contratos Kafka, el CQRS de Orders y el estado persistido en Redis se conservan.

## Gateway y Users de demostración (Lab 6)

Traefik enruta a Orders, Inventory y Users. No cambia los bounded contexts de negocio ni sustituye los contratos Kafka. Users contiene registros ficticios de lectura y fallo simulado; no es un CRUD de usuarios ni la fuente de identidades de Keycloak. La comprobación HTTP Orders → Inventory continúa por el Service interno y usa Client Credentials. El circuit breaker del Gateway mantiene estado separado del circuito Redis del cliente de Orders.
