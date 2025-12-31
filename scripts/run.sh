#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d ".venv" ]]; then
  uv venv .venv
  uv pip install -r requirements.txt
fi

uv run python main.py
