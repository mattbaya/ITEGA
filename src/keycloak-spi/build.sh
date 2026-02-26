#!/bin/bash
# Build the Newshare Keycloak SPI JAR
# Usage: ./build.sh
# Output: target/newshare-protocol-mapper-0.1.0.jar
# Copy the JAR to Keycloak's providers directory and restart Keycloak

set -e

cd "$(dirname "$0")"

mvn clean package -DskipTests

echo ""
echo "JAR built at: target/newshare-protocol-mapper-0.1.0.jar"
echo "Copy to Keycloak: cp target/newshare-protocol-mapper-0.1.0.jar /path/to/keycloak/providers/"
echo "Then restart Keycloak: docker compose restart keycloak"
