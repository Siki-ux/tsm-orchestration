ARG BASE_IMAGE_REGISTRY=python
ARG BASE_IMAGE_TAG=3.13-slim

# see https://hub.docker.com/_/python/
# e.g. python:3.13-slim
FROM ${BASE_IMAGE_REGISTRY}:${BASE_IMAGE_TAG} as base

ARG BUILD_DATE
ARG VCS_REF

LABEL maintainer="The ZID Team" \
    org.opencontainers.image.title="time.IO ConfigDB Updater Image" \
    org.opencontainers.image.licenses="EUPL-1.2" \
    org.opencontainers.image.version="0.1" \
    org.opencontainers.image.revision=$VCS_REF \
    org.opencontainers.image.created=$BUILD_DATE


FROM base as build

ARG SKIP_SSL_VERIFY=false

COPY src/requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv
RUN if [ "$SKIP_SSL_VERIFY" = "true" ]; then \
      echo 'charset-normalizer!=3.4.7' > /tmp/constraints.txt && \
      /opt/venv/bin/pip install --no-cache-dir \
        --trusted-host pypi.org --trusted-host files.pythonhosted.org \
        --trusted-host codebase.helmholtz.cloud --trusted-host jfrog-pkg-proxy.it.att.com \
        -c /tmp/constraints.txt \
        -r /tmp/requirements.txt; \
    else \
      /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi


FROM base AS dist

# copy the python binaries (with baked-in requirement packages) to the actual stage
COPY --from=build /opt/venv opt/venv
# first serach in /opt/venv/bin for binaries (e.g. python3)
ENV PATH="/opt/venv/bin:$PATH"

# create a non-root user and run all further commands as 'appuser'
ARG UID=1000
RUN adduser --uid ${UID} --disabled-password appuser
USER appuser

# Certificaters are needed if sslmode=verify-full
ENV PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
WORKDIR /home/appuser/app
COPY --chown=appuser src .

ENTRYPOINT ["python3"]


# RUN apk update && apk add bash gcc musl-dev libpq-dev

