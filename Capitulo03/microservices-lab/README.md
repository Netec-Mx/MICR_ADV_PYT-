# Microservicios Avanzado — Laboratorio 3

Guía completa: [LABORATORIO.md](LABORATORIO.md).

Incluye los dos microservicios, Event Store PostgreSQL, migraciones, proyecciones,
snapshots, outbox, Kafka y Redis. Mantiene los contratos de los laboratorios 1 y 2.

La guía especifica las instalaciones, los tres archivos Compose, la secuencia de
migración previa al arranque, los curl, consultas SQL y criterios de aceptación.

Validación realizada: 39 pruebas de Pedidos y 52 de Inventario, con PostgreSQL 16.3
y Redis 7.2.5 reales. Docker Compose y broker Kafka real pendientes de validación
local. Consulta [informe de revisión](docs/informe-revision-lab03.md).

Usa Python 3.12 y los requisitos fijados de cada servicio.
