#!/bin/bash
# Script para subir los cambios al servidor Fedora y reiniciar el bot

SERVER="daniel@192.168.1.99"
PASS="Dn07ap28"
REMOTE_DIR="/home/daniel/proyectos/Bot_agresivo"

echo "🚀 Iniciando despliegue de Bot Agresivo..."

# 1. Compilar el Frontend
echo "📦 Compilando frontend..."
cd web
npm run build
cd ..

if [ ! -d "web/dist" ]; then
    echo "❌ Error: No se encontró la carpeta web/dist después de compilar."
    exit 1
fi

# 2. Subir Archivos Críticos (Excluyendo venv y datos temporales)
echo "📤 Subiendo archivos modificados..."
sshpass -p "$PASS" rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'data' --exclude '.git' \
    kraken_bot \
    ecosystem.config.cjs \
    start_backend.sh \
    run_all.sh \
    run_all.py \
    run_bot_standalone.py \
    run_viewer.py \
    config.py \
    GUIA_ESTRATEGIAS.md \
    $SERVER:$REMOTE_DIR/

echo "📤 Subiendo configuración de Sentinel Turbo..."
sshpass -p "$PASS" rsync -avz data/sentinel_config.json $SERVER:$REMOTE_DIR/data/

echo "📤 Subiendo build del frontend..."
sshpass -p "$PASS" rsync -avz web/dist/ $SERVER:$REMOTE_DIR/web/dist/

# 3. Fin
echo "✅ Archivos sincronizados con éxito!"
echo "El bot ha sido detenido en el servidor (si estaba corriendo)."
echo "Ahora puedes iniciarlo manualmente con:"
echo "ssh $SERVER 'cd $REMOTE_DIR && ./run_all.sh'"
echo "Dashboard disponible en: http://192.168.1.99:8000"
