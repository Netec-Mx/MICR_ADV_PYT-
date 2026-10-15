# Laboratorio 10 · Microservicios Avanzado

Guía principal: **[LAB10.md](LAB10.md)**. Solución acumulativa con Istio, mTLS entre las aplicaciones, canary de Orders, blue/green de Inventory y métricas por versión. Parte del Lab 9 funcionando; conserva sus informes de imágenes por digest.

Sigue la preparación, el cambio de ingreso y las validaciones de la guía. Resultados y límites de revisión: [reports/lab10/revision-verification.md](reports/lab10/revision-verification.md).

# Laboratorio 9 · Microservicios Avanzado

Guía principal: **[LAB09.md](LAB09.md)**. Empaquetado acumulativo, imágenes equivalentes, remediación Trivy, registry local y un chart Helm para las tres aplicaciones.

Parte de un Lab 8 funcionando. Sigue la secuencia 9.0.0 → upgrade/rollback → despliegue final 9.1.0. Las dependencias actuales están corregidas; `requirements-baseline*.txt` se conserva solo para la comparación didáctica. Verificación y límites: [reports/lab09/revision-verification.md](reports/lab09/revision-verification.md).

# Laboratorio 8 · Microservicios Avanzado

Guía principal: **[LAB08.md](LAB08.md)**. Código acumulativo con Vault, tracing, métricas RED, logs correlacionados y stack Helm de observabilidad.

Con Lab 7 operativo: `bash scripts/lab08/deploy.sh`; abre los port-forward y ejecuta `bash scripts/lab08/validate_all.sh`. Consulta la guía para prerrequisitos y límites de verificación.

# Laboratorio 7 · Microservicios Avanzado

Guía principal: **[LAB07.md](LAB07.md)**. Esta entrega contiene el código acumulativo revisado y la integración de Vault para los tres servicios.

Con Lab 6 operativo: `bash scripts/lab07/deploy.sh` y después `bash scripts/lab07/validate_all.sh`. Los detalles, prerrequisitos y límites de verificación están en LAB07.md.

# Microservicios Avanzado · Laboratorio 6

Solución acumulativa de los laboratorios 1–6. Sigue [LAB06.md](LAB06.md) para despliegue minikube/Helm, JWT, Gateway, curl y pruebas de políticas.

Python 3.12. Traefik 3.7.14 / chart 41.7.0 incluido. PostgreSQL, Kafka, Redis y Keycloak se despliegan en Kubernetes; Users es un servicio de demostración.
