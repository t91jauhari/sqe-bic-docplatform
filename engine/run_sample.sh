#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  echo 'Created .env. Edit LLAMA_CLOUD_API_KEY, then run this script again.'
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py "$@"
