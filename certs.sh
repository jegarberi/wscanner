#!/bin/sh
# Genera un certificado autofirmado si no se montó uno propio en /etc/nginx/certs
set -e
DIR=/etc/nginx/certs
mkdir -p "$DIR"
if [ ! -s "$DIR/cert.pem" ] || [ ! -s "$DIR/key.pem" ]; then
  CN="${SERVER_NAME:-scanner3d.local}"
  SAN="DNS:localhost,DNS:${CN},IP:127.0.0.1"
  if [ -n "$SERVER_IP" ]; then SAN="$SAN,IP:$SERVER_IP"; fi
  echo "certs.sh: generando certificado autofirmado (CN=$CN, SAN=$SAN)"
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$DIR/key.pem" -out "$DIR/cert.pem" \
    -subj "/CN=$CN" -addext "subjectAltName=$SAN" >/dev/null 2>&1
fi
