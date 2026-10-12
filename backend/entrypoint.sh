#!/usr/bin/env bash
set -euo pipefail
python -m migration_gate
alembic upgrade head
exec uvicorn main:app --workers 1 --host 0.0.0.0 --port 80
