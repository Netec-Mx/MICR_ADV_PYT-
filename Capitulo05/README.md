# Laboratorio 5 · Seguridad de APIs con OAuth 2.0, JWT y Keycloak

**Curso:** Microservicios Avanzado · **Nivel:** alto · **Bloom:** aplicar.
**Duración orientativa:** 66 minutos, después de descargar imágenes y preparar Python.
**Base:** laboratorios 1–4 corregidos. El ZIP adjunto incluye la solución completa.

## Resultado esperado y objetivos

1. Configurar un realm y clientes confidenciales con roles para Orders e Inventory.
2. Validar tokens de acceso JWT RS256 usando JWKS, issuer y audiencia.
3. Exigir conjuntamente scopes y roles en los endpoints.
4. Autenticar automáticamente Orders → Inventory mediante Client Credentials.
5. Probar tokens ausentes, inválidos, expirados y permisos insuficientes.

Se conservan las rutas `/api/v1`, UUID, importes Decimal, pedido inicial `pending`, EventStore/CQRS, outbox, Kafka, Redis, retries, circuit breaker y bulkhead. El JWT del usuario no se reenvía a Inventory: Orders usa su propia identidad de servicio. Kafka mantiene sus contratos del laboratorio 2.

```mermaid
flowchart TD
  U["Usuario: Authorization Code + PKCE"] --> K["Keycloak · realm microservices-lab"]
  K -->|"JWT: orders.read / orders.write"| O["Orders · :8001"]
  O -->|"Client Credentials: inventory.read"| K
  O -->|"Bearer de servicio + resiliencia"| I["Inventory · :8002"]
  K -->|"JWKS: firma RS256"| I
  K -->|"JWKS: firma RS256"| O
  O --> E["PostgreSQL · eventos / proyección / outbox"]
  E -->|"Relay"| B["Kafka · contratos Lab 2"]
  B --> I
  I --> R["Redis · stock / reservas / idempotencia"]
```

La consulta HTTP verifica stock; la reserva efectiva se procesa por Kafka. Una consulta degradada conserva el comportamiento del Lab 4 (`X-Stock-Precheck: deferred`). Un fallo de credenciales o autorización del servicio devuelve **503 y bloquea la escritura**: no puede convertirse en fallback de negocio.

## 0. Preparación y versiones

Extrae `microservices-lab` del ZIP y abre una terminal en esa carpeta. Usa Docker Desktop con Compose v2 y **Python 3.12**. No reutilices el entorno Python 3.13 del laboratorio original.

PowerShell, sin depender del comando `py`:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python --version
python -m pip install -r order-service/requirements-dev.txt
python -m pip check
python scripts/preflight.py --auth
```

Si Python está en otra ruta, sustituye únicamente la ruta del ejecutable. En Linux/macOS:

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r order-service/requirements-dev.txt
python -m pip check
python scripts/preflight.py --auth
```

Se mantienen las dependencias funcionales probadas de los labs anteriores y se añaden **PyJWT[crypto] 2.15.1** y **cryptography 50.0.2** en ambos servicios. Keycloak se fija en **26.8.0**. El laboratorio original usaba python-jose 3.3.0; esta revisión reemplaza ese validador y sus opciones permisivas. No mezcles ambos validadores ni actualices paquetes individualmente durante la práctica.

## 1. Realm y arranque completo · 12 minutos

La configuración declarativa está en `scripts/keycloak/setup_realm.py`. Regenera el import antes de arrancar:

```powershell
python scripts/keycloak/setup_realm.py
function dc { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml -f docker-compose.resilience.yml -f docker-compose.auth.yml @args }
dc config --quiet
dc up -d postgres redis zookeeper kafka keycloak-db keycloak
```

Equivalente Bash:

```bash
dc() { docker compose -f docker-compose.yml -f docker-compose.kafka.yml -f docker-compose.eventstore.yml -f docker-compose.resilience.yml -f docker-compose.auth.yml "$@"; }
dc config --quiet
dc up -d postgres redis zookeeper kafka keycloak-db keycloak
```

Espera a que la infraestructura esté saludable (`dc ps`). Abre <http://localhost:8080>; administrador de Keycloak: `admin` / `admin_lab_pass`. Comprueba el realm **microservices-lab** y sus clientes, roles y scopes.

Keycloak usa su propio PostgreSQL y volumen; no reutiliza el usuario ni la base de EventStore. `/health/ready` de Keycloak está en el puerto **9000**. La comprobación de salud usa Bash porque la imagen de Keycloak no incluye curl.

Si ya existe el realm, `--import-realm` **no lo sobrescribe**. Para aplicar una configuración anterior corregida, elimina únicamente ese realm desde la consola y reinicia Keycloak; perderás sus usuarios y tokens de práctica. Conserva los volúmenes de negocio. No ejecutes `down -v` para actualizar el laboratorio.

Completa topics y migraciones antes de iniciar los microservicios:

```powershell
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic orders.created --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic inventory.stock-reserved --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic inventory.stock-failed --partitions 3 --replication-factor 1
dc exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic order-events --partitions 3 --replication-factor 1
dc build order-service inventory-service
dc run --rm --no-deps -e EVENTSTORE_ADMIN_DATABASE_URL=postgresql+asyncpg://lab_admin:lab_admin_lab_pass@postgres:5432/eventstore_db order-service python -m alembic upgrade head
dc up -d --build order-service inventory-service
dc ps
```

Los mismos comandos `dc` funcionan en Bash. La migración se ejecuta dentro del contenedor con la conexión administrativa; el servicio utiliza el rol restringido `order_app`. Si continúas con la base del Lab 4 ya migrada, `upgrade head` conserva los datos y no reaplica migraciones completadas.

Los cinco overlays son necesarios. `AUTH_ENABLED=true` activa seguridad en ambas APIs; Orders también exige `EVENTSTORE_ENABLED=true`. Las factories sin autenticación se conservan únicamente para regresiones de labs anteriores.

## 2. Audiencias, roles y scopes · 10 minutos

| Recurso | Rol obligatorio | Scope obligatorio |
|---|---|---|
| GET Orders y check-stock | `order:read` | `orders.read` |
| POST/PATCH Orders | `order:write` | `orders.write` |
| GET Inventory | `inventory:read` | `inventory.read` |
| POST productos/reservas | `inventory:write` | `inventory.write` |
| Diagnóstico/reset de circuitos y rebuild | `ops:admin` | `ops.admin` |

**Ambos permisos son obligatorios.** Un scope por sí solo no concede un rol. El rebuild y reset conservan además la comprobación `X-Admin-Key: lab-admin-key` del Lab 4. `/health` es público para readiness; `/openapi.json` y `/docs` muestran contratos públicos, mientras las operaciones exigen Bearer. `/api/v1/auth/me` exige un token válido para la audiencia del servicio y devuelve identidad/claims seleccionados.

| Cliente | Flujo | Permisos de su identidad |
|---|---|---|
| `lab-admin-client` | Client Credentials, operador de práctica | Los cinco permisos |
| `readonly-client` | Client Credentials, prueba de lectura | Orders e Inventory lectura |
| `order-service-client` | Client Credentials | Sólo lectura de Inventory |
| `inventory-service-client` | Client Credentials | Sólo lectura de Inventory; configurado, sin llamada saliente ficticia |
| `expiry-test-client` | Client Credentials, prueba | Lectura Orders; token de 2 segundos |
| `frontend-client` | Authorization Code con PKCE S256 | Depende de los roles del usuario autenticado |

Los clientes tienen `fullScopeAllowed=false` y mappings explícitos de roles. Cada scope incluye un mapper de audiencia; los clientes incorporan mappers de roles y de `sub`. Todos tienen deshabilitado el password grant.

| Configuración | Valor dentro de Docker |
|---|---|
| Issuer validado en ambas APIs | `http://localhost:8080/realms/microservices-lab` |
| Audiencia Orders | `order-api` |
| Audiencia Inventory | `inventory-api` |
| Descarga JWKS | `http://keycloak:8080/realms/microservices-lab/protocol/openid-connect/certs` |
| Token endpoint para Orders | `http://keycloak:8080/realms/microservices-lab/protocol/openid-connect/token` |

El issuer es la identidad pública del emisor; JWKS y token endpoint usan la dirección interna accesible entre contenedores. No sustituyas el issuer por `http://keycloak:8080`. La configuración es local, HTTP y `start-dev`, con credenciales de práctica. Un despliegue remoto requiere hostname coherente y TLS; desactivar la validación de issuer/audiencia no es una solución.

## 3. Inspección del validador · 10 minutos

Revisa `shared/auth/jwt_validator.py` y `dependencies.py`:

- Sólo RS256, `kid` obligatorio, RSA ≥2048 y claves descargadas de la URL configurada. No se sigue `jku` enviado por el token.
- Firma, `iss`, `aud`, `exp`, `iat`, `sub` y tipo de access token `Bearer` obligatorios; también se valida `nbf` cuando existe. Un ID token no sirve como Bearer de API.
- JWKS compartido por proceso: TTL 60 segundos, lock contra descargas concurrentes y espera mínima de 2 segundos para refrescar por `kid` desconocido. Tras una rotación, un `kid` nuevo puede recibir 401 durante esa ventana; vuelve a intentar después. No se admite una caché expirada si JWKS está caído.
- Sin Bearer o JWT inválido: **401** con `WWW-Authenticate: Bearer`. Token válido sin rol o scope: **403**. JWKS inaccesible y sin caché válida: **503**.

Los roles autorizan operaciones; esta práctica no implementa propiedad de pedidos por usuario ni aislamiento multitenant.

## 4. Usuarios con Authorization Code + PKCE · 8 minutos

Ejecuta en tu equipo, con el navegador disponible:

```powershell
python scripts/keycloak/login_pkce.py --scope "orders.read inventory.read" --output readonly-token.json
```

Inicia sesión con `readonly-user` / `Read-Lab05!`. El helper abre el navegador, verifica `state`, intercambia el código con `code_verifier` y guarda sólo el access token y su duración. Callback exacto: `http://127.0.0.1:8765/callback`; libera ese puerto antes de ejecutar. No uses Client Credentials para simular una identidad humana.

Para un usuario operador:

```powershell
python scripts/keycloak/login_pkce.py --scope "orders.read orders.write inventory.read inventory.write ops.admin" --output admin-token.json
```

Usa `admin-user` / `Admin-Lab05!`. Los archivos de token están ignorados por Git; no los publiques. Un usuario readonly no obtiene el rol de escritura aunque solicite un scope de escritura.

## 5. Curl y Client Credentials · 12 minutos

PowerShell: usa **curl.exe**, evitando el alias `curl`. Obtén tokens de prueba sin imprimirlos:

```powershell
$tokenUrl = 'http://localhost:8080/realms/microservices-lab/protocol/openid-connect/token'
$admin = (curl.exe -sS -X POST $tokenUrl -d 'grant_type=client_credentials' -d 'client_id=lab-admin-client' -d 'client_secret=lab-admin-secret' --data-urlencode 'scope=orders.read orders.write inventory.read inventory.write ops.admin' | ConvertFrom-Json).access_token
$read = (curl.exe -sS -X POST $tokenUrl -d 'grant_type=client_credentials' -d 'client_id=readonly-client' -d 'client_secret=readonly-secret' --data-urlencode 'scope=orders.read inventory.read' | ConvertFrom-Json).access_token
curl.exe -i http://localhost:8001/health
curl.exe -i http://localhost:8001/api/v1/orders
curl.exe -i -H "Authorization: Bearer invalid.jwt.token" http://localhost:8001/api/v1/orders
curl.exe -i -H "Authorization: Bearer $read" http://localhost:8001/api/v1/orders
curl.exe -i -X POST -H "Authorization: Bearer $read" -H 'Content-Type: application/json' --data-raw '{}' http://localhost:8001/api/v1/orders
curl.exe -i -H "Authorization: Bearer $admin" http://localhost:8002/api/v1/auth/me
```

Los tokens normales duran 300 segundos. Si expiran durante la práctica, vuelve a obtenerlos; no amplíes la expiración para ocultar un 401.

Resultados: salud 200; sin token 401; token mal formado 401; lectura 200; escritura readonly 403; identidad Inventory 200.

Crea producto y pedido con cuerpos en archivos para evitar problemas de comillas en PowerShell:

```powershell
@{ name='Producto Lab05'; sku=('AUTH-' + [guid]::NewGuid().ToString('N').Substring(0,8).ToUpperInvariant()); stock_quantity=20 } | ConvertTo-Json | Set-Content -Encoding utf8 product.json
$product = (curl.exe -sS -X POST -H "Authorization: Bearer $admin" -H 'Content-Type: application/json' --data-binary '@product.json' http://localhost:8002/api/v1/products | ConvertFrom-Json)
@{ customer_id=[guid]::NewGuid().ToString(); items=@(@{product_id=$product.id;quantity=2;unit_price='10.00'}) } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 order.json
curl.exe -i -X POST -H "Authorization: Bearer $admin" -H 'Content-Type: application/json' --data-binary '@order.json' http://localhost:8001/api/v1/orders
curl.exe -i -H "Authorization: Bearer $read" "http://localhost:8002/api/v1/products/$($product.id)"
```

El pedido devuelve **201**, `pending`, `total="20.00"` y `X-Stock-Precheck: verified`. Poco después, Kafka/Redis reduce stock de 20 a 18. No añadas `customer_id` igual a un nombre de usuario: el contrato continúa usando UUID.

Bash, equivalente para obtener un token y hacer una lectura:

```bash
TOKEN_URL='http://localhost:8080/realms/microservices-lab/protocol/openid-connect/token'
READ=$(curl -fsS -X POST "$TOKEN_URL" -d 'grant_type=client_credentials' -d 'client_id=readonly-client' -d 'client_secret=readonly-secret' --data-urlencode 'scope=orders.read inventory.read' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -i -H "Authorization: Bearer $READ" http://localhost:8002/api/v1/products
```

Revisa `shared/auth/token_client.py` y `order-service/app/clients/inventory_client.py`: cache del token por `expires_in`, margen de renovación, lock para evitar solicitudes duplicadas y `inventory.read` como único scope. Ante 401 de Inventory, invalida el token y renueva una vez; 403 o un segundo 401 producen 503. Los fallos de autenticación se excluyen del circuit breaker y no se aceptan como stock desconocido.

## 6. Validación y evidencia · 14 minutos

Con todo levantado:

```powershell
python scripts/validate_lab05.py
```

El script verifica ambas APIs, 401/403, audiencia incorrecta, permisos de servicio, creación con precheck autenticado, reserva Kafka/Redis y un JWT **realmente firmado y expirado**. Un token inventado con texto `expired` no demuestra expiración. El cliente de prueba tiene TTL 2 segundos; el script espera 3 segundos tras comprobar que inicialmente funciona.

Regresiones de laboratorios anteriores con Bearer de operador:

```powershell
$env:LAB_API_TOKEN_FILE = (Resolve-Path admin-token.json).Path
python scripts/validate_lab02.py
$env:EVENTSTORE_DATABASE_URL = 'postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db'
python scripts/validate_lab03.py
```

Pruebas automatizadas completas, con bases aisladas creadas por los fixtures:

```powershell
$env:POSTGRES_TEST_ADMIN_URL = 'postgresql+asyncpg://lab_admin:lab_admin_lab_pass@localhost:5432/eventstore_db'
$env:REDIS_TEST_URL = 'redis://localhost:6379/15'
$env:KEYCLOAK_TEST_ISSUER = 'http://localhost:8080/realms/microservices-lab'
Push-Location order-service
python -m pytest tests -q
Pop-Location
Push-Location inventory-service
python -m pytest tests -q
Pop-Location
```

Las pruebas generadas de las factories históricas sin autenticación usan los contratos `contracts/legacy/`; las pruebas dedicadas de seguridad cubren las rutas protegidas.

Los fixtures sólo eliminan las bases y claves temporales que crean. Sin variables de PostgreSQL, Redis o Keycloak, sus pruebas de integración se omiten; un resultado con skips no prueba esos componentes. Las cinco pruebas reales de Keycloak incluyen PKCE correcto, rechazo de verifier incorrecto, password grant deshabilitado, audiencia de servicio y expiración.

El overlay de chaos del Lab 4 sigue disponible. Al usarlo, pasa también el overlay auth y `LAB_API_TOKEN_FILE` de operador al script. El mock :8003 es una dependencia sintética local y no valida JWT; no demuestra seguridad del Inventory real :8002. No alteres el namespace normal para ejecutar chaos.

### Criterios de aceptación

- Peticiones sin token o con firma/issuer/audiencia/expiración inválidos reciben 401.
- Usuarios readonly pueden leer y reciben 403 al escribir.
- Pedidos válidos conservan EventStore, outbox y reserva asíncrona del Lab 2.
- Orders consulta Inventory con identidad propia; no reenvía credenciales del usuario.
- Credenciales de servicio inválidas producen 503 sin crear eventos ni outbox.
- Circuit breaker, retries y bulkhead siguen pasando sus regresiones.
- Tokens y secretos no aparecen en los logs de aplicación ni en la entrega del alumno.

### Diagnóstico

| Síntoma | Comprobación |
|---|---|
| Keycloak no arranca | `dc logs keycloak keycloak-db`; salud en :9000 y DB propia |
| Realm no se actualiza | El import omite realms existentes; no se sobrescribe automáticamente |
| JWT válido devuelve 401 | `iss`, audiencia correcta, mapper `sub`, hora y RS256 |
| JWT devuelve 403 | Rol **y** scope; obtener token nuevo después de cambiar roles |
| Orders devuelve 503 de autenticación | Cliente `order-service-client`, secreto y `inventory.read`; no abrir el circuito para ocultarlo |
| Stock no baja | Topics creados, relay activo, consumer de Inventory y Redis; revisar logs |
| pip compila pydantic-core | Verificar Python 3.12 y recrear el entorno; no instalar en Python 3.13 |

Detén la práctica con `dc stop`; conserva volúmenes. La seguridad añadida cubre las APIs HTTP y el flujo OAuth. Kafka continúa con la configuración didáctica anterior; no se introduce autenticación de broker en este capítulo.

## Material y referencias

- `shared/auth/`: JWT, permisos y cliente de tokens.
- `infra/keycloak/` y `scripts/keycloak/`: import y login PKCE.
- `docker-compose.auth.yml`: infraestructura e integración de ambos servicios.
- `scripts/validate_lab05.py`: validación real de toda la pila.
- `docs/informe-revision-lab05.md`: cambios y alcance de verificación.
- [Keycloak 26.8.0](https://www.keycloak.org/2026/10/keycloak-2680-released), [hostname](https://www.keycloak.org/server/hostname), [importación](https://www.keycloak.org/server/importExport).
- [PyJWT: validación y claims](https://pyjwt.readthedocs.io/en/stable/usage.html).

## Estado de la revisión

176 pruebas aprobadas (119 Orders y 57 Inventory), con PostgreSQL, Redis y Keycloak reales. Preflight, dependencias y contratos verificados. El arranque Docker Compose y la reserva completa por Kafka deben validarse en el equipo del alumno con `scripts/validate_lab05.py`; no se ejecutaron en el entorno de revisión.
