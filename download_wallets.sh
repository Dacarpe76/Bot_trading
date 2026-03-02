#!/bin/bash
echo "Descargando datos de las wallets desde el servidor Fedora (192.168.1.99)..."
sshpass -p "Dn07ap28" rsync -av daniel@192.168.1.99:/home/daniel/proyectos/Bot_agresivo/wallet_state_*.json /home/daniel/projects/Bot_agresivo/
echo "¡Datos descargados correctamente! Tu dashboard local ahora mostrará las estadísticas actualizadas."
