# Bot de Trading MEXC (Servidor)

Este es un servidor completo de trading algorítmico diseñado para MEXC Spot.
Incluye Dashboard Web, Gestión de Base de Datos y Motor de Ejecución Asíncrono.

## Características

*   **Stack:** Python 3.10+, FastAPI, SQLite, TailwindCSS.
*   **Estrategias:** RollingDCA, Aggressive, HybridElite, NetScalp.
*   **Infraestructura:** WebSockets Reales, Cola de Órdenes, Sistema de Logs.

## Instalación

1.  Entra en el directorio:
    ```bash
    cd servidor
    ```

2.  Crea un entorno virtual e instala dependencias:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  Configura tus claves API:
    Edita el archivo `.env` (créalo si no existe) o exporta las variables:
    ```bash
    export MEXC_API_KEY="tu_clave"
    export MEXC_SECRET_KEY="tu_secreto"
    ```

## Ejecución

Para iniciar el servidor Web y el Bot:

```bash
./run.sh
```

El Dashboard estará disponible en: **http://ip_del_servidor:8000** (o localhost).

## Estrategias

Por defecto, el bot arranca con **RollingDCA** (compra en caídas de 5m).
Para cambiar la estrategia, edita `app/services/strategies.py` al final del archivo.

## Estructura

*   `app/main.py`: Punto de entrada Web.
*   `app/services/bot_engine.py`: Motor de trading (Loop principal).
*   `app/services/strategies.py`: Lógica de análisis técnico.
*   `mexc_bot.db`: Base de datos SQLite (se crea automáticamente).
