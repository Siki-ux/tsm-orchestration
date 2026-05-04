ARG BASE_IMAGE_REGISTRY=tomcat
ARG BASE_IMAGE_TAG=11

FROM ${BASE_IMAGE_REGISTRY}:${BASE_IMAGE_TAG}

ARG BUILD_DATE=""
ARG VCS_REF=""

LABEL maintainer="The ZID Team" \
    org.opencontainers.image.title="time.IO FROST-Server Image" \
    org.opencontainers.image.licenses="EUPL-1.2" \
    org.opencontainers.image.version="0.1" \
    org.opencontainers.image.revision=$VCS_REF \
    org.opencontainers.image.created=$BUILD_DATE

EXPOSE 8080

ARG FROST_VERSION=2.5.3
ARG UID=1000
ARG GID=1000
ARG FROST_URL=https://repo1.maven.org/maven2/de/fraunhofer/iosb/ilt/FROST-Server/FROST-Server.HTTP/$FROST_VERSION/FROST-Server.HTTP-$FROST_VERSION.war
ARG POSTGIS_JDBC_URL=https://repo1.maven.org/maven2/net/postgis/postgis-jdbc/2024.1.0/postgis-jdbc-2024.1.0.jar
ARG POSTGRESQL_URL=https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar

LABEL maintainer="The ZID Team" \
    org.opencontainers.image.title="time.IO FROST-Server Image" \
    org.opencontainers.image.licenses="EUPL-1.2" \
    org.opencontainers.image.version="0.1" \
    org.opencontainers.image.revision=$VCS_REF \
    org.opencontainers.image.created=$BUILD_DATE

COPY --chown=${UID}:${GID} index.jsp /usr/local/tomcat/webapps/ROOT/index.jsp

# Create a tomcat user with the UID and GID specified in the build arguments
# If the UID is already in use, just print out the info
RUN mkdir -p $CATALINA_HOME/conf/Catalina/localhost \
    && apt-get -y update && apt-get -y install wget \
    && apt-get clean \
    && addgroup --system --gid ${GID} tomcat \
    && adduser --system --uid ${UID} --gid ${GID} --home /home/tomcat tomcat \
    || echo "The UID '${UID}' is already in use."

ARG SKIP_SSL_VERIFY=false

# Download the FROST-Server.war, postgis-jdbc.jar, and postgresql.jar files
# Create the /share directory and set the owner to the UID user
RUN WGET_OPTS=""; \
    if [ "$SKIP_SSL_VERIFY" = "true" ]; then WGET_OPTS="--no-check-certificate"; fi; \
    mkdir -p $CATALINA_HOME/conf/Catalina/localhost \
    && mkdir -p /share \
    && wget $WGET_OPTS --show-progress=off -O $CATALINA_HOME/lib/postgis-jdbc.jar $POSTGIS_JDBC_URL \
    && wget $WGET_OPTS --show-progress=off -O $CATALINA_HOME/lib/postgresql.jar $POSTGRESQL_URL \
    && wget $WGET_OPTS --show-progress=off -O /share/FROST-Server.war $FROST_URL \
    && chown -R ${UID}:${GID} $CATALINA_HOME \
    && chown -R ${UID}:${GID} /share

# Add the root ca-certificates to the user's .postgresql directory
RUN mkdir ${HOME}/.postgresql \
    && cp /etc/ssl/certs/ca-certificates.crt ${HOME}/.postgresql/root.crt

USER ${UID}