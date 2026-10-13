FROM debian:trixie-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./

RUN uv python install 3.13 \
    && uv sync --frozen --no-install-project --no-group dev \
    && .venv/bin/python -c "import sqlite3; v = sqlite3.sqlite_version_info; assert v >= (3, 51, 3), v; print('SQLite', sqlite3.sqlite_version)"


FROM debian:trixie-slim AS runtime

LABEL io.ciphermoth.min-updater-protocol="3"

ENV PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    CIPHERMOTH_DATA_DIR=/data \
    CIPHERMOTH_API_URL=http://localhost/api

RUN useradd -m -u 1000 -s /bin/bash ciphermoth

WORKDIR /app/src

COPY --from=builder /opt/python /opt/python
COPY --from=builder /app/.venv /app/.venv
COPY backend/ .
RUN chmod +x entrypoint.sh
RUN printf '#!/bin/sh\nexec python /app/src/cli.py "$@"\n' > /usr/local/bin/ciphermoth \
    && printf '#!/bin/sh\nexec python /app/src/vault_admin.py "$@"\n' > /usr/local/bin/ciphermoth-admin \
    && chmod +x /usr/local/bin/ciphermoth /usr/local/bin/ciphermoth-admin
RUN mkdir -m 0700 /data && chown ciphermoth:ciphermoth /data

USER ciphermoth

VOLUME ["/data"]

CMD ["./entrypoint.sh"]
