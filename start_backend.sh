#!/bin/bash
# Detectar el directorio actual del script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Activar venv si existe
if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=.
exec python3 kraken_bot/web_server/server.py
