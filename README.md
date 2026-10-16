<img src="images/neteclogo (2).png" alt="logo" width="300"/>

# Arquitectura Avanzada de Microservicios

## Plataforma de laboratorios

Te damos la bienvenida a la **plataforma de laboratorios** del curso **Arquitectura Avanzada de Microservicios [MICR_ADV_PYT]** de **Netec**. A través de prácticas guiadas con Python y FastAPI, desarrollarás y evolucionarás una solución de Pedidos e Inventario, incorporando mensajería, persistencia, resiliencia, seguridad, observabilidad y despliegues en Kubernetes.

## Lista de laboratorios

Cada laboratorio continúa el trabajo del anterior. Haz clic en su título para abrir la guía y consulta sus requisitos antes de comenzar.



### Capítulo 1: Fundamentos avanzados y diseño de microservicios en Python

#### [Laboratorio 1. Prototipo de microservicios con FastAPI y pruebas contractuales](Capitulo01/Lab01_Microservicios_Avanzado_revisado.md)

- **Descripción**: Construir los servicios independientes de Pedidos e Inventario con FastAPI, delimitar sus contextos y organizar modelos, esquemas, servicios y rutas. Definir contratos OpenAPI, comprobarlos con pytest y Schemathesis, y ejecutar ambos servicios mediante Docker Compose. Este prototipo constituye la base de las prácticas posteriores.
- ⏱️ **Duración estimada**: 42 min.

### Capítulo 2: Comunicación entre servicios y mensajería asincrónica

#### [Laboratorio 2. Integrar microservicios Python con Kafka y deduplicar eventos](Capitulo02/README.md)

- **Descripción**: Incorporar productores y consumidores Kafka para publicar pedidos y procesar reservas de inventario de forma asíncrona. Definir eventos de dominio, particionar mensajes por pedido y utilizar Redis para almacenar stock, reservas y resultados de deduplicación. Comprobar que la reentrega de un evento no descuenta existencias nuevamente.
- ⏱️ **Duración estimada**: 57 min.

### Capítulo 3: Patrones de consistencia: CQRS y Event Sourcing

#### [Laboratorio 3. Event Sourcing, CQRS, proyecciones y snapshots](Capitulo03/README.md)

- **Descripción**: Implementar un Event Store inmutable en PostgreSQL y separar los comandos de escritura de las consultas mediante CQRS. Guardar eventos, proyecciones, snapshots y mensajes de outbox de forma transaccional; reconstruir el estado desde el historial y publicar eventos en Kafka mediante un relay con reintentos.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 4: Resiliencia y tolerancia a fallas

#### [Laboratorio 4. Circuit Breaker, retries, bulkhead y degradación controlada](Capitulo04/README.md)

- **Descripción**: Proteger la consulta HTTP de Pedidos a Inventario mediante reintentos con backoff y jitter, un circuit breaker cuyo estado se conserva en Redis y un bulkhead que limita la concurrencia. Inyectar fallos controlados, observar las transiciones del circuito y comprobar la degradación del servicio y su recuperación.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 5: Seguridad federada, OAuth2, JWT y gestión de identidades

#### [Laboratorio 5. Seguridad de APIs con OAuth 2.0, JWT y Keycloak](Capitulo05/README.md)

- **Descripción**: Configurar clientes, roles y scopes en Keycloak; validar tokens JWT con firma RS256, JWKS, emisor y audiencia. Utilizar Authorization Code con PKCE para usuarios y Client Credentials para la comunicación entre servicios. Verificar solicitudes con tokens ausentes, inválidos, expirados o con permisos insuficientes.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 6: API Gateway, enrutamiento y edge patterns para Python

#### [Laboratorio 6. API Gateway y políticas para microservicios Python](Capitulo06/README.md)

- **Descripción**: Desplegar Traefik mediante Helm en minikube y configurar rutas hacia los servicios de Pedidos, Inventario y Usuarios. Aplicar límites de solicitudes por servicio y circuit breaker en el gateway, conservando la autenticación y las dependencias existentes. Validar rutas, respuestas y políticas con curl y scripts de comprobación.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 7: Configuración centralizada y gestión de secretos

#### [Laboratorio 7. Vault y gestión de secretos en microservicios Python](Capitulo07/README.md)

- **Descripción**: Desplegar HashiCorp Vault con Helm y configurar KV v2, autenticación de Kubernetes y políticas de mínimo privilegio. Integrar la lectura de secretos en los servicios FastAPI con hvac, renovar tokens y comprobar la rotación de secretos sin reiniciar las aplicaciones. Revisar la auditoría de accesos permitidos y rechazados.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 8: Observabilidad: trazabilidad, métricas y logging distribuidos

#### [Laboratorio 8. Observabilidad de microservicios Python con OpenTelemetry](Capitulo08/README.md)

- **Descripción**: Instrumentar los servicios con OpenTelemetry y desplegar Collector, Jaeger, Prometheus, Alertmanager y Grafana. Correlacionar trazas distribuidas y logs JSON, visualizar métricas de solicitudes, errores y duración, y comprobar alertas de latencia y errores sin sustituir la lógica ni la seguridad de las aplicaciones existentes.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 9: Contenerización, imágenes y despliegue con Docker y Helm

#### [Laboratorio 9. Imágenes optimizadas y despliegues con Helm](Capitulo09/README.md)

- **Descripción**: Construir imágenes Docker con etapas múltiples y usuario no root, medir su tamaño frente a una imagen base y analizar vulnerabilidades con Trivy. Parametrizar un chart Helm para los tres servicios, publicar las imágenes en el registry local de minikube y verificar despliegues, actualizaciones y rollback mediante revisiones y digests.
- ⏱️ **Duración estimada**: 66 min de trabajo guiado; reservar 30–60 min adicionales para la primera preparación.

### Capítulo 10: Orquestación con Kubernetes y service mesh

#### [Laboratorio 10. Microservicios Python con Istio](Capitulo10/README.md)

- **Descripción**: Incorporar Pedidos, Inventario y Usuarios al service mesh de Istio, habilitar sidecars y comprobar mTLS estricto entre las cargas seleccionadas. Ejecutar despliegues canary de Pedidos y blue/green de Inventario por encabezado, validar la distribución del tráfico y consultar las señales de observabilidad del mesh.
- ⏱️ **Duración estimada**: 66 min.

### Capítulo 11: CI/CD, GitOps y automatización

#### [Laboratorio 11. Pipeline desde commit hasta Kubernetes con GitOps](Capitulo11/README.md)

- **Descripción**: Separar el código de aplicación y la configuración GitOps en dos repositorios. Automatizar pruebas, cobertura, construcción, escaneo y publicación de imágenes mediante GitHub Actions; desplegar Pedidos por digest con Argo CD. Comprobar self-healing y utilizar un observador que verifica la release y revierte en Git una promoción fallida.
- ⏱️ **Duración estimada**: 66 min según el temario.
- **Observación de planificación**: la guía revisada recomienda 90–120 min de sesión para incluir esperas de CI y recuperación.

### Capítulo 12: Pruebas avanzadas, chaos engineering y operación en producción

#### [Laboratorio 12. Carga, caos controlado y SLOs](Capitulo12/README.md)

- **Descripción**: Diseñar escenarios smoke, load, stress y spike con k6 y observar sus resultados en Prometheus y Grafana. Inyectar fallos de pods, red y recursos con Chaos Mesh sobre el entorno local del curso; comprobar contratos durante el fallo, evaluar indicadores y objetivos de servicio y documentar la recuperación en un postmortem con evidencias.
- ⏱️ **Duración estimada**: 66 min según el temario.
- **Observación de planificación**: la guía revisada recomienda 90–120 min para los experimentos con baseline y recuperación; señala que los 66 min originales resultaban insuficientes. Requiere el laboratorio 11 operativo y las herramientas preparadas.

---

## 📬 Contacto y más información

Si tienes alguna pregunta o necesitas más detalles, no dudes en [contactarnos](mailto:soporte@netec.com). También puedes encontrar más recursos en nuestra [página](https://netec.com).

---

¡Gracias por visitar nuestra plataforma! Revisa los requisitos de cada laboratorio y realiza las prácticas en el orden indicado.
