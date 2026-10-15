# Laboratorio 6 · API Gateway y políticas para microservicios Python

**Curso:** Microservicios Avanzado · **Complejidad:** media · **Bloom:** aplicar.
**Tiempo guiado:** 66 minutos, con herramientas e imágenes preparadas antes de clase.
**Continuidad:** código acumulativo de los labs 1–5 corregidos. El ZIP contiene la solución completa y el chart Helm fijado.

## Objetivos y resultado esperado

1. Desplegar Traefik 3 como Ingress Controller en minikube mediante Helm y sus CRDs.
2. Configurar IngressRoutes hacia tres microservicios FastAPI bajo `microservices.local`.
3. Aplicar rate limiting diferenciado por servicio.
4. Aplicar circuit breaker en el edge y distinguirlo del circuito interno de Orders.
5. Validar rutas y políticas con curl y scripts que fallen cuando no se cumple lo esperado.

Se conservan UUID, `/api/v1`, Decimal, JWT, roles/scopes, Client Credentials, EventStore/CQRS, outbox, Kafka, Redis, retries y bulkhead. Orders e Inventory usan el código revisado; no se sustituyen por diccionarios en memoria. **Users es un servicio adicional de demostración**, con datos ficticios de lectura y fallo simulado; Keycloak continúa administrando identidades y autenticación.

```mermaid
flowchart TD
  C["Cliente · Host microservices.local + Bearer"] --> G["Traefik · rutas y políticas"]
  G -->|"100/min · burst 20"| O["Orders · JWT + CQRS"]
  G -->|"200/min · burst 40"| I["Inventory · JWT"]
  G -->|"50/min · burst 10"| U["Users demo · JWT"]
  O -->|"Client Credentials + resiliencia"| I
  O --> P["PostgreSQL · eventos y outbox"]
  P -->|"Relay"| K["Kafka · contratos Lab 2"]
  K --> I
  I --> R["Redis · stock y reservas"]
```

Keycloak valida usuarios y emite tokens para los tres recursos. Las APIs verifican firma/issuer/audiencia mediante JWKS. El Gateway conserva `Authorization`; no reemplaza los permisos de aplicación.

## Correcciones respecto al original

El archivo original estaba rotulado como laboratorio 4; aquí se identifica como **laboratorio 6**. Se corrigen contexto de build, versiones del chart, paths, exposición del dashboard, comprobaciones de readiness y falsos positivos de los scripts. `checkPeriod` es la frecuencia de evaluación del circuito, **no una ventana de errores de diez segundos**. El rate limiter usa token bucket; 50/min describe la reposición, no un contador fijo que admite 50 solicitudes instantáneas.

El chart original **28.3.0 declara appVersion v3.0.2**, aunque el texto afirmaba que incluía 3.0.4. Esta revisión fija **chart 41.7.0 / Traefik 3.7.14**, con valores contrastados con su schema y renderizados. El chart se incluye en `vendor/`; instalarlo no necesita buscar una versión distinta en el repositorio.

## 0. Preparación previa del instructor

Usa Ubuntu con Docker funcionando para el usuario actual. Entorno objetivo: minikube **1.39.0**, Kubernetes **1.35.8**, kubectl de la rama **1.35**, Helm **3.20.1** y Python **3.12**. Los manifests usan APIs estables y `traefik.io/v1alpha1`.

Reserva al menos **6 CPU, 10 GiB para minikube y 40 GB de disco**; se recomienda un host/VM de 16 GiB. Se despliegan las dependencias reales del curso además de las tres APIs. Descargar imágenes y compilar por primera vez puede exceder el tiempo guiado.

Extrae el ZIP. Desde `microservices-lab`:

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r order-service/requirements-dev.txt
python -m pip check
python scripts/preflight.py --auth
minikube version
kubectl version --client
helm version --short
docker info
```

No requiere el Python launcher `py`. En Windows, ejecuta la práctica en una VM Ubuntu; los comandos de este capítulo son Bash. No ejecutes los scripts Bash directamente en PowerShell.

Versiones acumulativas: PostgreSQL 16.3, Redis 7.2.5, Kafka/Zookeeper Confluent 7.6.1, Keycloak 26.8.0, FastAPI 0.111.0, Pydantic 2.7.1, PyJWT 2.15.1 y cryptography 50.0.2. La migración de plataforma no cambia las versiones de las dependencias de negocio.

Este laboratorio crea **otra instancia de datos en PVCs de Kubernetes**. Continúa el código y los contratos, pero no importa automáticamente los volúmenes ni los pedidos del Lab 5 en Compose. Conserva aquella instancia. Si Compose ocupa :8080, detén sus servicios con la función `dc stop` del Lab 5; no uses `down -v`.

## 1. Clúster y despliegue ordenado · 14 minutos

Desde la raíz del proyecto:

```bash
export PROFILE=msvc-gateway
export KUBE_CONTEXT=msvc-gateway
minikube start -p "$PROFILE" --driver=docker --cpus=6 --memory=10240 --disk-size=40g --kubernetes-version=v1.35.8
minikube addons disable ingress -p "$PROFILE"
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
k get nodes -o wide
bash scripts/lab06/deploy.sh
```

No actives el addon Traefik de minikube: en esta práctica se instala el chart fijado.

`deploy.sh` usa contexto y perfil explícitos, termina ante errores y ejecuta estas etapas:

1. Genera el realm y su ConfigMap; construye las tres imágenes en minikube desde el contexto raíz correcto.
2. Crea namespaces, secretos de práctica, configuración de inicialización y los dos PostgreSQL.
3. Espera readiness de bases, Redis, Zookeeper y Kafka; crea los cuatro topics del curso con tres particiones.
4. Despliega Keycloak y espera readiness en su puerto management :9000.
5. Ejecuta `eventstore-migrate` con la conexión administrativa; Orders utilizará después el rol restringido `order_app`.
6. Despliega las tres APIs y espera rollout; aplica los CRDs del chart con server-side apply e instala/actualiza Traefik mediante `helm upgrade --install` y aplica sus middlewares y rutas.

Helm no actualiza automáticamente CRDs durante un upgrade. El script los aplica explícitamente desde el chart fijado antes de instalar/actualizar el release. No mezcla CRDs descargados de otra versión.

El Job completado se recrea de forma acotada cuando repites el script; `alembic upgrade head` no borra datos. No recrea PVCs. Las credenciales de práctica están en `k8s/lab06/01-secrets.yaml`, y el realm conserva los valores conocidos del Lab 5.

Comprueba:

```bash
k -n microservices get deployments,statefulsets,services,pvc
k -n microservices logs job/eventstore-migrate
k -n traefik get deployment,service
k get crd ingressroutes.traefik.io middlewares.traefik.io
```

No basta con contar pods `Running`; un pod puede no estar Ready y el Job tiene un pod `Completed`. El validador usa rollout por componente.

## 2. Acceso estable y seguridad · 8 minutos

Traefik usa **ClusterIP**. Abre dos terminales y deja los procesos activos:

```bash
# Terminal A: emisor público fijo del Lab 5
kubectl --context msvc-gateway -n microservices port-forward --address 127.0.0.1 service/keycloak 8080:8080
```

```bash
# Terminal B: entrada del Gateway
kubectl --context msvc-gateway -n traefik port-forward --address 127.0.0.1 service/traefik 18080:80
```

Todas las pruebas siguientes se ejecutan en la misma máquina/VM Ubuntu donde corren esos port-forward. No dependen de `/etc/hosts`, NodePort ni de que la IP de minikube sea accesible desde Windows.

```bash
export GATEWAY_URL=http://localhost:18080
export GATEWAY_HOST=microservices.local
export AUTH_ISSUER=http://localhost:8080/realms/microservices-lab
```

La consola de Keycloak está en <http://localhost:8080>: `admin` / `admin_lab_pass`. Usuarios de práctica: `admin-user` / `Admin-Lab05!` y `readonly-user` / `Read-Lab05!`.

Las APIs usan el issuer público fijo `http://localhost:8080/realms/microservices-lab` y JWKS interno `http://keycloak:8080/.../certs`. Orders obtiene tokens en la dirección interna de Keycloak y consulta `http://inventory-service:8002`. Cambiar el Host del Gateway no cambia el issuer.

Se añade audiencia **users-api**, rol **user:read** y scope **users.read**, asignados a operadores/readonly de práctica. Los permisos anteriores se conservan; `order-service-client` continúa con sólo `inventory.read`. El realm se importa únicamente cuando no existe: regenerar el ConfigMap y reiniciar Keycloak **no sobrescribe un realm previo**. Si actualizas una configuración vieja en esta instancia, ajusta los scopes/roles en la consola o elimina sólo el realm de práctica y vuelve a importarlo; no borres volúmenes de negocio.

Para una identidad humana puedes usar el helper PKCE del Lab 5 con `--scope "orders.read inventory.read users.read"`. Requiere que el navegador y su callback :8765 sean accesibles en la misma máquina que Keycloak. Las pruebas de este capítulo usan Client Credentials de operador/lector y no password grant.

## 3. Rutas y middlewares · 10 minutos

Revisa `k8s/traefik/values.yaml`, `middlewares.yaml` y `routes.yaml`.

| Ruta del Gateway | Backend | Permiso conservado |
|---|---|---|
| `/api/v1/orders` y sus subrutas | `order-service:8001` | Rol + scope Orders |
| `/api/v1/products` y sus subrutas | `inventory-service:8002` | Rol + scope Inventory |
| `/api/v1/reservations` y sus subrutas | `inventory-service:8002` | Escritura Inventory |
| `/api/v1/users` y sus subrutas | `users-service:8003` | `user:read` + `users.read` |

No se inventa `/api/v1/inventory`, que no existe en el contrato corregido. Cada regla combina `Host`, `Path` exacto y `PathPrefix` terminado en `/`; `/api/v1/orders-evil` no coincide. No se elimina `/api/v1` ni se aplica StripPrefix.

Ejemplo real:

```yaml
match: Host(`microservices.local`) && (Path(`/api/v1/orders`) || PathPrefix(`/api/v1/orders/`))
```

Las rutas, servicios y middlewares están en **microservices**. El controlador puede estar en **traefik** y observar microservices mediante su provider/RBAC. `allowCrossNamespace=false` no impide eso: regula referencias de una ruta a recursos de otro namespace. No es necesario habilitarlo para estas rutas.

| Política | Reposición | Capacidad del bucket |
|---|---|---|
| Orders | 100 tokens/min | 20 |
| Inventory | 200 tokens/min | 40 |
| Users | 50 tokens/min | 10 |

Cada servicio tiene middleware propio. `sourceCriterion.requestHost=true` agrupa todas las peticiones de ese router bajo `microservices.local`: cuota agregada y reproducible de práctica, **no por usuario JWT**. No se usa el Bearer completo como clave del limiter. Hay una réplica de Traefik; estos buckets y circuitos viven en memoria del proceso y no constituyen una cuota distribuida.

Orden: **rate limiter → circuit breaker → backend**. Un 429 se genera antes del backend y no debe confundirse con 503 de circuito abierto. Peticiones sin JWT también consumen cuota antes de recibir 401 de la API.

Circuitos normales: expresión `ResponseCodeRatio(500, 600, 0, 600) > 0.50`, `checkPeriod=100ms`, `fallbackDuration=15s` y `recoveryDuration=30s`. Son circuitos de edge por router. El circuito Redis de Orders → Inventory del Lab 4 es otro mecanismo, con otro estado y otra finalidad. El edge no sustituye reintentos/bulkhead de Orders ni garantiza entrega por Kafka.

El dashboard de Traefik está **deshabilitado** y su API administrativa **no se publica**; no se habilita `api.insecure`. No se publican `/health`, `/docs`, `/openapi.json`, `/admin` ni diagnósticos de Orders mediante estas IngressRoutes. Para diagnóstico de readiness se usa Kubernetes; para comprobar una API directamente usa un port-forward temporal y sigue enviando Bearer donde corresponda.

## 4. Curl y prueba funcional · 10 minutos

Obtén un token de lector; no lo imprimas:

```bash
TOKEN_URL="$AUTH_ISSUER/protocol/openid-connect/token"
READ=$(curl -fsS -X POST "$TOKEN_URL" -d 'grant_type=client_credentials' -d 'client_id=readonly-client' -d 'client_secret=readonly-secret' --data-urlencode 'scope=orders.read inventory.read users.read' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -i -H "Host: $GATEWAY_HOST" -H "Authorization: Bearer $READ" "$GATEWAY_URL/api/v1/orders"
curl -i -H "Host: $GATEWAY_HOST" -H "Authorization: Bearer $READ" "$GATEWAY_URL/api/v1/products"
curl -i -H "Host: $GATEWAY_HOST" -H "Authorization: Bearer $READ" "$GATEWAY_URL/api/v1/users"
curl -i -H "Host: $GATEWAY_HOST" "$GATEWAY_URL/api/v1/orders"
curl -i -H 'Host: wrong.local' "$GATEWAY_URL/api/v1/orders"
curl -i -H "Host: $GATEWAY_HOST" "$GATEWAY_URL/dashboard/"
curl -i -X POST -H "Host: $GATEWAY_HOST" -H "Authorization: Bearer $READ" -H 'Content-Type: application/json' --data '{}' "$GATEWAY_URL/api/v1/orders"
```

Resultados: tres lecturas 200; sin JWT 401; Host incorrecto 404; dashboard 404; escritura readonly 403. Un token sólo con audiencia users-api recibe 401 en Orders. Los tokens normales duran 300 segundos: vuelve a obtenerlos si expiran.

Ejecuta:

```bash
python scripts/lab06/validate_gateway.py
```

El validador obtiene tokens de operador/lector, comprueba las tres rutas, 401/403, audiencia incorrecta, aislamiento de prefijos y ausencia de dashboard. Después crea producto/pedido vía Gateway, exige `X-Stock-Precheck: verified` y verifica que Kafka/Redis reduzca stock de **20 a 18**. El pedido conserva `pending` y `total="20.00"`. No valida únicamente códigos HTTP; comprueba comportamiento de negocio.

## 5. Rate limiting sin falsos positivos · 10 minutos

```bash
python scripts/lab06/test_ratelimit.py
```

El script envía 80 lecturas de Users con concurrencia acotada y exige:

- Al menos un 200 y un 429, sin 401/403/500 ni errores de conexión.
- Inventory sigue respondiendo 200: buckets separados.
- Después de dos segundos, una lectura Users vuelve a ser admitida: reposición.

No espera un resultado ficticio de 58 éxitos y 22 rechazos. Con bucket inicialmente lleno, la ráfaga inicial admite aproximadamente 10 y después repone **50/60 ≈ 0.83 por segundo**; tiempos y tráfico previo cambian el número observado. Si repites la prueba inmediatamente, espera **12 segundos** para reponer los diez tokens del bucket de Users antes de volver a ejecutarla.

Puedes observar el rate limiter con curl, pero el script da una comprobación completa y devuelve código distinto de cero ante incumplimientos. Un 429 puede aparecer antes de la autenticación si ya agotaste la cuota; espera reposición antes de diagnosticar JWT.

## 6. Circuit breaker con prueba aislada · 14 minutos

Para no introducir fallos en Orders ni ocultarlos detrás del rate limiter de Users, activa el router de chaos **sólo durante esta prueba**:

```bash
k apply -f k8s/traefik/chaos-route.yaml
python scripts/lab06/test_circuitbreaker.py
```

El router tiene prioridad **100**, frente a **20** de las rutas normales, y coincide únicamente con `/api/v1/users/fail/simulate`. Usa un circuito independiente `circuitbreaker-chaos` con `fallbackDuration=3s` y `recoveryDuration=2s`; no usa rate limiting. La API sigue exigiendo JWT, `user:read` y `users.read`.

```mermaid
stateDiagram-v2
  [*] --> Cerrado
  Cerrado --> Abierto: ratio 5xx mayor a 0.50
  Abierto --> Recuperando: termina fallbackDuration
  Recuperando --> Cerrado: recuperación saludable
  Recuperando --> Abierto: vuelve a fallar
```

El endpoint acepta `?fail=true` para devolver 500 y `?fail=false` para devolver 200; sus respuestas llevan `X-Lab-Backend: users-service`. El 503 generado por el edge no lleva ese marcador.

La prueba exige **todas** estas evidencias:

1. Un 500 proviene efectivamente del backend.
2. Aparece un 503 sin marcador del backend.
3. Una petición que el backend respondería 200 también queda bloqueada por el circuito abierto.
4. Inventory sigue respondiendo 200 mediante su propio router.
5. Al dejar de simular fallos, se observan cinco respuestas 200 consecutivas tras la recuperación.

401, 403, 429, timeout o router ausente **no cuentan como apertura**. Si falta una fase, el script termina con error. `checkPeriod` determina cuándo evalúa la expresión; no se afirma una ventana fija de diez segundos ni un mínimo fijo de 30 fallos.

Retira el router de prueba al terminar:

```bash
k delete -f k8s/traefik/chaos-route.yaml --ignore-not-found
```

El endpoint simulado sigue en el servicio de demostración; sin el router específico queda sujeto a las políticas normales de Users. No uses ese endpoint en ejercicios de negocio ni lo presentes como funcionalidad de producción.

## Validación completa y pruebas de regresión

Con los port-forward activos y el entorno Python activado:

```bash
bash scripts/lab06/validate_all.sh
```

Comprueba rollout de todos los componentes, flujo completo de negocio, rate limiting y circuito aislado. Aplica el router de chaos para la última prueba; retíralo después con el comando anterior. No cambia recursos de otro contexto, no cuenta pods de forma rígida y no continúa tras fallos.

Para las suites de regresión, abre port-forward adicionales:

```bash
# Cada comando en una terminal separada
k -n microservices port-forward --address 127.0.0.1 service/postgres 5432:5432
k -n microservices port-forward --address 127.0.0.1 service/redis 6379:6379
```

```bash
export POSTGRES_TEST_ADMIN_URL='postgresql+asyncpg://lab_admin:lab_admin_lab_pass@localhost:5432/eventstore_db'
export REDIS_TEST_URL='redis://localhost:6379/15'
export KEYCLOAK_TEST_ISSUER="$AUTH_ISSUER"
(cd order-service && python -m pytest tests -q)
(cd inventory-service && python -m pytest tests -q)
(cd users-service && python -m pytest tests -q)
```

Los fixtures crean/eliminan únicamente sus bases y claves temporales. Sin variables de integración se omiten pruebas de PostgreSQL, Redis o Keycloak; un resultado con skips no valida esos componentes. Los contratos legacy sólo sirven a las factories históricas sin auth; las pruebas de JWT y rutas protegidas son independientes.

Para verificar Helm sin desplegar:

```bash
helm lint vendor/traefik-41.7.0.tgz -f k8s/traefik/values.yaml --kube-version 1.35.8
helm template traefik vendor/traefik-41.7.0.tgz -n traefik --kube-version 1.35.8 --include-crds -f k8s/traefik/values.yaml > /tmp/lab06-traefik-rendered.yaml
```

Renderizar Helm o validar YAML no demuestra readiness ni que las políticas se hayan ejecutado. `docs/informe-revision-lab06.md` distingue las verificaciones realizadas de las pendientes en Kubernetes.

## Diagnóstico

| Síntoma | Comprobación concreta |
|---|---|
| 404 del Gateway | Host exacto, path correcto, CRDs establecidos, IngressRoute/middlewares y logs de Traefik |
| 401 | Token renovado, audience del servicio, issuer fijo, rol/scope y reloj; 401 no es circuito abierto |
| 403 | Rol y scope conjuntamente; obtener token nuevo después de modificar permisos |
| 429 durante pruebas JWT | Esperar reposición del bucket; no desactivar JWT |
| 503 en Gateway | Logs access: `OriginStatus` y `DownstreamStatus`; circuito edge frente a backend no Ready/error interno |
| 503 de autenticación en Orders | Secreto/scopes de order-service-client y acceso a Keycloak; no convertirlo en fallback |
| Stock no baja | Topics, consumer Inventory, relay outbox y Redis; no marcar la prueba como aprobada sólo por 201 |
| ImagePullBackOff | Imagen `:lab06` construida en el perfil correcto; `minikube -p "$PROFILE" image ls` |
| Keycloak no Ready | PostgreSQL propio, import y health :9000; logs de ambos componentes |
| Job migration falla | `k -n microservices logs job/eventstore-migrate`; conexión administrativa y rol order_app |
| Helm nombre en uso | Usar `upgrade --install` con el mismo release, namespace y chart fijado |

```bash
k -n traefik logs deployment/traefik --tail=50
k -n microservices get ingressroutes,middlewares
k -n microservices get endpointslices
k -n microservices logs deployment/order-service --tail=50
k -n microservices logs deployment/inventory-service --tail=50
k -n microservices logs deployment/keycloak --tail=50
```

Los access logs de Traefik omiten headers, incluido Authorization. No publiques archivos de token. La práctica conserva HTTP/local y credenciales didácticas del curso; no añade TLS, alta disponibilidad, cuotas distribuidas ni autenticación del broker en este capítulo.

## Cierre y continuidad

Cierra únicamente los procesos port-forward de tus terminales. Para pausar conservando PVCs e imágenes:

```bash
minikube stop -p "$PROFILE"
```

Al continuar, inicia el mismo perfil y abre de nuevo los port-forward. Las imágenes :lab06 y datos permanecen. No elimines el clúster, namespaces ni PVCs si continuarás con el laboratorio 7. No se modifica `/etc/hosts`, así que no hay entradas que limpiar.

## Entregables del alumno

- Valores Helm y rutas/middlewares revisados.
- Evidencia de lectura autenticada, 401/403 y pedido con reserva asíncrona.
- Conteos 200/429 de la ráfaga y prueba de reposición/aislamiento.
- Evidencia de 500 backend → 503 edge → recuperación 200.
- Explicación de por qué `checkPeriod` no es una ventana de errores y por qué el circuito de edge difiere del circuito interno de Orders.

## Referencias oficiales

- [Chart Traefik 41.7.0](https://github.com/traefik/traefik-helm-chart/releases/tag/v41.7.0) y [Traefik 3.7.14](https://github.com/traefik/traefik/releases/tag/v3.7.14).
- [RateLimit](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/ratelimit/) y [CircuitBreaker](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/circuitbreaker/).
- [Minikube: construcción de imágenes](https://minikube.sigs.k8s.io/docs/handbook/pushing/) y [kubectl port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/).

## Estado de la revisión

**183 pruebas aprobadas** (119 Orders, 57 Inventory, 7 Users). Políticas ejecutadas con Traefik real: rate limiting, reposición/aislamiento, apertura y recuperación del circuito. Se validaron 35 manifests y el chart Helm. El rollout completo minikube y la reserva mediante Kafka en Kubernetes deben validarse con `deploy.sh` y `validate_all.sh` en el equipo del alumno; no se ejecutaron en el entorno de revisión. Consulta el informe incluido para el alcance exacto.
