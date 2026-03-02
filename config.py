# config.py

# BINANCE API KEYS
API_KEY = 'YOUR_BINANCE_API_KEY'
SECRET_KEY = 'YOUR_BINANCE_SECRET_KEY'

# TRADING CONFIGURATION
STABLECOIN = 'USDT'  # 'USDT' or 'USDC'
PAXG_SYMBOL = f'PAXG/{STABLECOIN}'
BTC_SYMBOL = f'BTC/{STABLECOIN}'
ETH_SYMBOL = f'ETH/{STABLECOIN}'
SOL_SYMBOL = f'SOL/{STABLECOIN}'

# THRESHOLDS
FEAR_AND_GREED_THRESHOLD = 30  # Below this is Fear (Attack Mode)
DXY_THRESHOLD = 103            # Above this is high dollar strength (Shield Mode)
PMI_THRESHOLD = 50             # Below this is contraction (Shield Mode)

# EXECUTION
DRY_RUN = True  # Set to False to enable real trading
CHECK_TIME = "09:00" # Daily check time (24h format)

# CAPITAL MANAGEMENT
INITIAL_BALANCE = 500.0  # Balance per Strategy for Robustness Study
CAPITAL_LIMIT_PCT = 0.4 # Default Conservative Limit (40%)
CAPITAL_LIMIT_AGGRESSIVE = None # No Limit
VREL_THRESHOLD = 3.0
ERR_THRESHOLD = 2.5
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65

# FEES
FEE_SPOT_TAKER = 0.0026
FEE_SPOT_MAKER = 0.0016
FEE_FUTURES_TAKER = 0.0005
FEE_FUTURES_MAKER = 0.0002

# SYSTEM
TIMEFRAME = 1 # 1 minute
SYMBOLS = ['SOL/EUR', 'XBT/EUR', 'ETH/EUR', 'XRP/EUR', 'ADA/EUR', 'DOT/EUR', 'AVAX/EUR'] # Priority Assets
KRAKEN_REST_URL = "https://api.kraken.com/0/public"
MAX_ENTRY_PCT = 0.10 # 10% of equity per trade
MAX_ENTRY_AMT = 1000.0 # Unlimited relative to 500 balance, rely on PCT
TELEGRAM_TOKEN = "YOUR_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_ID"
