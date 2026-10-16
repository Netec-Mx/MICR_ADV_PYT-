# Lab 10: verificación de la revisión

Fecha: 2026-10-08. Esta entrega conserva los objetivos del laboratorio y el código acumulativo. Las comprobaciones locales no sustituyen las pruebas del mesh desplegado.

## Pruebas ejecutadas

**273 pruebas distintas aprobadas y 1 omitida.** Se evita contar dos veces las pruebas de observabilidad repetidas con el empaquetado.

| Área | Aprobadas |
|---|---:|
| Orders | 119 |
| Inventory | 57 |
| Users | 7 |
| Vault e integración acumulativa | 29 |
| Observabilidad | 8 |
| Empaquetado e imágenes | 30 |
| Identidad de release, validador de tráfico y chart del mesh | 23 |
| Total | 273 |

Las pruebas de integración afectadas se repitieron tras preservar el PYTHONPATH de los procesos hijos. Esas pruebas ejercitan el launcher real, los encabezados de variante/versiones, PostgreSQL, Redis, validación JWT y entrega OTLP, con los dobles de infraestructura definidos en la suite para Vault/TokenReview. La prueba opcional de la cadena completa Collector/Jaeger/Grafana quedó omitida por las limitaciones de procesos, procfs e IPC del entorno. No se ejecutó aquí un broker Kafka real.

## Manifests y herramientas

- Helm: render de las tres releases con mesh habilitado; pruebas del chart y compatibilidad con el modo del Lab 9.
- Esquema oficial de Kubernetes 1.35.8: **38 recursos distintos**, 14 de aplicaciones y 24 de observabilidad. Los 14 recursos de aplicaciones se validaron de nuevo tras la inyección local: 52 instancias de validación, no 52 recursos distintos.
- Istio 1.31.1: generación del manifiesto de instalación y validación de 17 objetos de políticas contando los cuatro estados de tráfico alternativos. En una etapa se aplican únicamente su archivo de rutas y las políticas comunes.
- `istioctl analyze --use-kube=false --failure-threshold Error`: sin problemas de configuración sobre los manifests locales de aplicaciones, observabilidad, instalación y políticas.
- Inyección local con `istioctl kube-inject`, utilizando la configuración oficial de la instalación y un stub local de descubrimiento de webhooks: cinco Deployments con proxy, probes reescritos y métricas fusionadas. Se verificó la conservación de UID/fsGroup 10001, token Vault con audience `vault`, token Istio con audience `istio-ca` y ausencia del token Vault en los mounts del proxy.
- `promtool check config --syntax-only`: configuración Prometheus válida. Esta comprobación no valida conectividad de scrapes ni consulta series reales de Envoy.
- Sintaxis de todos los archivos Python y de los scripts Bash nuevos: válida.

## Comprobaciones pendientes en el clúster del alumno

No hay Docker ni minikube en el entorno de revisión: no se construyeron/publicaron las imágenes 10.0.0/10.1.0, ni se instaló Istio en un clúster. No se midieron aquí tráfico canary real, negociación mTLS, scrapes de Envoy o paneles con series del mesh.

`scripts/lab10/validate_all.sh` comprueba esas condiciones con respuestas reales, controles de conectividad, cabeceras de release, contadores mTLS, targets de Prometheus y el flujo de negocio acumulativo. El validador estadístico usa una muestra de 400 solicitudes por etapa; sus pruebas unitarias validan sus criterios de aceptación, no acreditan un despliegue Istio.

La guía diferencia cifrado entre las aplicaciones, acceso original a backends y scrape interno en 15020. La reversión recupera las revisiones Helm capturadas antes del ejercicio y no revierte datos de negocio.
