#!/bin/bash

# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Python y venv si no existen
sudo apt install -y python3 python3-venv python3-pip

# Crear entorno virtual
python3 -m venv .venv

# Activar entorno
source .venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

echo "Instalación completada. Ejecuta ./run.sh para iniciar el bot."
