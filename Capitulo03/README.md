# Laboratorio 3 — Event Sourcing, CQRS, proyecciones y snapshots

**Curso:** Microservicios Avanzado · **Nivel:** alto · **Bloom:** crear  
**Duración:** 66 minutos con dependencias, imágenes y entornos preparados. La primera instalación requiere tiempo adicional.  
**Continuidad:** partir del laboratorio 2 corregido; conservar la API de pedidos del laboratorio 1 y los contratos Kafka del laboratorio 2.

## 1. Resultado esperado

Pedidos deja de almacenar su estado de negocio en memoria. Cada comando válido agrega eventos en PostgreSQL y actualiza una proyección de consulta dentro de la misma transacción. El servicio consulta exclusivamente esa proyección. Los snapshots aceleran la recuperación del agregado; Kafka recibe los mensajes mediante una outbox persistente.

```mermaid
flowchart TD
    Cliente["Cliente HTTP"] --> Comandos["Comandos de Pedidos"]
    Cliente --> Consultas["Consultas de Pedidos"]
    Comandos --> Agregado["Agregado y reglas"]
    Agregado --> Transaccion["Transacción PostgreSQL"]
    subgraph PostgreSQL
      Transaccion --> Eventos["Eventos append-only"]
      Transaccion --> Proyeccion["Proyección de pedidos"]
      Transaccion --> Snapshot["Snapshot cada 10 eventos"]
      Transaccion --> Outbox["Outbox persistente"]
    end
    Consultas --> Proyeccion
    Eventos --> Replay["Replay y reconstrucción"]
    Snapshot --> Replay
    Replay --> Agregado
    Outbox --> Relay["Relay con reintentos"]
    Relay --> Kafka["Kafka"]
    Kafka --> Inventario["Inventario del laboratorio 2"]
    Inventario --> Redis["Stock y reservas en Redis"]
```

La flecha hacia Inventario corresponde al tópico `orders.created`. El tópico `order-events` contiene eventos internos para inspección y no se consume como solicitudes de reserva. El administrador reconstruye proyecciones desde **todos los eventos**, sin publicar mensajes nuevos.

### Los cinco objetivos que se conservan

| Objetivo | Implementación y evidencia |
|---|---|
| Event Store inmutable en PostgreSQL | Tabla `events`, metadatos completos, versiones únicas por agregado, permisos y triggers contra UPDATE, DELETE y TRUNCATE. |
| Separación CQRS | `OrderCommands` escribe mediante el Event Store; `OrderQueries` lee solamente `order_projections`. |
| Proyecciones síncronas | Evento y proyección se confirman o se revierten juntos; replay comparte las reglas del agregado. |
| Snapshots y reconstrucción | Snapshot en versiones 10, 20, etc.; carga snapshot + eventos posteriores; `POST /admin/rebuild-projections`. |
| Persistencia y publicación Kafka | Evento y outbox se guardan juntos; relay publica y registra confirmación del broker. `OrderCreated` mantiene el contrato del laboratorio 2. |

### Qué cambia frente al laboratorio original

| Problema del original | Corrección |
|---|---|
| Cambiaba `/api/v1/orders`, el cuerpo, el estado inicial y el evento usado por Inventario | Conserva rutas, UUID, múltiples ítems, precios decimales y estado `pending`; separa eventos internos del contrato público Kafka. |
| Proyección escrita después de confirmar eventos | Una sola transacción para eventos, proyección, snapshots y outbox. |
| `expected_version` no comprobaba la versión real | Bloqueo por agregado, comprobación de versión y restricción única. |
| Snapshot cargado sin aplicar correctamente los eventos posteriores | Recuperación coherente con `REPEATABLE READ` y replay de la cola. |
| Snapshot omitido al cruzar un múltiplo de 10 dentro de un lote | Verifica cada evento del lote; snapshot representa exactamente el punto de corte. |
| Kafka podía perder mensajes después de confirmar PostgreSQL | Outbox con entrega al menos una vez y reintentos; no promete exactamente una vez. |
| Reconstrucción mediante GET y sin coordinación | POST con clave administrativa, transacción y exclusión frente a escrituras. |
| Migraciones generadas/modificadas manualmente en clase | Dos revisiones explícitas, encadenadas y verificadas. |
| Limpieza destruía el historial o todos los procesos Uvicorn | Parada del proyecto sin borrar volúmenes; reinicio destructivo solamente como opción explícita. |

## 2. Preparación y materiales

Descomprime `Lab03_Microservicios_Avanzado_materiales.zip` en una carpeta nueva. El paquete contiene ambos servicios completos, el código heredado de los laboratorios 1 y 2, migraciones, contratos, pruebas y esta guía. Trabaja desde `microservices-lab`, que contiene los tres archivos Compose.

No se convierten los pedidos anteriores almacenados en memoria en eventos históricos. Este laboratorio persiste los pedidos nuevos. Si reutilizas la infraestructura del laboratorio 2, primero detén sus API; utiliza siempre el conjunto de tres archivos Compose indicado abajo. Para una ejecución aislada, elige otro nombre de proyecto con `-p` y puertos libres.

**Requisitos:** Docker con Compose v2, Python **3.12** para ejecutar herramientas y pruebas desde el host, puertos 8001, 8002, 5432, 6379 y 29092 disponibles. La instalación del laboratorio original con Python 3.13 no es el entorno de este material.

Pedidos añade estas dependencias a las versiones ya fijadas en el laboratorio 2:

```text
pydantic-settings==2.2.1
SQLAlchemy==2.0.30
asyncpg==0.29.0
alembic==1.13.1
```

Los archivos `requirements.txt` y `requirements-dev.txt` del paquete son la referencia para instalar. No actualices Pydantic o sus dependencias aisladamente. La versión fijada de `pydantic-settings` es deliberada para mantener compatibilidad con Pydantic 2.7.1.

### Entornos Python, si aún no existen

PowerShell, desde la raíz del proyecto; no requiere el lanzador `py`. Ajusta la ruta si Python 3.12 está instalado en otra ubicación:

```powershell
$Python312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $Python312 --version
& $Python312 -m venv order-service/.venv312
& $Python312 -m venv inventory-service/.venv312
& ./order-service/.venv312/Scripts/python.exe -m pip install -r order-service/requirements-dev.txt
& ./inventory-service/.venv312/Scripts/python.exe -m pip install -r inventory-service/requirements-dev.txt
& ./order-service/.venv312/Scripts/python.exe scripts/preflight.py --eventstore
```

Si ya existen los entornos corregidos, verifica su versión e instala los requisitos actualizados; no los vuelvas a crear. No uses un entorno creado con Python 3.13 aunque se llame `.venv312`.

Bash:

```bash
python3.12 -m venv order-service/.venv312
python3.12 -m venv inventory-service/.venv312
order-service/.venv312/bin/python -m pip install -r order-service/requirements-dev.txt
inventory-service/.venv312/bin/python -m pip install -r inventory-service/requirements-dev.txt
order-service/.venv312/bin/python scripts/preflight.py --eventstore
```

El preflight verifica intérprete, versiones principales y contratos OpenAPI. No reemplaza la prueba de PostgreSQL o Kafka.

## 3. Infraestructura y migraciones — 12 minutos

### 3.1. Preparar Compose

En PowerShell define una vez esta función, manteniendo la terminal en la raíz del proyecto:

```powershell
function dc { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml @args }
dc config
dc build order-service inventory-service
dc up -d postgres zookeeper kafka redis
dc ps
```

En Bash usa la misma función durante toda la práctica:

```bash
dc() { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml "$@"; }
dc config
dc build order-service inventory-service
dc up -d postgres zookeeper kafka redis
dc ps
```

Espera a que PostgreSQL, Kafka y Redis estén saludables. Los comandos siguientes sirven igual en ambas terminales:

```text
dc exec postgres pg_isready -U lab_admin -d eventstore_db
dc exec redis redis-cli ping
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --list
```

PostgreSQL ya está incluido: no se presupone un contenedor externo llamado `mslab-postgres`. El archivo de inicialización crea el rol de ejecución `order_app`; se ejecuta únicamente con un volumen PostgreSQL nuevo. Un volumen antiguo que no tenga ese rol requiere ejecutar explícitamente `infra/postgres/001_roles.sql` como administrador antes de migrar. No borres datos para corregir un rol faltante.

### 3.2. Crear los cuatro tópicos

```text
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic orders.created --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic inventory.stock-reserved --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic inventory.stock-failed --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic order-events --partitions 3 --replication-factor 1
```

### 3.3. Aplicar las migraciones preparadas

Antes de arrancar las API:

```text
dc run --rm --no-deps -e EVENTSTORE_ADMIN_DATABASE_URL=postgresql+asyncpg://lab_admin:lab_admin_lab_pass@postgres:5432/eventstore_db order-service python -m alembic upgrade head
dc run --rm --no-deps -e EVENTSTORE_ADMIN_DATABASE_URL=postgresql+asyncpg://lab_admin:lab_admin_lab_pass@postgres:5432/eventstore_db order-service python -m alembic current
```

Debe aparecer `002_append_only (head)`. `001_eventstore` crea tablas, índices y restricciones; `002_append_only` crea triggers y concede permisos mínimos. No ejecutes `alembic revision --autogenerate`, ni edites `down_revision` con `sed`.

La API usa `order_app`; las migraciones usan `lab_admin`. Ambas credenciales y la clave administrativa incluidas son exclusivamente para el laboratorio local. El rol de la aplicación puede insertar/leer eventos, pero no alterarlos, borrarlos ni truncarlos. Los triggers rechazan esas operaciones también cuando se ejecutan directamente como propietario mientras siguen instalados. Un administrador capaz de quitar triggers o tablas queda fuera de esta garantía.

### 3.4. Arrancar las API

```text
dc up -d order-service inventory-service
dc ps
dc logs --tail 50 order-service inventory-service
```

Prueba `http://localhost:8001/health` y `http://localhost:8002/health`. Ambos deben responder HTTP 200. Pedidos verifica acceso a la tabla de eventos y disponibilidad de Kafka/relay; el estado saludable no implica que toda la outbox esté ya publicada.

## 4. Event Store y agregado — 12 minutos

Revisa estos archivos antes de ejecutar comandos:

| Archivo | Responsabilidad |
|---|---|
| `app/domain/events.py` | Eventos internos tipados, identificación, versión de esquema, correlación y causalidad. |
| `app/domain/order_aggregate.py` | Reglas, estados, importes `Decimal` y replay determinista. |
| `app/eventstore/models.py` | Tablas `events`, `order_projections`, `snapshot_orders`, `outbox`. |
| `app/eventstore/store.py` | Versión esperada, bloqueo por agregado y transacción atómica. |
| `app/commands/order_commands.py` | Traducción de solicitudes a eventos. |
| `shared/events.py` | Contratos de integración heredados del laboratorio 2. |

Todas las rutas de esta sección corresponden a `order-service`, salvo `shared`, que está en la raíz.

El total se deriva de los ítems con aritmética decimal; el cliente no envía `total_amount`. Se preservan UUID y precios como cadenas con dos decimales. Hay dos conceptos distintos:

- `event_version: "1.0.0"`: versión del **esquema** del evento.
- `aggregate_version: 1, 2, ...`: posición del evento dentro del historial de un pedido.

Cada evento tiene `event_id`, `event_type`, `aggregate_id`, `aggregate_type`, `aggregate_version`, fecha UTC, payload y metadatos de correlación/causalidad/origen. `(aggregate_id, aggregate_version)` es único. `event_id` también es único.

Al anexar eventos, el Store toma un bloqueo de transacción para ese agregado, lee la última versión y compara `expected_version`. Dos comandos que intentan escribir desde la misma versión no pueden confirmar ambos: uno obtiene `VERSION_CONFLICT`, HTTP 409. La cabecera opcional `X-Expected-Version` permite al cliente declarar la versión que leyó; el control interno se aplica aunque esa cabecera no se envíe.

## 5. CQRS y proyecciones — 12 minutos

`OrderQueries` no lee la tabla `events`, snapshots ni el agregado en memoria. Consulta `order_projections`. El comando necesita recuperar el agregado desde el historial para validar las reglas.

Dentro de una única transacción se ejecuta:

1. Comprobar versión y aplicar la regla de dominio.
2. Insertar el evento.
3. Actualizar la proyección.
4. Guardar el snapshot si corresponde.
5. Insertar los mensajes pendientes en outbox.

Un fallo revierte todos esos efectos. La proyección es síncrona: una creación confirmada responde **201**, y su GET posterior ya encuentra el pedido. La entrega hacia Kafka es asíncrona y eventual. Un 201 confirma persistencia de negocio, no la reserva de stock.

Estados permitidos:

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> confirmed
    confirmed --> processing
    processing --> shipped
    shipped --> delivered
    pending --> cancelled
    confirmed --> cancelled
    processing --> cancelled
    delivered --> [*]
    cancelled --> [*]
```

La cancelación se conserva en `PATCH /api/v1/orders/{id}/cancel`. No se permite enviar `cancelled` al endpoint genérico de estado. Agregar ítems se admite en `pending` o `confirmed`, hasta 100 ítems por pedido. Un salto como `confirmed → shipped` devuelve 409 y no crea eventos.

**Alcance:** confirmar es un comando manual. El laboratorio no implementa una saga: `StockReserved` no confirma automáticamente el pedido; cancelar no libera reservas; agregar ítems no solicita reservas adicionales. Esas extensiones requieren nuevos contratos y coordinación y no se introducen implícitamente en esta práctica.

## 6. Prueba con curl — 12 minutos

### 6.1. PowerShell: flujo completo y snapshot

Se usa `curl.exe` para evitar el alias de PowerShell. Los cuerpos se escriben como UTF-8 sin BOM y se envían con `--data-binary`, evitando problemas de comillas en Windows. Conserva la misma terminal para reutilizar las variables.

```powershell
$Utf8 = [System.Text.UTF8Encoding]::new($false)
function jsonFile($Nombre, $Objeto) {
    [System.IO.File]::WriteAllText((Join-Path $PWD $Nombre), ($Objeto | ConvertTo-Json -Depth 10), $Utf8)
}
curl.exe -i http://localhost:8001/health
curl.exe -i http://localhost:8002/health

# Producto con stock suficiente: evita reservar directamente el mismo stock otra vez.
jsonFile product.json @{name="Producto Lab03"; sku=("LAB03-" + [guid]::NewGuid().ToString().ToUpper()); stock_quantity=100}
$product = curl.exe -sS -X POST http://localhost:8002/api/v1/products -H "Content-Type: application/json" --data-binary "@product.json" | ConvertFrom-Json
$ProductId = $product.id

$item = @{product_id=$ProductId; quantity=1; unit_price="2.50"}
jsonFile order.json @{customer_id=[guid]::NewGuid().ToString(); items=@($item)}
$order = curl.exe -sS -X POST http://localhost:8001/api/v1/orders -H "Content-Type: application/json" --data-binary "@order.json" | ConvertFrom-Json
$OrderId = $order.id
if (-not $OrderId) { throw "No se creó el pedido: $($order | ConvertTo-Json)" }
curl.exe -i "http://localhost:8001/api/v1/orders/$OrderId"
curl.exe -i "http://localhost:8001/api/v1/orders?limit=10&offset=0"

# Creación = evento 1. Nueve ítems adicionales = versión 10.
jsonFile item.json $item
1..9 | ForEach-Object {
    curl.exe -sS -X POST "http://localhost:8001/api/v1/orders/$OrderId/items" -H "Content-Type: application/json" --data-binary "@item.json"
}
curl.exe -i "http://localhost:8001/api/v1/orders/$OrderId"

# Versión 11: un evento posterior al snapshot de versión 10.
jsonFile status.json @{new_status="confirmed"}
curl.exe -i -X PATCH "http://localhost:8001/api/v1/orders/$OrderId/status" -H "Content-Type: application/json" -H "X-Expected-Version: 10" --data-binary "@status.json"

# Versión obsoleta: debe responder 409 VERSION_CONFLICT.
curl.exe -i -X POST "http://localhost:8001/api/v1/orders/$OrderId/items" -H "Content-Type: application/json" -H "X-Expected-Version: 10" --data-binary "@item.json"

# Salto inválido: debe responder 409 INVALID_ORDER_STATE.
jsonFile status.json @{new_status="shipped"}
curl.exe -i -X PATCH "http://localhost:8001/api/v1/orders/$OrderId/status" -H "Content-Type: application/json" --data-binary "@status.json"

# Cancelación válida desde confirmed: versión 12.
curl.exe -i -X PATCH "http://localhost:8001/api/v1/orders/$OrderId/cancel"
curl.exe -i "http://localhost:8001/api/v1/orders/$OrderId"

# Reconstrucción autorizada, sin volver a publicar Kafka.
curl.exe -i -X POST http://localhost:8001/admin/rebuild-projections -H "X-Admin-Key: lab-admin-key"
curl.exe -i "http://localhost:8001/api/v1/orders/$OrderId"

# El evento inicial del pedido reserva UNA unidad en Inventario, eventualmente.
curl.exe -i "http://localhost:8002/api/v1/products/$ProductId"
```

Resultado esperado: creación 201; consultas y comandos válidos 200; snapshot en versión 10; total `25.00` con diez ítems; GET final `cancelled` y `X-Aggregate-Version: 12`; comandos rechazados no incrementan versión. El producto empieza con 100 y queda en 99 cuando Inventario procesa `orders.created`. Los nueve ítems agregados son únicamente eventos internos del ejercicio de snapshot. La cancelación mantiene esa reserva.

### 6.2. Bash: ejemplo equivalente

Requiere Python 3.12 para leer los UUID de las respuestas; no requiere `jq`:

```bash
curl -i http://localhost:8001/health
curl -i http://localhost:8002/health
curl -sS -X POST http://localhost:8002/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"Producto Lab03","sku":"LAB03-CURL","stock_quantity":100}' > product.json
PRODUCT_ID=$(python3.12 -c 'import json; print(json.load(open("product.json"))["id"])')
CUSTOMER_ID=$(python3.12 -c 'import uuid; print(uuid.uuid4())')
curl -sS -X POST http://localhost:8001/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d "{\"customer_id\":\"$CUSTOMER_ID\",\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1,\"unit_price\":\"2.50\"}]}" > order.json
ORDER_ID=$(python3.12 -c 'import json; print(json.load(open("order.json"))["id"])')
for n in $(seq 1 9); do
  curl -sS -X POST "http://localhost:8001/api/v1/orders/$ORDER_ID/items" \
    -H 'Content-Type: application/json' \
    -d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1,\"unit_price\":\"2.50\"}"
done
curl -i -X PATCH "http://localhost:8001/api/v1/orders/$ORDER_ID/status" \
  -H 'Content-Type: application/json' -H 'X-Expected-Version: 10' -d '{"new_status":"confirmed"}'
curl -i -X PATCH "http://localhost:8001/api/v1/orders/$ORDER_ID/status" \
  -H 'Content-Type: application/json' -H 'X-Expected-Version: 10' -d '{"new_status":"processing"}'
# La llamada anterior usa una versión obsoleta: 409.
curl -i -X PATCH "http://localhost:8001/api/v1/orders/$ORDER_ID/status" \
  -H 'Content-Type: application/json' -d '{"new_status":"shipped"}'
# confirmed -> shipped: 409.
curl -i -X PATCH "http://localhost:8001/api/v1/orders/$ORDER_ID/cancel"
curl -i -X POST http://localhost:8001/admin/rebuild-projections -H 'X-Admin-Key: lab-admin-key'
curl -i "http://localhost:8001/api/v1/orders/$ORDER_ID"
curl -i "http://localhost:8002/api/v1/products/$PRODUCT_ID"
```

### 6.3. Consultas SQL de evidencia

Sustituye `<ORDER_ID>` por el UUID generado; ejecuta cada sentencia desde `psql`:

```text
dc exec postgres psql -U lab_admin -d eventstore_db
```

```sql
SELECT aggregate_version, event_type, event_id, occurred_at, metadata
FROM events WHERE aggregate_id = '<ORDER_ID>' ORDER BY aggregate_version;

SELECT order_id, status, total_amount, event_count, last_event_id
FROM order_projections WHERE order_id = '<ORDER_ID>';

SELECT aggregate_id, aggregate_version, state, created_at
FROM snapshot_orders WHERE aggregate_id = '<ORDER_ID>';

SELECT id, topic, aggregate_version, sent_at
FROM outbox WHERE order_id = '<ORDER_ID>' ORDER BY id;
```

El historial tiene doce eventos válidos; la proyección tiene `event_count = 12`; el snapshot tiene `aggregate_version = 10` y estado correspondiente a esa versión, **no** el estado final cancelado. Por eso es necesario aplicar eventos 11 y 12 al recuperar el agregado. La outbox tiene trece filas: doce para `order-events` y una para `orders.created`. `sent_at` se completa al confirmar Kafka.

Prueba no destructiva del trigger: el UPDATE intenta asignar el mismo valor a un evento, pero debe ser rechazado:

```sql
UPDATE events SET event_type = event_type WHERE aggregate_id = '<ORDER_ID>';
-- ERROR: events is append-only
```

Las pruebas automatizadas de DELETE y TRUNCATE se ejecutan en bases temporales aisladas. No las ejecutes sobre el historial de trabajo.

## 7. Snapshots, reconstrucción y Kafka — 10 minutos

### Snapshots

El snapshot no es la fuente de verdad. Conserva estado, versión, correlación y último evento. `EventStore.load()` lee snapshot y cola dentro de una vista consistente y aplica cada evento posterior en orden. `use_snapshot=False` permite contrastar con el replay completo.

Si un lote cruza de versión 9 a 12, el snapshot debe representar la versión **10**, aunque el pedido finalmente tenga versión 12. La implementación comprueba cada frontera dentro del lote.

### Reconstrucción de proyecciones

`POST /admin/rebuild-projections`, con `X-Admin-Key`, reproduce el historial y reemplaza las proyecciones en una única transacción. Usa un bloqueo exclusivo de reconstrucción; las escrituras normales toman el bloqueo compartido equivalente. Mientras dura, las escrituras esperan y las consultas pueden observar la proyección previamente confirmada. Un fallo conserva la proyección anterior mediante rollback.

Un evento desconocido o una secuencia incompleta aborta la operación; no se omite silenciosamente. La reconstrucción no modifica eventos, no necesita snapshots, no altera la outbox y no publica otra vez `orders.created`. Reconstruye **todos** los pedidos de la base: coordina este ejercicio con otros participantes si comparten instancia. GET devuelve 405 y una clave ausente/incorrecta devuelve 403.

### Publicación Kafka

Los dos mensajes de creación comparten `event_id`, `correlation_id` y `order_id`/`aggregate_id`, pero tienen esquemas diferentes:

| Tópico | Destino | Contenido |
|---|---|---|
| `orders.created` | Inventario del laboratorio 2 | `OrderCreated` versión 1.0.0, `order_id`, cliente e ítems con producto/cantidad; conserva el contrato anterior. |
| `order-events` | Inspección del Event Store | Eventos internos con `aggregate_id`, secuencia del agregado y datos para replay. |
| `inventory.stock-reserved` | Observación de reserva | Resultado compatible con el laboratorio 2. |
| `inventory.stock-failed` | Observación de fallo | Resultado compatible con el laboratorio 2. |

El relay publica primero la fila pendiente más antigua y no la marca como enviada hasta recibir confirmación del productor. Si el broker falla, conserva la fila y reintenta. Si el proceso termina entre la confirmación Kafka y el commit PostgreSQL, puede repetir el mensaje con el mismo `event_id`. Inventario conserva la deduplicación del laboratorio 2; su registro de resultados tiene una retención de 24 horas, por lo que no se promete deduplicación ilimitada.

El laboratorio usa un solo relay activo mediante bloqueo PostgreSQL y procesamiento secuencial. Es una implementación didáctica: throughput, particionado de outbox, autenticación administrativa y saga no se presentan como soluciones de producción.

Para observar mensajes, ejecuta en otra terminal con la función `dc` definida:

```text
dc exec kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic order-events --from-beginning --timeout-ms 10000
dc exec kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic orders.created --from-beginning --timeout-ms 10000
dc exec kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic inventory.stock-reserved --from-beginning --timeout-ms 10000
```

Estos comandos leen también mensajes antiguos y terminan por timeout; un timeout del consumidor de observación no significa que la publicación haya fallado. Correlaciona los mensajes con tu pedido. El grupo de observación no reemplaza al consumidor de Inventario.

## 8. Pruebas automatizadas y criterios de aceptación

### 8.1. Ejecutar las pruebas con bases PostgreSQL temporales

El administrador de pruebas necesita crear/borrar bases de datos; usa solamente la instancia local del laboratorio. Cada caso crea una base `lab03_test_<uuid>`, aplica las migraciones reales, conecta el Store como `order_app` y elimina esa base al terminar. No borra tablas del laboratorio. Si no defines `POSTGRES_TEST_ADMIN_URL`, las pruebas PostgreSQL se omiten; esa ejecución parcial no valida el Event Store.

PowerShell:

```powershell
$env:POSTGRES_TEST_ADMIN_URL = "postgresql+asyncpg://lab_admin:lab_admin_lab_pass@localhost:5432/postgres"
$env:REDIS_TEST_URL = "redis://localhost:6379/15"
& ./order-service/.venv312/Scripts/python.exe scripts/validate.py
```

Bash:

```bash
export POSTGRES_TEST_ADMIN_URL='postgresql+asyncpg://lab_admin:lab_admin_lab_pass@localhost:5432/postgres'
export REDIS_TEST_URL='redis://localhost:6379/15'
order-service/.venv312/bin/python scripts/validate.py
```

Las pruebas Redis usan prefijos temporales; elegir la base 15 separa su espacio de la base 0 del servicio. No ejecutes suites contra infraestructura de producción.

### 8.2. Validar los servicios reales y la outbox

Con las API del paso 3 levantadas, desde la raíz:

PowerShell:

```powershell
$env:EVENTSTORE_DATABASE_URL = "postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db"
$env:EVENTSTORE_ADMIN_KEY = "lab-admin-key"
& ./order-service/.venv312/Scripts/python.exe scripts/validate_lab02.py
& ./order-service/.venv312/Scripts/python.exe scripts/validate_lab03.py
```

Bash:

```bash
export EVENTSTORE_DATABASE_URL='postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db'
export EVENTSTORE_ADMIN_KEY='lab-admin-key'
order-service/.venv312/bin/python scripts/validate_lab02.py
order-service/.venv312/bin/python scripts/validate_lab03.py
```

El primer script verifica la continuidad HTTP/Kafka/Inventario del laboratorio 2. El segundo crea un pedido específico de Event Sourcing, prueba snapshot 10 y cola 11, compara replay completo, rechaza un salto de estado, cancela, reconstruye y espera la confirmación de todas sus filas de outbox. Este segundo script usa un UUID de producto inexistente deliberadamente: Inventario responde `StockReservationFailed`; la reserva exitosa se verifica con el primer script y el ejemplo curl con producto real. No interpretes ese fallo de reserva esperado como fallo de snapshots.

### Evidencia de esta revisión

Se ejecutaron **91 pruebas aprobadas**: 39 de Pedidos y 52 de Inventario. De Pedidos, 19 conservan regresiones del modo anterior y 20 verifican el modo Event Store con PostgreSQL 16.3 real y migraciones reales. Inventario incluye 11 pruebas con Redis 7.2.5 real. Se comprobaron atomicidad, permisos y triggers, escritura concurrente, replay, fronteras de snapshot, reconstrucción y relay con fallo/reintento mediante productor simulado. También se validaron ambos contratos OpenAPI.

**Límite de la validación:** no se ejecutó Docker Compose ni un broker Kafka real en el entorno de revisión. Los scripts del apartado 8.2 permiten completar esa comprobación en tu equipo. Las pruebas de outbox con productor simulado no equivalen a una ejecución Kafka de extremo a extremo. Las advertencias de deprecación proceden de Schemathesis y su pila fijada de pruebas.

### Entregables del participante

| Evidencia | Criterio de aceptación |
|---|---|
| Historial SQL | Versiones 1 a 12, sin eventos de comandos rechazados. |
| Inmutabilidad | UPDATE inocuo rechazado; suite también verifica DELETE/TRUNCATE en bases temporales. |
| Consulta CQRS | GET coincide con `order_projections`; no recurre al historial si falta la proyección. |
| Snapshot y replay | Snapshot versión 10; snapshot + cola equivale al replay completo. |
| Reconstrucción | Estado visible igual antes/después; eventos y outbox no crecen. |
| Concurrencia | Versión obsoleta devuelve 409; no hay versiones repetidas. |
| Kafka e Inventario | Creación compatible, reserva inicial única y outbox confirmada. |
| Ejecución | Pruebas PostgreSQL y Redis sin omisiones; scripts reales aprobados. |

## 9. Ejecución opcional desde el host

Para editar y ejecutar Uvicorn fuera de Docker, conserva solamente la infraestructura del paso 3 y detén las API contenedorizadas con `dc stop order-service inventory-service`. Aplica las migraciones antes de iniciar Pedidos. En PowerShell, una terminal para Pedidos:

```powershell
$env:EVENTSTORE_ENABLED = "true"
$env:MESSAGING_ENABLED = "true"
$env:EVENTSTORE_DATABASE_URL = "postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db"
$env:EVENTSTORE_ADMIN_KEY = "lab-admin-key"
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:29092"
$env:PYTHONPATH = $PWD.Path
& ./order-service/.venv312/Scripts/python.exe -m uvicorn app.main:app --app-dir order-service --port 8001
```

En otra terminal PowerShell, desde la misma raíz:

```powershell
$env:MESSAGING_ENABLED = "true"
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:29092"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:PYTHONPATH = $PWD.Path
& ./inventory-service/.venv312/Scripts/python.exe -m uvicorn app.main:app --app-dir inventory-service --port 8002
```

En Bash usa las mismas variables con `export` y los intérpretes `.venv312/bin/python`. Para migrar desde el host, define `EVENTSTORE_ADMIN_DATABASE_URL` apuntando al puerto local 5432 y ejecuta `python -m alembic upgrade head` desde `order-service` con su intérprete. Si omites `EVENTSTORE_ENABLED=true`, `app.main` inicia el modo anterior: no valida este laboratorio.

## 10. Diagnóstico y cierre

| Síntoma | Qué comprobar |
|---|---|
| `pydantic-core` intenta compilar/falla | Intérprete real 3.12, entorno nuevo de esa versión y requisitos completos. |
| `/health` de Pedidos devuelve 503 | Migraciones, URL/credenciales, tópicos creados, Kafka y logs del relay. |
| `role order_app does not exist` | Inicialización del volumen PostgreSQL; ejecutar el SQL de roles como administrador y migrar. |
| `relation events does not exist` | Ejecutar `alembic upgrade head` contra la misma base usada por la API. |
| No hay snapshots después de crear muchos pedidos | El umbral es por **pedido**, no el conteo global; un pedido debe alcanzar versión 10. |
| Total o proyección cambian tras rebuild | Consultar el mismo pedido, verificar historial y versión; ejecutar la comparación automatizada. |
| Outbox pendiente | Disponibilidad de Kafka, tópico `order-events`, errores del productor y relay activo. |
| Inventario no reserva ítems agregados | Comportamiento explícito del alcance: solo la creación solicita reserva. |
| 409 al cambiar estado | Revisar transición permitida y cabecera de versión esperada. |
| Pruebas aprobadas con `skipped` | Faltan URL PostgreSQL/Redis o infraestructura; no es una validación completa. |

Para detener sin perder datos:

```text
dc down
```

Los volúmenes conservan PostgreSQL, Redis y Kafka. No uses `TRUNCATE events`, `DELETE events`, ni comandos que terminen todos los procesos Uvicorn del equipo. Para reiniciar completamente **solo este proyecto de práctica**, `dc down -v` elimina todos sus volúmenes; hazlo únicamente cuando quieras perder eventos, reservas y mensajes juntos.

### Referencias técnicas

- [PostgreSQL 16: triggers y TRUNCATE](https://www.postgresql.org/docs/16/sql-createtrigger.html).
- [PostgreSQL 16: bloqueos consultivos de transacción](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS).
- [SQLAlchemy 2: sesiones asíncronas y concurrencia](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html).
- [Alembic: uso con AsyncIO](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
