# Configuración del Bot de Trading (Paper Trading)

# Capital Inicial Simulada
INITIAL_CAPITAL = 500.0  # Euros
INITIAL_CASH = 500.0
SIMULAR_APORTE_MENSUAL = 0.0 # Euros
DIA_APORTE_MENSUAL = 10 # Día del mes para el aporte

# Símbolos (Yahoo Finance)
SYMBOL_BTC = "BTC-EUR"
SYMBOL_GOLD = "GC=F" # Futuros del Oro

# Indicadores
SMA_FAST = 50
SMA_SLOW = 200
RSI_PERIOD = 14

# Umbrales Estrategia
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# PMI (Simulado si no hay API real)
# Umbral de contracción manufacturera
PMI_THRESHOLD = 50.0 
PMI_DEFAULT = 48.0 # Valor por defecto para pruebas

# Pesos de Cartera Objetivo (Default)
WEIGHT_BTC_DEFAULT = 0.5
WEIGHT_GOLD_DEFAULT = 0.5
