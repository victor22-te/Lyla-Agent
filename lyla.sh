#!/usr/bin/env bash
# Launcher rápido para LYLA (Spider-Man 2099)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "Inicializando entorno virtual..."
    python3 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python -m lyla.cli "$@"
