FROM matrixdotorg/synapse:latest

USER root
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

COPY homeserver.yaml.tmpl /conf/homeserver.tmpl
COPY log.config /conf/log.config
COPY nginx.conf /etc/nginx/sites-enabled/default
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
