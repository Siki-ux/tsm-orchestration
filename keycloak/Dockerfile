FROM quay.io/keycloak/keycloak:latest AS builder

# Copy custom provider JAR and themes into the image
COPY plugins/ /opt/keycloak/providers/
COPY themes/ /opt/keycloak/themes/

# Run the Keycloak build phase (Quarkus augmentation) once at image build time.
# These flags must match what the container will use at runtime.
# Runtime-only values (DB URL, credentials, hostname) are NOT needed here.
RUN /opt/keycloak/bin/kc.sh build \
    --db=postgres \
    --http-enabled=true \
    --health-enabled=true \
    --proxy-headers=xforwarded \
    --http-relative-path=/keycloak

FROM quay.io/keycloak/keycloak:latest
COPY --from=builder /opt/keycloak/ /opt/keycloak/
