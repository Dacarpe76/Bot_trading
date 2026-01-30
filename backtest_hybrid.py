import pandas as pd
import ta
import sys
from kraken_bot.strategies import StrategyHybridElite
from kraken_bot.paper_wallet import PaperWallet

class MockWallet(PaperWallet):
    def __init__(self, initial_balance=500.0):
        super().__init__("Backtest", initial_balance, None)
        self.trades_history = []

    def log_trade(self, position, price, pnl, reason):
        self.trades_history.append({
            'symbol': position['symbol'],
            'side': position['type'],
            'entry': position['entry_price'],
            'exit': price,
            'pnl': pnl,
            'reason': reason
        })

def run_backtest():
    print("Loading Data...")
    try:
        df = pd.read_csv('/home/daniel/Bot_agresivo/TRH_Research_2026_01_25.csv', on_bad_lines='skip')
        df = df[df['Timestamp'] != '0'] # Filter Header repeats or garbage
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df = df.dropna(subset=['Timestamp'])
        df = df.sort_values('Timestamp')
        df = df.drop_duplicates(subset=['Timestamp', 'Symbol'], keep='last')
    except Exception as e:
        print(f"Data Load Error: {e}")
        return

    # Pre-calculate Indicators for all symbols
    print("Calculating Indicators...")
    data_by_sym = {}
    
    symbols = df['Symbol'].unique()
    for sym in symbols:
        sub = df[df['Symbol'] == sym].copy().sort_values('Timestamp')
        if len(sub) < 20: continue
        
        # RSI 14
        sub['rsi'] = ta.momentum.RSIIndicator(sub['Close'], window=14).rsi()
        
        # VRel (Volume / SMA20)
        vol_mean = sub['Volume'].rolling(20).mean()
        sub['vrel'] = sub['Volume'] / vol_mean.replace(0, 1)
        
        # ERR (Efficiency Ratio - Kaufman) - simplified proxy or use ta
        # Using simple |Change| / Sum(|Changes|) over 10 periods
        change = sub['Close'].diff().abs()
        path = change.rolling(10).sum()
        dist = (sub['Close'] - sub['Close'].shift(10)).abs()
        sub['err'] = dist / path.replace(0, 1) * 10
        
        # Wick Ratio
        body = (sub['Open'] - sub['Close']).abs()
        upper = sub['High'] - sub[['Open', 'Close']].max(axis=1)
        lower = sub[['Open', 'Close']].min(axis=1) - sub['Low']
        wick = (upper + lower)
        sub['wick_pct'] = wick / body.replace(0, 0.0001)
        
        data_by_sym[sym] = sub.set_index('Timestamp')

    # Setup Strategy
    wallet = MockWallet(500.0)
    strat = StrategyHybridElite(wallet)
    
    # Simulation Loop
    print("Simulating Market...")
    import numpy as np
    timestamps = df['Timestamp'].unique()
    timestamps = np.sort(timestamps)
    
    btc_open_candle = {} # Store Open price for current minute to calc Trend
    
    for ts in timestamps:
        # 1. Update Market Context (BTC Trend)
        trend = "NEUTRAL"
        
        # Check XBT/EUR for this timestamp
        if 'XBT/EUR' in data_by_sym and ts in data_by_sym['XBT/EUR'].index:
            row = data_by_sym['XBT/EUR'].loc[ts]
            price = row['Close']
            
            # Simple Trend Logic matching Processor
            # We assume 'Open' in CSV is the minute open
            open_p = row['Open']
            if open_p > 0:
                change = (price - open_p) / open_p
                if change < -0.0025: trend = "DUMP"
        
        # 2. Process Ticks for All Symbols
        for sym in symbols:
            if sym not in data_by_sym or ts not in data_by_sym[sym].index: continue
            
            row = data_by_sym[sym].loc[ts]
            price = row['Close']
            
            # Build Indicators Dict
            inds = {
                'rsi': row['rsi'],
                'vrel': row['vrel'],
                'err': row['err'],
                'wick_pct': row['wick_pct'],
                'wick_pct': row['wick_pct'],
                'market_trend': trend,
                'Open': row['Open'], # Added for Green Candle Check
                'atr': row['ATR_14'] if 'ATR_14' in row else 0.0 # Use pre-calc/CSV ATR if avail
            }
            if pd.isna(inds['atr']): inds['atr'] = price * 0.01 # Fallback
            
            # Strategy Logic
            # Check Exit First
            open_pos = None
            pos_id = None
            for pid, p in wallet.positions.items():
                if p['symbol'] == sym:
                    open_pos = p
                    pos_id = pid
                    break
            
            if open_pos:
                strat.manage_position(pos_id, open_pos, price, inds)
            else:
                strat.check_entry_logic(sym, price, inds)

    # Report
    print("\n--- Backtest Results: HybridElite ---")
    print(f"Final Balance: {wallet.balance_eur:.2f} EUR")
    print(f"Net Profit: {wallet.balance_eur - 500.0:.2f} EUR")
    print(f"Trades Executed: {len(wallet.trades_history)}") # Note: MockWallet needs to capture history
    
    # Check Trapped
    if wallet.positions:
        print("\nTrapped Positions:")
        for pid, p in wallet.positions.items():
            cur = data_by_sym[p['symbol']].iloc[-1]['Close']
            print(f"- {p['symbol']} Entry: {p['entry_price']:.2f} Current: {cur:.2f} PnL: {wallet.calc_pnl_pct_net(pid, cur):.2f}%")

if __name__ == "__main__":
    run_backtest()
