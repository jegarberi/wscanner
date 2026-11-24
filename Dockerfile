# Escáner 3D webcam: sitio estático servido por nginx con http y https
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY certs.sh /docker-entrypoint.d/05-certs.sh
COPY index.html README.md /usr/share/nginx/html/

RUN chmod +x /docker-entrypoint.d/05-certs.sh

EXPOSE 80 443
