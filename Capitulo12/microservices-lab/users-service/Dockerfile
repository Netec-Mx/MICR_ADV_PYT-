# syntax=docker/dockerfile:1
ARG BASE_IMAGE=python:3.12.14-slim-bookworm
FROM $BASE_IMAGE AS builder
WORKDIR /build
ARG REQUIREMENTS_LOCK=requirements-lock.txt
COPY users-service/${REQUIREMENTS_LOCK} ./requirements-lock.txt
RUN --mount=type=cache,target=/root/.cache/pip python -m pip wheel --only-binary=:all: --wheel-dir=/wheels -r requirements-lock.txt
FROM $BASE_IMAGE AS runtime
COPY --from=builder /build/requirements-lock.txt /tmp/requirements-lock.txt
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements-lock.txt && python -m pip check && rm -f /tmp/requirements-lock.txt
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1
ARG APP_VERSION=9.1.0
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.title="users-service" org.opencontainers.image.version="$APP_VERSION"
RUN groupadd --gid 10001 appgroup && useradd --uid 10001 --gid 10001 --no-create-home appuser
WORKDIR /app
COPY shared/ ./shared/
COPY users-service/app/ ./app/
USER 10001:10001
EXPOSE 8003
CMD ["python", "-m", "shared.vault.launcher", "--port", "8003"]
