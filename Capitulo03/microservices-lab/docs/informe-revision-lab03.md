# Informe de revisión — Laboratorio 3

Se conservaron los cinco objetivos: Event Store PostgreSQL, CQRS, proyecciones
síncronas, snapshots cada diez eventos con reconstrucción y publicación Kafka.
Se corrigieron contratos, recuperación de snapshots, control de concurrencia,
atomicidad, publicación fiable, administración y limpieza.

## Verificación ejecutada

| Grupo | Resultado |
|---|---|
| Pedidos, regresión modo Lab01/02 | 19 aprobadas |
| Pedidos, PostgreSQL real/migraciones/CQRS/outbox simulada | 20 aprobadas |
| Inventario | 52 aprobadas, incluyendo 11 con Redis real |
| Contratos OpenAPI principales | Ambos válidos |
| Intérprete y dependencias principales | Python 3.12.14; requisitos fijados |

PostgreSQL 16.3 se ejecutó en una instancia temporal compilada para el entorno de
prueba. Las pruebas crearon bases independientes y ejecutaron las migraciones
001_eventstore y 002_append_only; el Store conectó como order_app. Redis 7.2.5 se
ejecutó en un puerto de prueba independiente. No se usa SQLite como sustituto.

Casos cubiertos: restricciones de inmutabilidad y permisos, rollback de fallo de
proyección, colisión de versión y evento duplicado, snapshot 10 + cola 11,
lotes que cruzan versión 10, rebuild que restaura proyección y conserva outbox,
rollback por evento desconocido, coordinación con comandos concurrentes,
publicación fallida seguida de reintento con identidad estable, contrato
orders.created, rutas HTTP, validaciones y ausencia de fallback de consulta.

La prueba del relay emplea un productor simulado para observar fallos y ack.
No se ejecutó Docker Compose ni Kafka real. Los scripts validate_lab02.py y
validate_lab03.py completan HTTP/broker/consumidor en el equipo del participante.
Se revisó la configuración Compose, pero no se declara una ejecución de
contenedores que no se realizó.

## Límites explícitos

Snapshots son caché reconstruible, no fuente de verdad. La proyección síncrona no
presenta el desfase eventual de Kafka. La outbox garantiza retención/reintentos,
no exactly-once. Inventario deduplica durante 24 horas. El relay es secuencial y
el rebuild carga el historial del laboratorio en memoria. Los accesos de
administración y credenciales son didácticos. No se implementa saga de reserva,
confirmación ni liberación automática.

Se reescribió la guía con un diagrama inicial Mermaid, instrucciones PowerShell
y Bash, entornos Python 3.12, orden de migración, ejemplos curl y evidencia SQL.
