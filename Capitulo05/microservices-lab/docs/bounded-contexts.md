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
