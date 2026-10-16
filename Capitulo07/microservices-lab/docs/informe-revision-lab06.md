# Informe de revisión · Laboratorio 6

## Resultado

Se mantienen los cinco objetivos del capítulo: Traefik mediante Helm/CRDs, tres backends, rutas declarativas, rate limiting y circuit breaker con validación mediante curl/Python. Se preservan las aplicaciones y contratos de los labs 1–5. El título incorrecto de laboratorio 4 se corrige a laboratorio 6.

## Problemas encontrados y cambios

| Original | Corrección |
|---|---|
| Orders/Inventory rehechos en memoria, sin JWT/CQRS/Kafka/Redis | Mismo código acumulativo; manifests de dependencias y aplicaciones en Kubernetes |
| Builds con requirements fuera del contexto y reconstrucción posterior | Build desde raíz mediante minikube image build y Dockerfiles por servicio |
| Chart 28.3.0 atribuido a Traefik 3.0.4 | Su Chart.yaml declara v3.0.2; chart 41.7.0 / appVersion v3.7.14 fijados y digest verificado |
| Valores antiguos de Helm y dashboard insecure expuesto | Valores validados contra el chart actual; dashboard deshabilitado, API admin sin ruta pública, Service ClusterIP |
| /api/v1/inventory incompatible con Lab 1 corregido | Rutas existentes products/reservations; UUID/Decimal/pending conservados |
| allowCrossNamespace considerado necesario por ubicación del controlador | Rutas/servicios/middlewares en microservices; controller observa namespace; referencias cruzadas deshabilitadas |
| checkPeriod descrito como ventana fija de errores | Documentado como intervalo de evaluación; sin afirmar ventana fija ni número mágico de fallos |
| Prueba de circuit breaker no falla si no abre/recupera, interferencia de 429 | Router chaos prioritario, circuito separado sin rate limiter, JWT obligatorio; fases estrictas y marcador backend |
| Rate limiter aceptaba resultados parciales y conteos de ejemplo engañosos | Ráfaga concurrente acotada, 200+429 obligatorios, aislamiento/reposición, errores inesperados fallan |
| validación set -e con ((PASS++)) y conteo de Running rígido | Scripts fail-fast; rollout por componente y prueba real de reserva asíncrona |
| Limpieza elimina namespaces/clúster/entrada hosts | Pausa minikube y cierre de port-forward; conservar PVCs/imágenes para Lab 7 |

Users es un tercer servicio de demostración, con datos ficticios de lectura. No sustituye Keycloak ni introduce otro sistema de identidades. Se protege mediante users-api / user:read / users.read. Las identidades de servicio de Orders mantienen permiso mínimo inventory.read.

## Verificación realizada

- **183 pruebas aprobadas**: Orders 119, Inventory 57, Users 7; sin skips en la ejecución con variables de integración.
- PostgreSQL 16.3, Redis 7.2.5 y Keycloak 26.8.0 reales para regresiones. Keycloak utiliza **H2 temporal en las pruebas**, mientras el despliegue entregado usa PostgreSQL separado.
- Traefik **3.7.14 real**, tres procesos FastAPI y Keycloak real: Host/path routing, JWT, prefijo límite (/orders-evil), dashboard/API no accesibles, Client Credentials Orders → Inventory, pedido pending/20.00 y precheck verified con persistencia EventStore.
- Rate limiting HTTP real: **10 respuestas 200 y 70 respuestas 429** en una ráfaga de 80 (0.15 s); Inventory siguió disponible y Users repuso cuota tras dos segundos. Estos conteos son evidencia de esta ejecución, no una expectativa fija para cada alumno.
- Circuit breaker HTTP real: 500 con marcador del backend; 503 generado por el edge sin marcador; petición saludable bloqueada; otro router disponible; recuperación con cinco 200 consecutivos.
- Las políticas y reglas de la prueba HTTP se obtienen de los manifests entregados y se cargan mediante **file provider**. Esto prueba su ejecución en Traefik, pero no demuestra que el provider Kubernetes CRD, RBAC y DNS del clúster hayan realizado un rollout.
- **35 manifests** contra schemas oficiales: Swagger Kubernetes 1.35.8 y CRDs del chart fijado. IntOrString se adapta a unión integer/string para JSON Schema.
- `helm lint` y `helm template --include-crds` aprobados con Helm 3.20.1 y kubeVersion 1.35.8. Los **6 recursos nativos** renderizados se comprobaron contra Swagger, omitiendo campos opcionales null y adaptando IntOrString.
- SHA256 del chart empaquetado coincide con el index.yaml oficial; sintaxis Python/Bash, contratos OpenAPI, preflight y pip check aprobados.

## Pendiente de verificación en el entorno del alumno

No se ejecutó Docker ni un clúster minikube en este entorno. Permanecen pendientes el build de imágenes, mounts/permisos/PVCs, PostgreSQL de Keycloak, Jobs/rollout, provider Kubernetes CRD/RBAC/DNS, port-forward y el flujo completo de reserva **Kafka real dentro de Kubernetes**. La guía proporciona deploy.sh y validate_all.sh para verificar todo y terminar con error si falla una comprobación.

La instancia Kubernetes comienza con PVCs propios; no importa los datos Compose del Lab 5. El laboratorio mantiene una réplica por componente y credenciales/HTTP de práctica. No incorpora TLS, cuotas distribuidas, alta disponibilidad ni autenticación del broker en este capítulo.
