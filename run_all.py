#!/usr/bin/env python3
import os
import sys

# Ensure the project root is in PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Import and run the integrated server
from kraken_bot.web_server.server import app
import uvicorn

if __name__ == "__main__":
    print("--- INICIANDO KRAKEN SENTINEL 2026 (Modo Integrado) ---")
    print("Dashboard: http://localhost:8000")
    print("-------------------------------------------------------")
    
    # Run uvicorn server which starts the bot lifespan
    uvicorn.run("kraken_bot.web_server.server:app", host="0.0.0.0", port=8000, reload=False)
