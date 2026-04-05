#!/bin/sh
sed "s|__GITHUB_OAUTH_SECRET__|$GITHUB_OAUTH_SECRET|g" /conf/homeserver.tmpl > /tmp/homeserver.yaml
nginx
exec python3 -m synapse.app.homeserver --config-path /tmp/homeserver.yaml
