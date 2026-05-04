ARG BASE_IMAGE_REGISTRY=debian
ARG BASE_IMAGE_TAG=stable-slim

FROM ${BASE_IMAGE_REGISTRY}:${BASE_IMAGE_TAG}

ARG BUILD_DATE
ARG VCS_REF
ARG SUPERCRONIC_VERSION=0.2.33

LABEL maintainer="The ZID Team" \
    org.opencontainers.image.title="time.IO Cron-Scheduler Image" \
    org.opencontainers.image.licenses="EUPL-1.2" \
    org.opencontainers.image.version="0.1" \
    org.opencontainers.image.revision=$VCS_REF \
    org.opencontainers.image.created=$BUILD_DATE

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini python3 python3-venv inotify-tools \
    && rm -rf /var/lib/apt/\
    && rm -rf /etc/cron.*/*

COPY src/requirements.txt .
COPY cron/supercronic-entrypoint.sh .
COPY cron/supercronic-health.sh .

ARG SKIP_SSL_VERIFY=false

RUN if [ "$SKIP_SSL_VERIFY" = "true" ]; then \
      curl -fsSLO --insecure https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64; \
    else \
      curl -fsSLO https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64; \
    fi \
    && chmod 755 supercronic-linux-amd64 \
    && mv supercronic-linux-amd64 /usr/local/bin/supercronic \
    && chmod 755 /supercronic-entrypoint.sh \
    && chmod 755 /supercronic-health.sh

RUN python3 -m venv /opt/venv
RUN if [ "$SKIP_SSL_VERIFY" = "true" ]; then \
      echo 'charset-normalizer!=3.4.7' > /tmp/constraints.txt && \
      /opt/venv/bin/pip install --no-cache-dir \
        --trusted-host pypi.org --trusted-host files.pythonhosted.org \
        --trusted-host codebase.helmholtz.cloud --trusted-host jfrog-pkg-proxy.it.att.com \
        -c /tmp/constraints.txt \
        -r requirements.txt; \
    else \
      /opt/venv/bin/pip install --no-cache-dir -r requirements.txt; \
    fi
ENV PATH="/opt/venv/bin:$PATH"

ARG UID=1000
ARG USER=tsm

RUN useradd --uid ${UID} -m -d /home/${USER} -s /bin/bash ${USER}

ENV PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
ENV STDOUT=/proc/1/fd/1
ENV STDERR=/proc/1/fd/2
ENV PYTHONPATH=/scripts/timeio

USER ${UID}

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "/supercronic-entrypoint.sh"]
