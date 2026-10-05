#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Missing local Python environment. See BUILD.txt.' >&2
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  echo 'Missing frontend build. Run pnpm build in frontend first.' >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
