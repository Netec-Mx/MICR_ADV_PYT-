# Informe de revisión — Laboratorio 4

Se preservan retry, circuit breaker Redis, bulkhead, fallback y observabilidad.
Se integra el precheck en CQRS sin eliminar Event Store, snapshots, proyecciones
ni outbox. El mock se aísla en 8003; Inventario real y Kafka se conservan.

## Correcciones

Ruta /api/v1/products/{UUID}, campo stock_quantity, API pública breaker.call(),
storage nativo Redis, singleton protegido para creación concurrente, threads
fuera del event loop, liberación de slots al finalizar el worker real, null para
stock desconocido, rechazo conocido sin escritura y configuración normal/caos.

## Evidencia

73 tests de Pedidos aprobados: 19 legacy, 20 Event Store, 28 resiliencia y 6
integración precheck/Event Store. 52 tests de Inventario. PostgreSQL 16.3 y Redis
7.2.5 reales en instancias de prueba. Siete escenarios de caos HTTP real aprobados
con Uvicorn, mock aislado y Redis: normal, éxito tras dos fallos, apertura,
bloqueo sin HTTP, recuperación half-open, timeout, 404 y saturación (apertura y
bloqueo se contabilizan como un escenario).

Se valida independencia de consultas/read model, ausencia de eventos/outbox
tras rechazo, agrupación de cantidades y conservación de creación pendiente.
No se ejecutaron Docker Compose ni Kafka real. Las pruebas HTTP de caos no
escriben negocio; la integración de escritura se probó aparte con PostgreSQL.

## Límites

PyBreaker 1.2.0 serializa llamadas protegidas. El bulkhead limita trabajos
admitidos, no garantiza N solicitudes HTTP simultáneas. Una réplica/un worker:
Redis persistente no constituye bloqueo distribuido. Los timeouts HTTPX son por
fase, no un presupuesto global de respuesta; un timeout no cancela trabajo
remoto. La consulta es preliminar y la reserva sigue siendo responsabilidad de
Kafka/Inventario. No se añade saga ni liberación automática.

Las credenciales/claves son de práctica local. La guía contiene Mermaid,
PowerShell/Bash, curl, Compose, test automático, recuperación y criterios.
