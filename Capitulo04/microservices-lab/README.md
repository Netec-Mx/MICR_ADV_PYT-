# Microservicios Avanzado — Laboratorio 4

Guía completa: [LABORATORIO.md](LABORATORIO.md).

Incluye ambos servicios, CQRS/Event Store, outbox, Kafka, Redis y resiliencia.
El mock usa 8003 y conserva Inventario real en 8002. Sigue las funciones Compose
normal y caos de la guía; vuelve al modo normal antes de probar reservas.

Pruebas: 73 de Pedidos y 52 de Inventario; siete escenarios HTTP de caos.
Docker Compose/Kafka completos pendientes de comprobación local.
