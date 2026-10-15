# Informe de revisión · Laboratorio 5

Se conserva la continuidad del curso y sus cinco objetivos de seguridad. El original sustituía las aplicaciones por ejemplos en memoria, desactivaba audiencia y carecía de comprobación real de scopes. Se reemplaza ese enfoque por seguridad integrada en las factories y rutas existentes.

## Cambios

- Keycloak 26.8.0 con base independiente, health management :9000 e import reproducible.
- PyJWT 2.15.1/cryptography 50.0.2 en Python 3.12; RS256 y claims requeridos.
- Roles y scopes, audiencias order-api/inventory-api, mapper sub explícito para usuarios, role scope mappings y password grant deshabilitado.
- Login de usuarios con Authorization Code + PKCE S256 y state.
- Client Credentials cacheado para Orders → Inventory; refresh una vez ante 401, 403 sin refresh; error de identidad bloquea la escritura sin fallback.
- Conserva PostgreSQL/CQRS, outbox, snapshots, Kafka/Redis y controles de resiliencia del Lab 4.
- Diagrama inicial Mermaid, curl PowerShell/Bash, validador de pila completa y pruebas negativas con JWT reales.
- OpenAPI generado validado; contratos actuales con Bearer y respuestas 401/403/503. Contratos legacy para regresiones que usan factories sin autenticación.

## Verificación realizada

**176 pruebas aprobadas: 119 Orders + 57 Inventory**, Python 3.12.14. PostgreSQL 16.3 y Redis 7.2.5 reales para integración; Keycloak 26.8.0 real con almacenamiento H2 temporal exclusivamente para estas pruebas. Incluye 5 pruebas de Keycloak: firma/audiencia de servicio, expiración real, rechazo de password grant, Authorization Code PKCE válido y verifier incorrecto. Se comprobó que un fallo de identidad de servicio no crea eventos ni outbox. Se repitieron los contratos afectados y las pruebas de Inventory después de documentar Bearer.

También se verificó HTTP real con ambas APIs y Keycloak: token Client Credentials de operador, rechazo sin Bearer, creación de producto y pedido con precheck `verified` mediante identidad de servicio y persistencia EventStore. Esa prueba aisló la mensajería y no demuestra una reserva Kafka.

Preflight y pip check aprobados. Se validan sintaxis Python y esquemas OpenAPI.

**Límite de verificación:** no se ejecutó Docker Compose ni Kafka en este entorno. La base PostgreSQL de Keycloak del overlay y la reserva asíncrona completa deben comprobarse con `dc config --quiet`, `dc up` y `python scripts/validate_lab05.py` en el equipo del alumno. El test con H2 no sustituye la prueba del contenedor PostgreSQL de Keycloak. Los comandos de la guía conservan los topics y migraciones de la base revisada del Lab 4.

Las warnings de las bibliotecas anteriores se conservan como deuda del entorno acumulativo; el alcance de este capítulo no es actualizar toda la pila del curso.
