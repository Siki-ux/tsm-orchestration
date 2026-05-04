ARG BASE_IMAGE_REGISTRY=debian
ARG BASE_IMAGE_TAG=stable-slim
# which python version is supported by the version:
# -> https://wiki.debian.org/Python#Supported_Python_Versions
# debian-trixie contains python 3.13

FROM ${BASE_IMAGE_REGISTRY}:${BASE_IMAGE_TAG} AS base

ARG BUILD_DATE
ARG VCS_REF

LABEL maintainer="The ZID Team" \
    org.opencontainers.image.title="time.IO Dispatcher Base Image" \
    org.opencontainers.image.licenses="EUPL-1.2" \
    org.opencontainers.image.version="0.1" \
    org.opencontainers.image.revision=$VCS_REF \
    org.opencontainers.image.created=$BUILD_DATE

RUN apt-get -y update \
    && apt-get -y dist-upgrade \
    && apt-get -y --no-install-recommends install \
      python3 \
      python3-tk \
      python3-venv \
      ca-certificates \
    && apt-get -y autoremove \
    && apt-get -y autoclean \
    && rm -rf /var/lib/apt

FROM base AS build

ARG SKIP_SSL_VERIFY=false

RUN apt-get -y update \
    && apt-get -y --no-install-recommends install \
      git openssh-client \
      curl \
      unzip

# Install minio mc client
RUN if [ "$SKIP_SSL_VERIFY" = "true" ]; then \
      curl --insecure https://dl.min.io/client/mc/release/linux-amd64/mc > /usr/local/bin/mc; \
    else \
      curl https://dl.min.io/client/mc/release/linux-amd64/mc > /usr/local/bin/mc; \
    fi \
    && chmod a+x /usr/local/bin/mc

# add requirements
COPY src/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv
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

# copy the minio client and the python binaries (with baked-in requirement packages)
# to the actual stage
COPY --from=build /usr/local/bin/mc /usr/local/bin/mc
COPY --from=build /opt/venv opt/venv
# first serach in /opt/venv/bin for binaries (e.g. python3)
ENV PATH="/opt/venv/bin:$PATH"

# Create a group and user and then tell docker to run all future commands as 'appuser'
ARG UID=1000
RUN useradd --uid $UID -m appuser
USER appuser

ENV PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
WORKDIR /home/appuser/app/src

COPY --chown=appuser src .

ENTRYPOINT ["python3"]
