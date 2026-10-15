# Laboratorio 11 · Pipeline desde commit hasta Kubernetes con GitOps

| Campo | Valor |
|---|---|
| Curso | Microservicios Avanzado · Python |
| Laboratorio | 11, acumulativo sobre el Lab 10 |
| Duración | 66 minutos de trabajo guiado; planifica 90–120 minutos de sesión con esperas de CI y recuperación. Descargas, cuentas y herramientas se preparan antes |
| Complejidad / Bloom | Alta / Crear |
| Plataforma | Ubuntu 24.04, amd64; perfil y contexto `msvc-gateway`; namespace `microservices` |
| Versiones de referencia | Python 3.12, Helm 3.20.1, Kubernetes 1.35.8, Istio 1.31.1, Argo CD 3.5.2, Trivy 0.75.0 |

## Resultado esperado

Automatizarás **Orders real**, conservando JWT, Vault, event store/CQRS, integración Kafka, Redis y observabilidad. Actions controla la calidad y publica una imagen; Argo CD controla el despliegue declarativo. Un observador local comprueba la revisión exacta, readiness y una prueba HTTP autenticada, y revierte en Git una promoción fallida.

```mermaid
flowchart TD
    A["Commit en ms-app-repo"] --> T["Tests y cobertura"]
    T --> B["Build y escaneo CRITICAL"]
    B --> Q{"¿Gates aprobados?"}
    Q -->|No| X["Detener promoción"]
    Q -->|Sí| R["GHCR: imagen por digest"]
    R --> G["Commit en ms-gitops-repo"]
    G --> C["Argo CD: reconciliación"]
    C --> O["Orders v1: rolling update"]
    O --> V{"¿Revisión Healthy y HTTP válido?"}
    V -->|Sí| E["Release validada"]
    V -->|No| D["Observador: git revert"]
    D --> G
    O --> S["Vault y backends existentes"]
```

El circuito de recuperación necesita el observador encendido. **Kubernetes no hace rollback automático por fallos de probes**: conserva réplicas anteriores con `maxUnavailable: 0` y reporta un rollout que no progresa. Argo CD tampoco revierte por sí solo un commit defectuoso. En esta práctica el observador crea el commit de reversión y Argo lo aplica.

## Objetivos

- [ ] Diseñar un pipeline GitHub Actions con tests, cobertura, validación, build, scan y publicación.
- [ ] Separar código de aplicación y configuración GitOps en dos repositorios.
- [ ] Configurar Argo CD con sincronización automática y self-healing.
- [ ] Exigir cobertura **≥80% sobre todos los módulos de `order-service/app`**, ninguna prueba de integración omitida y **cero CRITICAL**, incluyendo vulnerabilidades sin parche.
- [ ] Publicar el mismo archivo de imagen aprobado y desplegar por digest, sin reconstruir entre etapas.
- [ ] Demostrar rolling update, detección de drift y recuperación automática mediante Git.

## Correcciones frente al original

| Problema | Corrección |
|---|---|
| Orders sustituido por un diccionario en memoria y otro contrato | Se conserva el servicio acumulativo, sus migraciones e identidades |
| Namespace nuevo sin Vault/backends equivalentes | Se adopta Orders en `microservices` |
| Runner remoto accede a `localhost:5050` del alumno | GHCR accesible por HTTPS desde runner y nodos |
| Imagen disponible sólo en el filesystem del job de build | Archivo Docker aprobado transferido por artifact al job de publicación |
| Publicación antes del escaneo | Build → scan → artifact aprobado → push |
| `--ignore-unfixed` presentado como cero CRITICAL | Gate estricto, sin ignorar vulnerabilidades ni `.trivyignore` |
| GitOps usa una ruta local inexistente y omite push | Checkout del segundo repo, validación del chart, commit y push real |
| Servidor `git://` temporal sin flujo de recepción fiable | Repositorio GitHub HTTPS; credenciales fuera de Git |
| Valores con tag mutable y cambios por `sed` | Modificación estructurada de YAML y digest del registry |
| Probes implican rollback automático | Observador explícito con timeout, smoke y `git revert` |
| `argocd app rollback` con auto-sync | Reversión de Git, manteniendo una fuente de verdad |
| v1 pasa a GHCR y v2 pierde la referencia a su registry | `mesh.extra.repository` conserva el registry original |
| PR puede publicar/desplegar | Publicación sólo desde `main`, después del job de calidad |
| Dependencias de prueba heredadas incompatibles con Starlette | Schemathesis 4.30.0, pytest 8.4.2 y migración de sus pruebas de contrato |
| Limpieza borra namespaces, registry e imágenes del curso | Retiro de la Application sin cascada y recuperación de valores con Helm |

## Alcance y continuidad con el Lab 10

Orders mantiene nombre, puerto **8001**, ServiceAccount/rol Vault `order-service` y secretos fuera del repositorio. Inventory **8002** y Users **8003** siguen funcionando bajo sus releases Helm. Argo administra únicamente los recursos renderizados para Orders: dos Deployments v1/v2, Service, ConfigMap y ServiceAccount. No administra Vault, Kafka, bases, Istio ni observabilidad.

Antes de adoptar Orders, vuelve el tráfico a **100% del subset v1**. `v1` es la etiqueta de routing del Lab 10, no el número mayor del software: puede servir una imagen 11.0.0 o 11.1.0. El subset v2 permanece con su imagen 10.1.0 en el registry del Lab 9 y no recibe tráfico de Orders durante esta práctica. Ambas variantes siguen compartiendo datos.

El chart 1.2.0 permite 1–3 réplicas, conserva los selectors inmutables y añade repositorio de variante y referencias a `imagePullSecrets`. Se usan **dos réplicas por Deployment de Orders**; reserva capacidad adicional para sus proxies y `maxSurge: 1`. No hay HPA: introducirlo requeriría acordar con Argo qué controlador administra `spec.replicas`.

Las métricas fusionadas, mTLS y rutas del Lab 10 siguen activos. No ejecutes `scripts/lab10/validate_all.sh` para validar releases 11.x: su comprobación de identidad espera versiones 10.0.0/10.1.0. Usa los verificadores de este laboratorio y las pruebas de negocio del Lab 6.

## Materiales

Descomprime el ZIP y trabaja desde `microservices-lab/`. El código fuente entregado debe ser la raíz de `ms-app-repo`; no pongas `.github/` debajo de otra carpeta.

| Ruta | Función |
|---|---|
| `.github/workflows/lab11-ci-cd.yml` | Jobs quality y publish, acciones fijadas por SHA |
| `scripts/lab11/ci-tests.sh` | Cobertura y prohibición de skips de integración |
| `scripts/lab11/start-ci-services.sh` | PostgreSQL, Redis y Keycloak aislados para pruebas |
| `scripts/lab11/pipeline.sh` | Alternativa local con las mismas etapas |
| `scripts/lab11/gitops.py` | Preparación, validación, promoción, espera y recuperación |
| `scripts/lab11/smoke.py` | JWT, versión de release y consulta CQRS a través de Istio |
| `scripts/lab11/drift.py` | Prueba medible de self-healing |
| `scripts/lab11/cleanup.sh` | Recuperación de administración Helm |
| `tests-gitops/` | Reversión, concurrencia, estado y workflow |
| `reports/lab11/revision-verification.md` | Verificación realizada y límites |

## Preparación previa

1. Lab 10 operativo, Argo CD aún sin administrar Orders. Conserva sus capturas e imágenes; no reinicies minikube ni crees otro perfil.
2. Git, Docker Engine con acceso del usuario, Python 3.12, kubectl, Helm 3.20.1 y Trivy 0.75.0 disponibles. Docker debe descargar imágenes para los servicios CI y construir para `linux/amd64`. No se requiere `act`, Buildx separado ni Docker Compose.
3. Cuenta GitHub con Actions habilitado; crea **dos repositorios vacíos**: `ms-app-repo` y `ms-gitops-repo`. La ruta guiada usa el GitOps repo público, con configuración de laboratorio sin secretos; puede ser privado si registras credenciales de lectura en Argo.
4. Configura tu nombre/correo Git y autenticación local para ambos repositorios mediante GitHub CLI o un credential helper. No incrustes tokens en URLs.
5. Tokens separados: escritura **Contents** únicamente sobre el GitOps repo para CI (`GITOPS_WRITE_TOKEN`, PAT fine-grained); lectura de GHCR para nodos (PAT classic `read:packages`, con acceso al paquete y autorización SSO si corresponde). El `GITHUB_TOKEN` del workflow publica el paquete; no permite por defecto escribir en otro repo.
6. El paquete GHCR puede permanecer privado. Configura el Secret de pull antes de promover; **no se hace pública ninguna imagen automáticamente**.

Desde la raíz:

```bash
export KUBE_CONTEXT=msvc-gateway
export PATH="$HOME/.local/bin:$PATH"
kubectl --context "$KUBE_CONTEXT" get nodes
helm --kube-context "$KUBE_CONTEXT" list -n microservices
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r order-service/requirements-dev.txt
python -m pip check
export PYTHON_BIN=python
```

`.venv`, reportes operativos, tokens y estado CI están excluidos de Git. No añadas esos archivos con `git add -f`.

## 1. Separar y preparar los repositorios · 8 minutos

Convierte esta raíz en `ms-app-repo`, conservando código y archivos acumulativos. Si ya usas un repo existente, integra los archivos en él; no anides repositorios ni reinicialices una historia que quieres conservar.

Para una carpeta nueva sin `.git`:

```bash
git init -b main
git add .
git commit -m "feat: add cumulative Orders CI and GitOps lab"
git remote add origin https://github.com/TU_OWNER/ms-app-repo.git
git push -u origin main
```

Este primer push activa el workflow. **Todavía no configures `GITOPS_REPOSITORY`**: la ejecución inicial prepara/publica el paquete, pero no promueve a Kubernetes. Así puedes conceder lectura al paquete y crear el Secret antes del primer despliegue.

Vuelve el tráfico a v1 y prepara la captura de configuración, usando un directorio vacío que será el segundo repo:

```bash
kubectl --context "$KUBE_CONTEXT" -n microservices apply -f istio/routes-100-0.yaml
export GITOPS_DIR="$HOME/ms-gitops-repo"
python scripts/lab11/gitops.py prepare "$GITOPS_DIR" https://github.com/TU_OWNER/ms-gitops-repo.git
git -C "$GITOPS_DIR" push -u origin main
```

`prepare` copia el chart actualizado y los valores **reales** de la release. Conserva v2 en su repositorio original, establece dos réplicas y valida el render. Guarda los valores anteriores en `reports/lab11/before-values.yaml`; no publiques ese directorio. La configuración deseada queda en `charts/order-service/values.yaml` del segundo repo.

No captures valores que contengan secretos: el script rechaza las claves operativas prohibidas conocidas; revisa también cualquier personalización tuya antes del push.

## 2. Instalar Argo y adoptar Orders · 10 minutos

```bash
bash scripts/lab11/install-argocd.sh
bash scripts/lab11/configure-pull.sh
```

El primer script usa manifests upstream fijados en **3.5.2**, espera los componentes principales y configura tracking por anotaciones. No sobrescribe una instalación Argo ajena a la práctica. Si ya tienes Argo, revisa su versión y políticas antes de usar el instalador; éste está pensado para un namespace `argocd` dedicado al curso.

El segundo solicita usuario y PAT de lectura de GHCR sin mostrarlo; crea `microservices/lab11-ghcr-pull` a partir de un Docker config temporal. La cuenta debe tener acceso al paquete que publicó el workflow inicial. No guarda el token en el chart ni en Git.

Aplica la Application y el AppProject preparados:

```bash
kubectl --context "$KUBE_CONTEXT" apply -f reports/lab11/argo.yaml
BASELINE_SHA=$(git -C "$GITOPS_DIR" rev-parse HEAD)
python scripts/lab11/gitops.py wait "$BASELINE_SHA" --timeout 900
```

El proyecto permite sólo ese repo, namespace y tipos de recursos; la Application usa `releaseName: order-service`, auto-sync y self-heal, con **prune desactivado durante la adopción**. No lleva finalizer de cascada: la limpieza conservará las aplicaciones.

Helm se utiliza para renderizar; Argo no hace `helm upgrade` ni registra nuevas revisiones Helm. Durante la práctica **no ejecutes upgrades/rollbacks manuales de Orders ni el cleanup del Lab 10** mientras Argo siga reconciliando. Sus Secrets de historial Helm se conservan para la recuperación.

Para consultar la UI, abre un terminal independiente:

```bash
kubectl --context "$KUBE_CONTEXT" -n argocd port-forward svc/argocd-server 18443:443
```

Abre `https://localhost:18443`. La instalación de laboratorio usa certificado propio; acepta la excepción sólo para esta dirección local. Usuario `admin`; obtén la contraseña inicial sin guardarla en un repo:

```bash
kubectl --context "$KUBE_CONTEXT" -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
printf '\n'
```

Si el GitOps repo es privado, registra en Settings → Repositories su URL HTTPS y credencial **de sólo lectura** antes de aplicar/esperar la Application. No publiques el Secret resultante ni uses el token de escritura de CI para Argo.

## 3. Activar CI/CD y recuperación · 12 minutos

En Settings → Secrets and variables → Actions del **repo de aplicación**:

| Nombre | Tipo | Contenido |
|---|---|---|
| `GITOPS_REPOSITORY` | Variable | `TU_OWNER/ms-gitops-repo` |
| `GITOPS_WRITE_TOKEN` | Secret | Token con Contents read/write únicamente sobre ese repo |

Configura permisos del paquete GHCR para el repo de aplicación y la cuenta de lectura de los nodos. Si una política protege `main` en GitOps contra push directo, necesitarás un flujo con PR/aprobación; el laboratorio guiado usa un repo dedicado donde ese bot puede enviar la promoción directamente.

Mantén abiertos los port-forward del Lab 10, en terminales separadas:

```bash
kubectl --context "$KUBE_CONTEXT" -n istio-system port-forward svc/istio-ingressgateway 18080:80
```

```bash
kubectl --context "$KUBE_CONTEXT" -n microservices port-forward svc/keycloak 8080:8080
```

El observador necesita conectividad local a Kubernetes, Git, Keycloak y al gateway. Usa **otra copia de trabajo del mismo GitOps repo**, para que su polling no compita con tu editor o con el pipeline local:

```bash
git clone https://github.com/TU_OWNER/ms-gitops-repo.git "$HOME/ms-gitops-monitor"
git -C "$HOME/ms-gitops-monitor" config user.name "Lab11 Recovery"
git -C "$HOME/ms-gitops-monitor" config user.email "lab11-recovery@example.invalid"
python scripts/lab11/gitops.py monitor "$HOME/ms-gitops-monitor"
```

Deja ese terminal funcionando. Primero confirma la adopción baseline Healthy; después detecta commits nuevos en `main`. Para cada uno espera hasta 900 segundos, verifica **Synced + Healthy en el SHA exacto** y ejecuta el smoke JWT de Orders. Si falla, crea `git revert`, hace push y espera la recuperación. Una promoción revertida se registra como fallida, aunque el servicio anterior vuelva a estar sano.

El observador se detiene si hay cambios concurrentes, worktree sucio, conflictos o recuperación no saludable. Nunca hace force-push ni revierte un commit que contenga archivos ajenos a la única promoción de valores. **No es un controlador HA de producción**: si cierras el terminal, desaparece la recuperación automática de esta práctica.

Reejecuta ahora el workflow desde Actions → Run workflow sobre `main`. Las etapas son:

| Job / etapa | Gate o salida |
|---|---|
| quality: servicios aislados | PostgreSQL/Redis/Keycloak, sin usar datos del curso |
| quality: tests | Cobertura ≥80%, JUnit y cero skips de integración |
| quality: chart | Schema Helm y esquema oficial Kubernetes 1.35.8 |
| quality: build y scan | Archivo Docker; Trivy bloquea cualquier CRITICAL |
| publish | Descarga ese mismo archivo, lo carga y lo publica en GHCR |
| publish: GitOps | Checkout del segundo repo, render con valores reales, commit y push por digest |
| Argo / observador | Reconciliación, readiness y smoke; reversión si falla |

Un PR ejecuta calidad, sin publicar ni acceder al token GitOps. Cada job tiene su propio filesystem: el artifact transfiere la imagen aprobada, no una suposición de caché compartida. Actions no necesita kubeconfig ni acceso al API de Argo.

No soluciones un gate CRITICAL con `--ignore-unfixed`, `.trivyignore` o `continue-on-error`. Revisa `trivy.json`, actualiza base/dependencias, reconstruye y repite. El estado de vulnerabilidades cambia: no se promete que la imagen del laboratorio siga sin hallazgos en una fecha futura.

## 4. Validar una release y provocar un cambio · 10 minutos

En otra terminal, actualiza la copia de edición y comprueba la revisión exacta:

```bash
git -C "$GITOPS_DIR" pull --ff-only
DEPLOYED_SHA=$(git -C "$GITOPS_DIR" rev-parse HEAD)
python scripts/lab11/gitops.py wait "$DEPLOYED_SHA" --timeout 900
python scripts/lab11/smoke.py "$GITOPS_DIR"
python scripts/lab06/validate_gateway.py
```

El smoke exige `/api/v1/orders/release` con JSON `service=order-service`, `version=11.0.0`, headers `X-Lab-Variant: v1` y `X-Lab-Version: 11.0.0`; sin JWT debe responder 401. También consulta Orders CQRS. El validador del Lab 6 comprueba JWT, permisos y el flujo producto→pedido→reserva. Kafka se valida aquí en tu clúster, no mediante el contenedor CI.

Consulta los contenedores **por nombre**: la inyección puede poner al proxy primero en la lista.

```bash
kubectl --context "$KUBE_CONTEXT" -n microservices get deployment order-service -o jsonpath='{.spec.template.spec.containers[?(@.name=="order-service")].image}'
printf '\n'
kubectl --context "$KUBE_CONTEXT" -n microservices rollout status deployment/order-service --timeout=900s
kubectl --context "$KUBE_CONTEXT" -n microservices get pods -l app=order-service
```

La imagen debe ser `ghcr.io/tu_owner/lab11-order-service@sha256:...`; el Deployment v2 debe seguir referenciando `localhost:5000/order-service@sha256:...`. Observa dos réplicas y ambos contenedores Ready en los pods, o el estado equivalente de proxy nativo que emplee Istio.

La entrega incorpora un endpoint de release **antes** de la ruta dinámica UUID y protegido por `orders.read`; no agrega una colección de pedidos ficticia. Para practicar un cambio de código, amplía su modelo con un campo `capability: str = 'gitops'`, añade una aserción correspondiente en `test_release.py` y adapta el smoke para comprobarlo. Cambia además `APP_VERSION` del workflow a **11.1.0**. No basta con modificar sólo los values de GitOps para fingir una nueva build.

```bash
git add order-service/app/routers/cqrs.py order-service/tests/test_release.py scripts/lab11/smoke.py .github/workflows/lab11-ci-cd.yml
git commit -m "feat: expose GitOps capability in Orders release metadata"
git push origin main
```

El workflow construye y escanea la nueva imagen. El observador ejecuta `smoke.py` desde esta raíz como un proceso nuevo para cada promoción: leerá el smoke que acabas de actualizar. Mantén el terminal del observador abierto y verifica 11.1.0 con la misma secuencia.

## 5. Comprobar self-healing · 8 minutos

```bash
python scripts/lab11/drift.py
```

El script exige baseline de dos réplicas, escala temporalmente v1 a tres y espera hasta cuatro minutos. Sólo aprueba cuando `spec.replicas=2`, la generación está observada y hay dos réplicas Ready. El polling evita confundir un `sleep 30` con una verificación.

La detección de drift actúa sobre el estado de Kubernetes; no cambia Git ni revierte datos de pedidos. El rolling update también comparte datos. Este laboratorio no introduce migraciones incompatibles ni presenta la reversión de imagen como recuperación de base de datos.

## 6. Probar la recuperación automática · 18 minutos

Deja el observador encendido, espera que no haya otro pipeline activo y actualiza tu copia GitOps. Esta es una **inyección deliberada de fallo** directamente en el repo de configuración, no una publicación aprobada por CI:

```bash
git -C "$GITOPS_DIR" pull --ff-only
export GITOPS_DIR
python - <<'PY'
import os,yaml
from pathlib import Path
p=Path(os.environ['GITOPS_DIR'])/'charts/order-service/values.yaml'
v=yaml.safe_load(p.read_text());v['image']['digest']='sha256:'+'0'*64
p.write_text(yaml.safe_dump(v,sort_keys=False))
PY
python scripts/lab11/gitops.py render "$GITOPS_DIR"
git -C "$GITOPS_DIR" add charts/order-service/values.yaml
git -C "$GITOPS_DIR" commit -m "test: inject unavailable image digest"
git -C "$GITOPS_DIR" push origin main
```

El manifiesto es estructuralmente válido, pero el digest no existe. Observa:

```bash
kubectl --context "$KUBE_CONTEXT" -n microservices get pods -l app=order-service -w
```

Los pods nuevos fallarán al descargar la imagen; `maxUnavailable: 0` mantiene los antiguos, sujeto a su salud y a la capacidad del clúster. La Application no debería llegar al estado Healthy de esa revisión. Tras el timeout, el observador hace revert y espera otra revisión Healthy. El timeout de recuperación es independiente; un problema de red o de infraestructura puede requerir más tiempo que los 18 minutos guiados.

Verifica la evidencia:

```bash
git -C "$GITOPS_DIR" pull --ff-only
git -C "$GITOPS_DIR" log --oneline -4
RECOVERY_SHA=$(git -C "$GITOPS_DIR" rev-parse HEAD)
python scripts/lab11/gitops.py wait "$RECOVERY_SHA" --timeout 900
python scripts/lab11/smoke.py "$GITOPS_DIR"
```

Debe haber un commit de fallo y otro `Revert`, recuperar el digest anterior y aprobar el smoke de esa versión. Si el observador rechaza la reversión por cambios concurrentes, revisa el historial y resuelve explícitamente; no cambies el digest a mano en Kubernetes porque Argo lo volverá a reconciliar desde Git.

## Alternativa: pipeline local

Mantiene los mismos gates; no simula que se ejecutó GitHub Actions. Necesita Docker, Helm, Trivy, autenticación de push GHCR y GitOps, y una copia **limpia y actualizada** del segundo repo. No uses la copia del monitor.

```bash
bash scripts/lab11/start-ci-services.sh
export POSTGRES_TEST_ADMIN_URL='postgresql+asyncpg://postgres:lab11-ci-pass@localhost:15432/postgres'
export REDIS_TEST_URL='redis://localhost:16379/0'
export KEYCLOAK_TEST_ISSUER='http://localhost:18081/realms/microservices-lab'
export IMAGE_REPOSITORY=ghcr.io/tu_owner/lab11-order-service
export APP_VERSION=11.0.0
git -C "$GITOPS_DIR" pull --ff-only
docker login ghcr.io
bash scripts/lab11/pipeline.sh
bash scripts/lab11/stop-ci-services.sh
```

Si el pipeline falla, ejecuta igualmente `stop-ci-services.sh`. El script sólo elimina sus tres contenedores `lab11-ci-*`; no toca los backends del curso. Si ya existen esos contenedores por una ejecución interrumpida, deténlos con ese script antes de volver a iniciar. No cambies `APP_VERSION` local sin mantenerlo alineado con el workflow y con el código que vas a promover.

## Evidencia y criterios de éxito

| Evidencia | Condición |
|---|---|
| Reports de Actions | Tests sin skips de integración, cobertura ≥80%, scan CRITICAL vacío |
| Registro | Tag SHA completo e imagen promovida por digest |
| GitOps | Commit con digest/version y SHA del código; push real al segundo repo |
| Argo | Synced + Healthy en el commit deseado, no en uno anterior |
| Orders | Dos réplicas v1 Ready; identidad y acceso Vault originales |
| HTTP | JWT requerido, release/version correctas y consulta CQRS válida |
| Negocio acumulativo | Validador Lab 6 aprobado con Kafka real del clúster |
| Self-healing | De tres a dos réplicas, generación observada y readiness |
| Recuperación | Fallo detectado, commit `Revert`, digest anterior y smoke aprobado |

Conserva artifacts, SHAs, log del observador y tiempos observados. No basta contar tags, mostrar pods antiguos Running ni imprimir una marca de éxito al final de un script.

## Recuperar administración Helm

Primero termina el observador con Ctrl+C en su propio terminal y deshabilita futuras promociones del workflow: elimina la variable `GITOPS_REPOSITORY` o deshabilita ese workflow en Actions. Espera que no haya jobs activos. Después:

```bash
bash scripts/lab11/cleanup.sh
```

Se elimina la Application **sin cascada**, luego se recuperan los valores capturados de Orders con el chart compatible 1.2.0 y se elimina el Secret de pull que ya no se referencia. El tráfico permanece en v1, como en la preparación. Argo instalado, repositorios, imágenes, PVC, datos, Istio y otros servicios permanecen disponibles.

No ejecutes `helm uninstall order-service`, no borres namespaces y no limpies todas las imágenes Docker. Tampoco uses el rollback de Helm mientras Argo aún administre la Application.

## Diagnóstico

| Síntoma | Qué revisar |
|---|---|
| CI no instala dependencias | Usa `requirements-dev.txt` revisado y Python 3.12; ejecuta `pip check` |
| Tests omiten PostgreSQL/Redis/Keycloak | Variables y arranque CI: omisiones hacen fallar el gate |
| Migración dice `role order_app does not exist` | Arranque CI crea ese rol de prueba antes de los tests |
| Trivy bloquea una dependencia/base | Revisa artifact JSON; remedia y reconstruye, sin excluir CRITICAL |
| `ImagePullBackOff` con GHCR válido | Secret, permisos del paquete, digest y arquitectura amd64 |
| `ComparisonError` | URL/path/branch del repo, lectura de Argo, schema del chart |
| Argo no cambia el clúster | Adoption Synced/Healthy, proyecto/destino, auto-sync y self-heal |
| Smoke ve v2 o una versión 10.x | Rutas Orders 100/0, convergencia Istio y digest/revisión de v1 |
| 503 de Orders | Readiness Vault/DB, logs del contenedor `order-service`, conectividad a backends |
| No ocurre recuperación automática | Terminal del monitor, credencial de push y SHA observado |
| Revert rechazado | No se sobrescribe un commit posterior; inspecciona cambios concurrentes |

## Verificación de esta entrega

Consulta `reports/lab11/revision-verification.md`. La revisión diferencia pruebas ejecutadas, checks estáticos y verificaciones pendientes de infraestructura. Aquí no se enviaron commits a tus repositorios, no se publicaron imágenes ni se desplegó Argo en tu clúster.

## Referencias

- [Argo CD: automated sync y límites de rollback](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)
- [Argo CD: tracking por anotaciones](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_tracking/)
- [Argo CD 3.5.2: manifiesto fijado](https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.2/manifests/install.yaml)
- [Kubernetes: Deployment, progreso y rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [GitHub: autenticación y acceso GHCR](https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub: seguridad de Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- [Schemathesis: migración de v3 a v4](https://github.com/schemathesis/schemathesis/blob/master/MIGRATION.md)
