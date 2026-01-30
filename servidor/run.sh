#!/bin/bash
export MEXC_API_KEY=""
export MEXC_SECRET_KEY=""

# Database Init
# (handled by app startup)

# Run Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir .
