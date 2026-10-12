#!/bin/sh
set -e

node /app/runtime-config.mjs /app/dist /app/serve.json /tmp/serve.json

exec serve -s dist -l 3000 -c /tmp/serve.json
