# Laboratorio 4 — Circuit Breaker, retries, bulkhead y degradación controlada

**Curso:** Microservicios Avanzado · **Duración:** 66 minutos con el entorno preparado · **Complejidad:** alta · **Bloom:** aplicar.

**Punto de partida:** laboratorio 3 corregido, con Event Store PostgreSQL, proyecciones, snapshots, outbox, Kafka e Inventario con Redis. La instalación inicial de paquetes/imágenes queda fuera de los 66 minutos.

## 1. Resultado esperado y arquitectura

Pedidos consulta stock por HTTP antes de crear un pedido. La llamada se protege con reintentos, circuit breaker persistido en Redis y un semáforo que limita trabajos admitidos. Se conserva la escritura transaccional y la reserva por Kafka de los laboratorios anteriores. La consulta HTTP es una comprobación preliminar: **no reserva ni garantiza stock**.

```mermaid
flowchart TD
    Cliente["Cliente"] --> Pedidos["API de Pedidos"]
    Pedidos --> Proteccion["Bulkhead, breaker y retry"]
    Proteccion --> Consulta["GET de producto"]
    Consulta --> Inventario["Inventario real"]
    Consulta -. "Modo caos" .-> Mock["Mock aislado en 8003"]
    Proteccion --> Circuito["Estado del circuito en Redis"]
    Pedidos --> Decision{"Resultado preliminar"}
    Decision -->|"Insuficiente conocido"| Rechazo["409, sin escritura"]
    Decision -->|"Suficiente o desconocido"| Persistencia["Event Store y outbox"]
    Persistencia --> Kafka["orders.created"]
    Kafka --> Inventario
    Inventario --> Reserva["Reserva atómica en Redis"]
```

El mock no reemplaza Inventario en el puerto 8002 y no ejecuta su consumidor Kafka. Las pruebas de caos consultan el mock, pero no crean pedidos usando su stock ficticio.

### Objetivos conservados

| Objetivo original | Implementación y evidencia |
|---|---|
| Retry con backoff exponencial y jitter mediante Tenacity | Hasta tres intentos de GET para fallos transitorios; dos fallos seguidos de éxito en el tercero. |
| Circuit breaker PyBreaker con estado en Redis | `CircuitRedisStorage`, umbral de fallos, apertura, bloqueo y recuperación automática half-open. |
| Bulkhead con `asyncio.Semaphore` | Admisión limitada y espera corta; rechazos por saturación y liberación comprobada incluso al cancelar el solicitante. |
| Degradación controlada | `available: null`, `quantity: null`, causa explícita; creación diferida como pedido pendiente. |
| Observabilidad | Estado, contador, configuración, transiciones recientes y estadísticas del bulkhead; reset administrativo. |

### Correcciones importantes

| Problema del material original | Corrección |
|---|---|
| Ruta de stock inexistente y productos como `PROD-001` | Usa `GET /api/v1/products/{UUID}` y el campo `stock_quantity` de Inventario. |
| Llamada a `_sync_wrapper_check_stock` sin implementar y métodos privados inexistentes | Usa exclusivamente la API pública `breaker.call()`. |
| Aplicación alternativa sin pedidos ni Event Store | Extiende `create_cqrs_app`; mantiene todos los endpoints, migraciones y outbox. |
| Storage JSON incompleto, operaciones no atómicas y fechas incompatibles | Storage Redis provisto por PyBreaker, con respuestas bytes y namespace independiente. |
| Fallback inventa disponibilidad positiva y cantidad -1 | Disponibilidad desconocida representada con null; no se afirma que existe stock. |
| Recuperación simulada mediante reset manual | Se espera el cooldown y se verifican transiciones reales open → half-open → closed. |
| Script imprime éxito aunque falle una condición | Verificaciones explícitas que provocan salida no cero ante cualquier fallo. |
| Mock ocupa 8002, se matan procesos ajenos y se usa FLUSHDB | Mock en 8003; parada del proyecto y limpieza acotada a claves de pruebas. |

## 2. Preparación — 8 minutos

Descomprime `Lab04_Microservicios_Avanzado_materiales.zip` en una carpeta nueva. El paquete contiene ambos servicios completos. Trabaja desde `microservices-lab`, junto a los archivos Compose. Si actualizas tu proyecto anterior, conserva sus volúmenes y sustituye el código con las API detenidas. Este laboratorio no añade migraciones: sigue usando `002_append_only` del laboratorio 3.

Usa Python **3.12**, los entornos `.venv312` y los requisitos fijados. Pedidos añade:

```text
httpx==0.27.0
tenacity==8.3.0
pybreaker==1.2.0
```

Inventario conserva sus requisitos anteriores; no necesita PyBreaker ni Tenacity porque la llamada protegida sale de Pedidos. La comprobación de versiones usa `importlib.metadata`, no atributos `__version__` que esas librerías pueden no exponer.

PowerShell, sin depender del lanzador `py`:

```powershell
# Ajusta esta ruta si tu Python 3.12 está instalado en otra ubicación.
$Python312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $Python312 --version
# Solo si aún no existen entornos de Python 3.12:
& $Python312 -m venv order-service/.venv312
& $Python312 -m venv inventory-service/.venv312
& ./order-service/.venv312/Scripts/python.exe -m pip install -r order-service/requirements-dev.txt
& ./inventory-service/.venv312/Scripts/python.exe -m pip install -r inventory-service/requirements-dev.txt
& ./order-service/.venv312/Scripts/python.exe -m pip check
& ./order-service/.venv312/Scripts/python.exe scripts/preflight.py --resilience
```

Bash:

```bash
python3.12 -m venv order-service/.venv312
python3.12 -m venv inventory-service/.venv312
order-service/.venv312/bin/python -m pip install -r order-service/requirements-dev.txt
inventory-service/.venv312/bin/python -m pip install -r inventory-service/requirements-dev.txt
order-service/.venv312/bin/python -m pip check
order-service/.venv312/bin/python scripts/preflight.py --resilience
```

Si ya existen entornos correctos, omite su creación. Un entorno de Python 3.13 no se convierte en uno de 3.12 al cambiarle el nombre.

## 3. Arranque normal y continuidad — 10 minutos

Define una función para usar siempre los cuatro archivos. En PowerShell:

```powershell
function dc { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml -f docker-compose.resilience.yml @args }
```

En Bash:

```bash
dc() { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml -f docker-compose.resilience.yml "$@"; }
```

Los comandos siguientes son comunes a ambas terminales:

```text
dc config
dc build order-service inventory-service
dc up -d postgres zookeeper kafka redis
dc ps
```

Si reutilizas el laboratorio 3, espera a que la infraestructura esté saludable y confirma las migraciones. Si partes de volúmenes nuevos, crea los cuatro tópicos y aplica las migraciones:

```text
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic orders.created --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic inventory.stock-reserved --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic inventory.stock-failed --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic order-events --partitions 3 --replication-factor 1
dc run --rm --no-deps -e EVENTSTORE_ADMIN_DATABASE_URL=postgresql+asyncpg://lab_admin:lab_admin_lab_pass@postgres:5432/eventstore_db order-service python -m alembic upgrade head
dc run --rm --no-deps -e EVENTSTORE_ADMIN_DATABASE_URL=postgresql+asyncpg://lab_admin:lab_admin_lab_pass@postgres:5432/eventstore_db order-service python -m alembic current
dc up -d order-service inventory-service
dc ps
```

Debe aparecer `002_append_only (head)`. No se requiere un contenedor creado manualmente con nombre `mslab-postgres`. El SQL inicial de roles solo se ejecuta en un volumen PostgreSQL nuevo; si reutilizas otro volumen, comprueba que existe `order_app`.

### Configuración normal

| Variable | Valor en Compose | Significado |
|---|---|---|
| `EVENTSTORE_ENABLED` | true | Mantener persistencia/CQRS del lab 3. |
| `MESSAGING_ENABLED` | true | Mantener Kafka y relay de outbox. |
| `RESILIENCE_ENABLED` | true | Activar cliente y endpoints del lab 4. |
| `INVENTORY_BASE_URL` | http://inventory-service:8002 | Destino HTTP real. |
| `RESILIENCE_REDIS_URL` | redis://redis:6379/1 | Estado de circuitos, separado de Inventario DB 0. |
| `RESILIENCE_NAMESPACE` | lab04:orders:normal:inventory | Identidad estable del circuito. |
| `RESILIENCE_FAIL_MAX` | 5 | Cinco operaciones lógicas fallidas abren el circuito. |
| `RESILIENCE_RESET_TIMEOUT` | 30 | Cooldown en segundos. |
| `RESILIENCE_MAX_CONCURRENT` | 10 | Máximo de trabajos admitidos, activos o esperando el breaker. |
| `RESILIENCE_HTTP_TIMEOUT` | 1, por defecto | Timeout por fase de HTTPX. |
| `RESILIENCE_ACQUIRE_TIMEOUT` | 0.1, por defecto | Espera máxima para obtener un slot. |

Para arrancar fuera de Docker utiliza las URL locales `localhost:8002`, `localhost:6379/1`, `localhost:5432` y `localhost:29092`. No uses los nombres DNS internos `redis`, `postgres` o `inventory-service` desde el host.

## 4. Implementación de los patrones — 14 minutos

### Archivos a revisar

| Archivo desde la raíz | Responsabilidad |
|---|---|
| `shared/resilience/retry_policies.py` | Clasificar fallos y configurar Tenacity. |
| `shared/resilience/circuit_breaker_registry.py` | Singleton por cliente, storage Redis y transiciones. |
| `shared/resilience/bulkhead.py` | Semáforo, admisión y estadísticas. |
| `order-service/app/clients/inventory_client.py` | Cliente HTTP, adaptación async y fallback. |
| `order-service/app/routers/resilience.py` | Consulta y administración de circuitos. |
| `order-service/app/routers/cqrs.py` | Consulta preliminar antes de crear pedidos. |
| `order-service/app/cqrs_app.py` | Integración y cierre del cliente sin reemplazar CQRS. |

### Retry: tres intentos totales

Se reintenta únicamente el GET de producto, nunca el POST de creación ni la reserva. Hay **tres intentos totales**, es decir, un intento inicial y hasta dos reintentos. Tenacity usa `wait_random_exponential(multiplier=0.1, max=0.5)` y `reraise=True`.

| Resultado de la dependencia | Retry | Resultado para el cliente |
|---|---|---|
| 200 válido | No | Disponibilidad y cantidad observadas. |
| 404 | No | Producto inexistente, cantidad 0; no cuenta como fallo del circuito. |
| 408, 429, 500, 502, 503, 504 | Hasta tres intentos | Si se agotan, disponibilidad desconocida. |
| Error de transporte/timeout HTTPX | Hasta tres intentos | Si se agotan, disponibilidad desconocida. |
| Otros estados inesperados o JSON inválido | No | Disponibilidad desconocida; cuenta como fallo de integración. |
| Error de programación | No | Se propaga; no se disfraza como disponibilidad. |

### Circuit breaker: contar operaciones lógicas

El orden es **bulkhead → breaker → retry → GET**. El breaker envuelve la política completa: tres HTTP 503 dentro de una consulta cuentan como **un fallo lógico**, no tres. Con `fail_max=5`, cinco consultas agotadas pueden generar quince intentos HTTP antes de abrir. Una consulta bloqueada por circuito abierto hace cero intentos.

```mermaid
stateDiagram-v2
    [*] --> closed
    closed --> open: umbral de fallos
    open --> half_open: próxima llamada tras cooldown
    half_open --> closed: prueba exitosa
    half_open --> open: prueba fallida
```

El estado half-open aparece al llegar una llamada después del cooldown; no hay un temporizador que cierre el circuito por sí solo. El reset manual es una operación distinta y no demuestra recuperación automática.

Redis usa `CircuitRedisStorage` con `decode_responses=False`. Guarda claves con prefijo `lab04:orders:normal:inventory:pybreaker:`. Mantener el namespace permite recuperar el estado al reiniciar el proceso; cambiarlo crea otra identidad. Si Redis no está disponible al consultar, el resultado indica `resilience_storage_unavailable`; la observabilidad responde 503. No se ofrece una garantía de persistencia durante una caída de Redis.

### Adaptación de PyBreaker y concurrencia

PyBreaker 1.2.0 es síncrono. Para conservar esa librería y su API pública, el bloque completo de HTTPX `Client` y Tenacity se ejecuta mediante `asyncio.to_thread`. El endpoint sigue siendo asíncrono y el event loop puede atender otras tareas. No se pasa una coroutine sin ejecutar a `breaker.call()` ni se utilizan métodos privados para registrar éxito/fallo.

Esta versión de PyBreaker mantiene un `RLock` durante `call()`: **las llamadas HTTP protegidas por un mismo breaker se serializan**. Por ello, `max_concurrent=10` limita diez trabajos admitidos, incluyendo los que esperan ese bloqueo; no promete diez GET simultáneos. Este límite y el rechazo bajo carga son observables. Para desarrollar después una variante con HTTP nativamente asíncrono y mayor paralelismo, habría que escoger un breaker compatible y volver a probar sus transiciones.

El slot se libera cuando termina realmente el trabajo. Cancelar el solicitante no detiene automáticamente un thread; liberar antes el slot permitiría superar el límite. El cliente protege el trabajo con `asyncio.shield` y libera mediante callback de finalización. El cierre espera los trabajos admitidos antes de cerrar HTTP y Redis.

**Alcance:** una instancia y un worker para este laboratorio. Redis conserva estado, pero no convierte el bloqueo local ni el semáforo en mecanismos distribuidos. No se afirma que varias réplicas compartan un único probe half-open seguro.

### Fallback y creación de pedidos

Una respuesta degradada expresa:

```json
{
  "product_id": "11111111-1111-4111-8111-111111111111",
  "available": null,
  "quantity": null,
  "source": "fallback",
  "reason": "circuit_open",
  "attempts": 0
}
```

`null` significa desconocido. `false` con cantidad 0 significa una respuesta conocida sin disponibilidad; no son equivalentes.

Al crear un pedido se suman las cantidades de líneas repetidas del mismo producto y se consulta una vez cada UUID. Si el stock conocido es insuficiente, retorna 409 `INSUFFICIENT_STOCK`; un producto inexistente retorna 409 `PRODUCT_NOT_AVAILABLE`. No se escribe evento, proyección ni outbox.

Si todas las consultas son conocidas y suficientes, se crea el pedido con cabecera `X-Stock-Precheck: verified`. Si alguna es desconocida, se permite persistirlo como `pending` con `X-Stock-Precheck: deferred`. Se conserva el cuerpo y el estado 201. En ambos casos la reserva efectiva depende del consumidor Kafka; una consulta previa exitosa puede quedar obsoleta antes de reservar.

Este laboratorio sigue sin saga: `StockReserved` no confirma automáticamente pedidos, cancelar no libera reservas y agregar ítems no solicita reservas adicionales.

## 5. Pruebas normales con curl — 8 minutos

PowerShell usa `curl.exe` y archivos UTF-8 sin BOM para evitar errores de alias y comillas:

```powershell
$Utf8 = [System.Text.UTF8Encoding]::new($false)
function jsonFile($Nombre,$Objeto) {
    [System.IO.File]::WriteAllText((Join-Path $PWD $Nombre),($Objeto | ConvertTo-Json -Depth 10),$Utf8)
}
curl.exe -i http://localhost:8001/health
curl.exe -i http://localhost:8002/health
curl.exe -i http://localhost:8001/health/circuit-breakers

jsonFile product.json @{name="Producto Lab04"; sku=("LAB04-"+[guid]::NewGuid().ToString().ToUpper()); stock_quantity=10}
$product = curl.exe -sS -X POST http://localhost:8002/api/v1/products -H "Content-Type: application/json" --data-binary "@product.json" | ConvertFrom-Json
$ProductId = $product.id
curl.exe -i "http://localhost:8001/api/v1/orders/check-stock/$ProductId"

jsonFile order.json @{customer_id=[guid]::NewGuid().ToString(); items=@(@{product_id=$ProductId; quantity=2; unit_price="3.50"})}
curl.exe -i -X POST http://localhost:8001/api/v1/orders -H "Content-Type: application/json" --data-binary "@order.json"

# Cantidad superior al stock: 409, sin persistencia.
jsonFile insufficient.json @{customer_id=[guid]::NewGuid().ToString(); items=@(@{product_id=$ProductId; quantity=100; unit_price="3.50"})}
curl.exe -i -X POST http://localhost:8001/api/v1/orders -H "Content-Type: application/json" --data-binary "@insufficient.json"

# UUID válido inexistente: consulta conocida no disponible.
$MissingId = [guid]::NewGuid().ToString()
curl.exe -i "http://localhost:8001/api/v1/orders/check-stock/$MissingId"

# Reset administrativo: requiere la misma clave del lab 3.
curl.exe -i -X POST http://localhost:8001/health/circuit-breakers/inventory-service/reset -H "X-Admin-Key: lab-admin-key"
curl.exe -i -X POST http://localhost:8001/health/circuit-breakers/inventory-service/reset
```

Resultado esperado: consulta normal 200, `available=true`, cantidad 10 y un intento; creación 201 con estado pending, total `7.00` y precheck verified; stock efectivo eventualmente 8 al procesar Kafka; pedido insuficiente 409; consulta de UUID inexistente 200 con false/0; reset autorizado 200 y sin clave 403.

Bash, usando un UUID real obtenido al crear el producto:

```bash
curl -i http://localhost:8001/health/circuit-breakers
curl -sS -X POST http://localhost:8002/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"Producto Lab04","sku":"LAB04-CURL","stock_quantity":10}' > product.json
PRODUCT_ID=$(python3.12 -c 'import json; print(json.load(open("product.json"))["id"])')
CUSTOMER_ID=$(python3.12 -c 'import uuid; print(uuid.uuid4())')
curl -i "http://localhost:8001/api/v1/orders/check-stock/$PRODUCT_ID"
curl -i -X POST http://localhost:8001/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d "{\"customer_id\":\"$CUSTOMER_ID\",\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":2,\"unit_price\":\"3.50\"}]}"
curl -i -X POST http://localhost:8001/health/circuit-breakers/inventory-service/reset \
  -H 'X-Admin-Key: lab-admin-key'
```

## 6. Inyección de fallos y pruebas de caos — 12 minutos

Define una segunda función con el overlay de caos al final. PowerShell:

```powershell
function dchaos { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml -f docker-compose.resilience.yml -f docker-compose.chaos.yml @args }
```

Bash:

```bash
dchaos() { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml -f docker-compose.resilience.yml -f docker-compose.chaos.yml "$@"; }
```

Arranca el mock y recrea Pedidos con su destino de prueba:

```text
dchaos config
dchaos up -d --build inventory-mock order-service
dchaos ps
```

El modo caos cambia solamente el destino de las consultas HTTP preliminares y la identidad/configuración del circuito. Inventario real sigue en 8002 con sus datos y su consumidor Kafka. Usa namespace `lab04:orders:chaos:inventory`, umbral 3, cooldown 3 segundos, tres slots y timeout HTTP de 0.3 segundos. Es una configuración rápida para observar los mismos patrones.

**Durante el modo caos ejecuta consultas de stock y observabilidad. No crees pedidos basándote en el stock ficticio del mock.** La reserva real seguiría resolviéndose con Inventario real y podría contradecirlo.

### Script automático

PowerShell:

```powershell
& ./order-service/.venv312/Scripts/python.exe scripts/chaos_test.py
if ($LASTEXITCODE -ne 0) { throw "Falló una condición de resiliencia" }
```

Bash:

```bash
order-service/.venv312/bin/python scripts/chaos_test.py
```

El script comprueba que el namespace y los parámetros son los del modo caos antes de modificar el circuito. Todas sus condiciones lanzan un error si fallan, incluso ejecutándolo con `python -O`. Al finalizar debe indicar **7 ESCENARIOS HTTP DE CAOS APROBADOS**.

| Escenario | Evidencia requerida |
|---|---|
| Operación normal | Stock 100 y un intento. |
| Dos fallos transitorios | Tres solicitudes reales, éxito en la tercera. |
| Apertura y bloqueo | Tres fallos lógicos, nueve intentos HTTP; la siguiente consulta añade cero solicitudes al mock. |
| Recuperación automática | Cooldown y transiciones open → half-open → closed, sin reset para recuperar. |
| Timeout HTTP | Mock demora 0.8 s; cliente con 0.3 s agota tres intentos y devuelve desconocido. |
| Producto inexistente | 404 hace un intento, retorna false/0 y deja contador de fallos en cero. |
| Saturación | Nueve consultas concurrentes frente a tres slots; al menos seis rechazos y ningún slot perdido. |

El script espera a que las llamadas del mock terminen antes de reconfigurarlo. Un timeout del cliente no implica que el servidor remoto haya cancelado su trabajo; por ello el bulkhead acota trabajos locales y no garantiza cancelar solicitudes ya recibidas por la dependencia.

### curl de inspección del modo caos

En PowerShell, reutiliza `jsonFile` del paso 5:

```powershell
jsonFile mock.json @{status_code=503}
curl.exe -i -X POST http://localhost:8003/admin/config -H "Content-Type: application/json" --data-binary "@mock.json"
curl.exe -i -X POST http://localhost:8001/health/circuit-breakers/inventory-service/reset -H "X-Admin-Key: lab-admin-key"
$TestId = [guid]::NewGuid().ToString()
1..3 | ForEach-Object { curl.exe -sS "http://localhost:8001/api/v1/orders/check-stock/$TestId" }
curl.exe -i http://localhost:8001/health/circuit-breakers
curl.exe -i http://localhost:8003/admin/stats
curl.exe -i "http://localhost:8001/api/v1/orders/check-stock/$TestId"

# Restablecer el mock y esperar recuperación automática.
jsonFile mock.json @{status_code=200}
curl.exe -i -X POST http://localhost:8003/admin/config -H "Content-Type: application/json" --data-binary "@mock.json"
Start-Sleep -Seconds 4
curl.exe -i "http://localhost:8001/api/v1/orders/check-stock/$TestId"
curl.exe -i http://localhost:8001/health/circuit-breakers
```

Si las llamadas manuales tardan más que el cooldown, puede haber nuevos probes y variar el número de intentos. Para evidencia estricta usa el script automático.

### Volver al Inventario real

```text
dchaos stop inventory-mock
dchaos rm -f inventory-mock
dc up -d --force-recreate order-service
dc ps
```

Comprueba que observabilidad vuelve a mostrar el namespace `normal` y que el GET utiliza el producto real. No borres volúmenes para cambiar entre modos.

## 7. Tests y continuidad — 10 minutos

Las pruebas completas necesitan PostgreSQL y Redis locales. PostgreSQL usa bases temporales `lab03_test_<UUID>` creadas y eliminadas por cada caso; se conserva el nombre de fixture del laboratorio 3. No se eliminan las tablas de trabajo. Redis utiliza prefijos únicos para las pruebas.

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

Sin esas variables se omiten pruebas de infraestructura; esa ejecución parcial no valida el conjunto completo. El rol administrador de pruebas debe tener permisos para crear/borrar bases y se utiliza únicamente sobre la instancia de práctica.

Para probar continuidad con HTTP y Kafka reales, **vuelve al modo normal** y ejecuta:

```powershell
$env:EVENTSTORE_DATABASE_URL = "postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db"
& ./order-service/.venv312/Scripts/python.exe scripts/validate_lab02.py
& ./order-service/.venv312/Scripts/python.exe scripts/validate_lab03.py
```

En Bash exporta la misma variable y usa los intérpretes `bin/python`. El script del laboratorio 3 se actualizó para crear un producto real antes del pedido: el precheck del laboratorio 4 rechaza ahora los UUID inexistentes conocidos. Sus objetivos de snapshot, replay, rebuild y outbox se conservan.

### Verificación realizada en esta revisión

- 73 pruebas de Pedidos: 19 regresiones del modo anterior, 20 del Event Store/CQRS, 28 de resiliencia y 6 de integración entre precheck y Event Store.
- 52 pruebas de Inventario, incluyendo Redis real.
- Siete escenarios de caos mediante procesos HTTP reales de Pedidos y mock, con Redis real: no solo transporte simulado.
- Contratos OpenAPI válidos, sintaxis de los módulos y dependencias consistentes.

PostgreSQL 16.3 y Redis 7.2.5 se ejecutaron en instancias temporales. En las pruebas HTTP de caos no se conectó Kafka ni se ejercitaron escrituras de negocio; esas escrituras se verificaron por separado contra PostgreSQL. **Docker Compose y Kafka de extremo a extremo quedan pendientes de ejecución en tu equipo.** No se presenta la inspección de configuración como prueba de contenedores levantados.

Las advertencias de deprecación de PyBreaker 1.2.0 y Schemathesis corresponden a las versiones fijadas; no se corrigieron mediante una actualización indiscriminada que alterara los laboratorios anteriores.

### Criterios de aceptación

| Evidencia | Resultado esperado |
|---|---|
| Precheck normal | Ruta y UUID correctos; stock observado coincide con Inventario. |
| Retry | Tres intentos totales y esperas con jitter; no reintenta 404 ni creación. |
| Circuito persistente | Reiniciar cliente con el mismo namespace conserva open; reset vuelve a closed. |
| Recuperación | Probe half-open auténtico; éxito cierra y fallo vuelve a abrir. |
| Saturación/cancelación | Rechazo explícito; slots permanecen ocupados hasta finalizar el worker real. |
| Fallback | Nunca inventa cantidad ni disponibilidad positiva. |
| CQRS/Event Store | Rechazo conocido no escribe datos; aceptación conserva evento, proyección y outbox atómicos. |
| Kafka | La comprobación HTTP no sustituye la reserva ni cambia el contrato orders.created. |
| Observabilidad | Contadores coherentes; reset protegido y circuito inexistente devuelve 404. |

## 8. Diagnóstico y cierre — 4 minutos

| Síntoma | Comprobación |
|---|---|
| Importación `resilience` falla | Importar `shared.resilience`; iniciar desde la raíz del proyecto, sin rutas absolutas `/root/...`. |
| `PROD-001` devuelve 422 | El contrato exige UUID; obtenerlo de la API de productos. |
| Stock siempre cero | Leer `stock_quantity`, no `quantity`, de Inventario. |
| Circuito no abre tras tres errores HTTP | Cuenta fallos lógicos después de agotar retries; comprobar umbral normal/caos. |
| Sigue open después del cooldown | Se necesita una llamada de prueba; consultar estado no cierra el circuito. |
| HTTP GET se serializa | Comportamiento documentado de `pybreaker.call()`; el semáforo limita trabajos admitidos. |
| Mock devuelve 409 al configurar | Quedan llamadas activas tras timeouts; esperar `/admin/stats.active=0`. |
| `/health` es saludable pero circuito está open | Health del lab 3 verifica DB/Kafka; el circuito de consulta se observa por separado. |
| Pedidos desaparece o no hay snapshots | Confirmar `EVENTSTORE_ENABLED=true`; no iniciar una aplicación alternativa sin CQRS. |
| Solo funciona dentro de Docker | Revisar URLs DNS internas frente a localhost del host. |

Para detener y conservar datos, vuelve al modo normal y ejecuta:

```text
dc down
```

No uses `FLUSHDB`, `FLUSHALL`, `TRUNCATE events`, ni comandos que maten todos los procesos de los puertos. Las pruebas limpian solo sus claves. `dc down -v` borra los datos del proyecto y queda reservado para un reinicio completo deliberado.

### Referencias técnicas

- [PyBreaker 1.2.0: API pública y storage Redis](https://pypi.org/project/pybreaker/1.2.0/).
- [Código y documentación del proyecto PyBreaker](https://github.com/danielfm/pybreaker).
- [Tenacity: políticas de retry](https://tenacity.readthedocs.io/).
- [HTTPX: timeouts](https://www.python-httpx.org/advanced/timeouts/).
- [Python: asyncio.to_thread](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.to_thread).
