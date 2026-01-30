#!/bin/bash

source .venv/bin/activate
# Ejecutar servidor web (dashboard) y bot
nohup python -m kraken_bot.web_server > bot.log 2>&1 &
echo "Bot iniciado en segundo plano. Logs en bot.log"
echo "Dashboard disponible en http://localhost:8000"
