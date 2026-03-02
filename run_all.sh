#!/bin/bash
# Script para iniciar el Bot y el Dashboard (Sentinel 2026)

# Detectar el directorio del script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Determinar el ejecutable de python (preferir venv)
if [ -d "venv" ]; then
    PYTHON_EXEC="./venv/bin/python3"
elif [ -d ".venv" ]; then
    PYTHON_EXEC="./.venv/bin/python3"
else
    PYTHON_EXEC="python3"
fi

# Asegurar que el directorio raíz esté en PYTHONPATH
export PYTHONPATH=$DIR

echo ""
echo "--- INICIANDO KRAKEN SENTINEL 2026 (Modo Integrado) ---"
echo "Dashboard: http://localhost:8000"
echo "Para detener, pulsa Ctrl+C"
echo "-------------------------------------------------------"

# Ejecutar el servidor uvicorn integrado usando el ejecutable específico
$PYTHON_EXEC run_all.py
