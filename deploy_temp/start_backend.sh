#!/bin/bash
cd /home/daniel/proyectos/Bot_agresivo
source venv/bin/activate
export PYTHONPATH=.
exec python3 kraken_bot/web_server/server.py
