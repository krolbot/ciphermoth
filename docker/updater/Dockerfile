FROM docker:27-cli

RUN apk add --no-cache \
      docker-cli-compose \
      cosign \
      postgresql16-client \
      python3 \
      curl \
      tini

LABEL io.ciphermoth.updater-protocol="2"

WORKDIR /work

COPY backend/pyproject.toml /usr/local/share/ciphermoth/pyproject.toml
COPY docker/updater/updater.py /usr/local/lib/ciphermoth/updater.py
COPY docker/updater/updater.sh /usr/local/bin/updater.sh
RUN chmod +x /usr/local/bin/updater.sh

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/updater.sh"]
