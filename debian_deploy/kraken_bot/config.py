# kraken_bot/config.py

# --- API CONFIGURATION ---
# Kraken Websocket API
KRAKEN_WS_URL = 'wss://ws.kraken.com'
KRAKEN_REST_URL = 'https://api.kraken.com/0/public'

# --- TRADING CONFIGURATION ---
# Top 10 Pairs (Kraken format usually XBT/EUR, ETH/EUR... check availability)
# Using standard ISO codes where possible.
SYMBOLS = [
    'XBT/EUR', 'ETH/EUR', 'SOL/EUR', 'BNB/EUR', 'XRP/EUR', 
    'ADA/EUR', 'AVAX/EUR', 'DOGE/EUR', 'DOT/EUR', 'LINK/EUR'
]
TIMEFRAME = 1          # 1 Minute candles

# --- PAPER TRADING & MEXC SIMULATION ---
INITIAL_BALANCE = 500.0  # EUR
# MEXC Costs Simulation
# Spot (Longs): 0.1% Taker. DCA uses Maker (0.0%).
FEE_SPOT_TAKER = 0.001
FEE_SPOT_MAKER = 0.000 
# Futures (Shorts): 0.02% Taker. DCA uses Maker (0.0%).
FEE_FUTURES_TAKER = 0.0002
FEE_FUTURES_MAKER = 0.000

# --- RISK MANAGEMENT ---
# Snipe Mode: Max 10% of Cap or 60 EUR per entry
MAX_ENTRY_PCT = 0.10
MAX_ENTRY_AMT = 60.0
MIN_ENTRY_AMT = 10.0 # Minimum Trade Size
CAPITAL_LIMIT_PCT = 0.40 # New entries blocked if >40% used (60% Reserve for DCA)
CAPITAL_LIMIT_AGGRESSIVE = None # No Limit

# --- STRATEGY THRESHOLDS (Sniper Mode) ---
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
ERR_THRESHOLD = 2.5
VREL_THRESHOLD = 3.0

# --- LOGGING ---
LOG_FILE = 'bot_activity.log'
RESEARCH_FILE = 'market_research.csv'

# --- TELEGRAM ALERTS ---
TELEGRAM_TOKEN = '8354477556:AAGvUdno_5vDE06Wt4ECXXz5i9SEd7JqlPk'
TELEGRAM_CHAT_ID = '1203738200'

# --- METRICS ---
# Official Project Start: 19/01/2026 10:04:10
PROJECT_START_TIMESTAMP = 1768813450
