# kraken_bot/config.py

# --- API CONFIGURATION ---
# Kraken Websocket API
KRAKEN_WS_URL = 'wss://ws.kraken.com'
KRAKEN_REST_URL = 'https://api.kraken.com/0/public'

# --- TRADING CONFIGURATION ---
# Top 10 Pairs (Kraken format usually XBT/EUR, ETH/EUR... check availability)
# Using standard ISO codes where possible.
SYMBOLS = [
    'XBT/EUR', 'ETH/EUR', 'SOL/EUR', 'AVAX/EUR', 'ADA/EUR', 
    'DOT/EUR', 'XRP/EUR', 'LINK/EUR', 'MATIC/EUR', 'BNB/EUR', 'DOGE/EUR'
]
TIMEFRAME = 1          # 1 Minute candles

# --- PAPER TRADING & MEXC SIMULATION ---
INITIAL_BALANCE = 500.0  # EUR
# Spot (Longs): 0.05% Taker. DCA uses Maker (0.0%).
FEE_SPOT_TAKER = 0.0005
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
import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# --- API KEYS (KRAKEN / BINANCE) ---
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY")
KRAKEN_PRIVATE_KEY = os.getenv("KRAKEN_PRIVATE_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET") # Note: Bot_trading uses different names? checking later. Bot_trading/config didn't verify Binance.
# five_cubes_bot.py uses config.API_KEY, config.SECRET_KEY. I should standardize or set them here.
# Assuming I'll set standard names here.

# --- METRICS ---
# Official Project Start: 19/01/2026 10:04:10
PROJECT_START_TIMESTAMP = 1768813450

# --- AUTHENTICATION ---
# Stable secret for JWT cookies
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "bot_agresivo_ultra_secret_2026")
ADMIN_PASSWORD = "D4n13lo7o81976"
