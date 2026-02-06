import ccxt
import time
from datetime import datetime

print("Initializing Kraken...")
kraken = ccxt.kraken() 
# Not using keys for public data to see if that matters, public data shouldn't need them.
# But original used keys. I'll stick to public first.

symbol = 'BTC/EUR'
timeframe = '4h'
since_dt = datetime(2020, 1, 1)
since = int(since_dt.timestamp() * 1000)

print(f"Fetching {symbol} since {since} ({since_dt})")
try:
    ohlcv = kraken.fetch_ohlcv(symbol, timeframe, since=since, limit=5)

    if not ohlcv:
        print("Empty result")
    else:
        first_ts = ohlcv[0][0]
        last_ts = ohlcv[-1][0]
        
        print(f"Returned {len(ohlcv)} candles.")
        print(f"First candle: {first_ts} ({datetime.fromtimestamp(first_ts/1000)})")
        print(f"Last candle: {last_ts} ({datetime.fromtimestamp(last_ts/1000)})")
        
        if abs(first_ts - since) > 24*3600*1000:
             print("MISMATCH DETECTED!")
        else:
             print("MATCH OK.")
except Exception as e:
    print(f"Error: {e}")
