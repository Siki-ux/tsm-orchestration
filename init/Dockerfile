ARG BASE_IMAGE_REGISTRY=alpine
ARG BASE_IMAGE_TAG=latest

FROM ${BASE_IMAGE_REGISTRY}:${BASE_IMAGE_TAG}
ARG UID=1000
ARG SKIP_SSL_VERIFY=false

ARG BUILD_DATE
ARG VCS_REF

LABEL maintainer="The ZID Team" \
    org.opencontainers.image.title="time.IO Init Image" \
    org.opencontainers.image.licenses="EUPL-1.2" \
    org.opencontainers.image.version="0.1" \
    org.opencontainers.image.revision=$VCS_REF \
    org.opencontainers.image.created=$BUILD_DATE

RUN if [ "$SKIP_SSL_VERIFY" = "true" ]; then \
      echo "http://dl-cdn.alpinelinux.org/alpine/v3.23/main" > /etc/apk/repositories && \
      echo "http://dl-cdn.alpinelinux.org/alpine/v3.23/community" >> /etc/apk/repositories; \
    fi && \
    apk add --no-cache \
    openssh-keygen \
    openssl \
    tree
RUN adduser -u ${UID} -D tsm
COPY init.sh /init.sh
RUN chown tsm /init.sh
USER tsm
RUN mkdir /home/tsm/html
RUN mkdir -p /tmp/volume/minio \
    && mkdir -p /tmp/volume/cron \
    && mkdir -p /tmp/volume/database \
    && mkdir -p /tmp/volume/mqtt

CMD ["/init.sh"]