#!/bin/sh
mkdir -p /tmp/e2e-error
echo "<h1>CipherMoth cannot start</h1><p>e2e: synthetic configuration error</p>" > /tmp/e2e-error/index.html
exec serve -s /tmp/e2e-error -l 3000
