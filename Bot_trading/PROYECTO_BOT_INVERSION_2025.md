# Especificaciones Técnicas: Sistema de Inversión Kraken 2025

## 1. Visión General

El sistema operará exclusivamente en Kraken, gestionando una cartera diversificada entre Bitcoin (BTC) y Oro (PAXG), utilizando Euros o USDC como base de liquidez.

## 2. Estrategia Avanzada (Kraken)

- **Capital Inicial**: 500€ + 50€ mensuales (aportación día 10).
- **Filtro de Tendencia**: EMA de 200 periodos. Si el precio está por encima, sesgo alcista.
- **Lógica de Entrada (BTC)**: MACD adaptativo con configuración rápida (8, 17, 9).
- **Lógica de Oro (PAXG)**: Identificación de barridos de liquidez (Liquidity Sweeps) en niveles clave (SMC).
- **Gestión de Riesgo (ATR)**: El tamaño de cada posición se calculará basándose en el ATR (Average True Range) de 14 periodos. El objetivo es que la volatilidad del BTC no domine la cartera frente al Oro.
- **Rebalanceo**: Umbral del 15%. Si un activo se desvía un 15% de su peso objetivo, el bot reequilibra la cartera.

## 3. Cubo de Gastos y Seguridad

- **Cubo de Gastos**: El bot debe calcular el beneficio neto de cada operación cerrada (restando comisiones de Kraken) y asignar virtualmente el 10% a una cuenta de "Gastos".
- **Regla de Pérdida Cero**: El bot tiene prohibido ejecutar ventas por debajo del precio medio de compra (Break-even mínimo), a menos que sea un rebalanceo forzado.

## 4. Requisitos Técnicos

- **Lenguaje**: Python (ccxt, pandas, pandas_ta).
- **Base de Datos**: SQLite local (`trading_data.db`) para persistencia de precios y beneficios.
- **Alertas**: Notificación diaria a las 09:00 AM vía Telegram con el balance total en EUROS.
- **Resiliencia**: Si falla la conexión, reintento automático cada 300 segundos.
  "Antes de escribir las funciones de trading, asegúrate de implementar una función de 'Modo Simulación' (Paper Trading) para que podamos verificar que los cálculos del ATR y las señales de Telegram funcionan correctamente sin arriesgar capital real."
