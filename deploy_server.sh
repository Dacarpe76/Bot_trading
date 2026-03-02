#!/bin/bash
# Script de configuración para el Servidor Fedora

echo "--- Iniciando Configuración de Bot Agresivo en Fedora ---"

# 1. Instalar dependencias de Python
echo "Instalando dependencias de Python..."

# Detectar python3
PYTHON_BIN=$(which python3 || which python)
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: No se encontró Python instalado."
    exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    $PYTHON_BIN -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. Configurar Nginx para el Dashboard
echo "Generando configuración de Nginx..."
sudo tee /etc/nginx/conf.d/bot_agresivo.conf <<EOF
server {
    listen 80;
    server_name 81.39.37.98; # O la IP pública si es fija

    # Frontend (React Build)
    location / {
        root /home/daniel/proyectos/Bot_agresivo/web/dist;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # WebSockets
    location /ws {
        proxy_pass http://localhost:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
}
EOF

# 3. Permisos y SELinux (Nginx necesita leer el home)
echo "Ajustando permisos para Nginx..."
chmod 755 /home/daniel
chmod 755 /home/daniel/proyectos
chmod 755 /home/daniel/proyectos/Bot_agresivo
chmod -R 755 /home/daniel/proyectos/Bot_agresivo/web/dist

# Si SELinux está activo, permitir acceso a Nginx
if command -v chcon >/dev/null 2>&1; then
    echo "Aplicando contexto de SELinux..."
    sudo chcon -Rt httpd_sys_content_t /home/daniel/proyectos/Bot_agresivo/web/dist
fi

# 4. Reiniciar Nginx
echo "Reiniciando Nginx..."
sudo systemctl restart nginx

# 4. Iniciar con PM2
echo "Iniciando Backend con PM2..."
pm2 delete bot-agresivo-backend 2>/dev/null
pm2 start ecosystem.config.cjs

echo "--- Despliegue Completado! ---"
echo "Accede a: http://81.39.37.98"
