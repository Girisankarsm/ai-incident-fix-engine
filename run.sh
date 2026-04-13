#!/usr/bin/env zsh

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
if ! python -c "import fastapi, uvicorn, dotenv, groq, requests" >/dev/null 2>&1; then
  pip install -q -r "$ROOT_DIR/requirements.txt"
fi

cd "$ROOT_DIR/backend"
if [ "${DEV_RELOAD:-0}" = "1" ]; then
  exec uvicorn main:app --reload --host 127.0.0.1 --port 8000
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
