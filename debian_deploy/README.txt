# Despliegue en Debian

Este directorio contiene todo lo necesario para ejecutar el bot y el dashboard web en un servidor Debian.

## Instrucciones

1.  **Copiar archivos**: Sube esta carpeta al servidor (usando SCP, FTP, etc.).
2.  **Permisos**: Dale permisos de ejecución a los scripts:
    ```bash
    chmod +x install.sh run.sh
    ```
3.  **Instalación**: Ejecuta el script de instalación:
    ```bash
    ./install.sh
    ```
4.  **Ejecución**: Inicia el bot:
    ```bash
    ./run.sh
    ```

## Acceso

-   El dashboard estará disponible en `http://<IP_SERVIDOR>:8000`.
-   Para ver los logs en tiempo real: `tail -f bot.log`.

## Notas

-   Asegúrate de que el puerto 8000 esté abierto en el firewall si accedes desde fuera.
-   La configuración de API Keys está en `kraken_bot/config.py`.
