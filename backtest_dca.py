import pandas as pd
import ta
import sys
import numpy as np
from kraken_bot.strategies import StrategyRollingDCA
from kraken_bot.paper_wallet import PaperWallet

class MockWallet(PaperWallet):
    def __init__(self, initial_balance=1000.0):
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
        
    def open_position(self, symbol, side, price, quantity=0.0):
        # Override to inject strategy ID
        res = super().open_position(symbol, side, price, quantity)
        if res:
             # Find the newly created pos and tag it
             self.positions[res]['strategy'] = "RollingDCA"
             self.positions[res]['dca_step'] = 0
             self.positions[res]['size'] = quantity 
        return res

    def add_to_position(self, trade_id, price, quantity=0.0):
        res = super().add_to_position(trade_id, price, quantity)
        if res:
             pos = self.positions[trade_id]
             self.log_trade(pos, price, 0.0, f"DCA_Step_{pos.get('dca_step')}")
        return res

def run_backtest():
    print("Loading Data...")
    try:
        df = pd.read_csv('/home/daniel/Bot_agresivo/TRH_Research_2026_01_25.csv', on_bad_lines='skip')
        df = df[df['Timestamp'] != '0']
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df = df.dropna(subset=['Timestamp'])
        df = df.sort_values('Timestamp')
        df = df.drop_duplicates(subset=['Timestamp', 'Symbol'], keep='last')
    except Exception as e:
        print(f"Data Load Error: {e}")
        return

    # Pre-calculate Indicators
    print("Calculating 5m Indicators...")
    data_by_sym = {}
    
    symbols = df['Symbol'].unique()
    for sym in symbols:
        sub = df[df['Symbol'] == sym].copy().sort_values('Timestamp')
        if len(sub) < 50: continue
        
        # Resample to 5m
        sub = sub.set_index('Timestamp')
        sub_5m = sub['Close'].resample('5min').ohlc() # Returns open, high, low, close
        sub_5m['volume'] = sub['Volume'].resample('5min').sum()
        sub_5m = sub_5m.dropna()
        
        # RSI 5m
        if len(sub_5m) > 14:
             sub_5m['rsi_5m'] = ta.momentum.RSIIndicator(sub_5m['close'], window=14).rsi()
             
             # Reindex back to 1m (ffill) to simulate live feed having access to last closed 5m logic?
             # Actually StrategyRollingDCA checks 5m RSI.
             # In live bot, 5m RSI updates every 5 min.
             # We can't use 1m resolution for 5m RSI without lag.
             # But let's assume valid access.
             
             # Join back to 1m
             sub = sub.join(sub_5m['rsi_5m'].rename('rsi_5m'), how='left')
             sub['rsi_5m'] = sub['rsi_5m'].ffill()
        
        # Open 1m for Green Check
        sub['Open'] = sub['Open'] # Already there
        
        data_by_sym[sym] = sub

    # Setup Strategy
    wallet = MockWallet(1000.0)
    strat = StrategyRollingDCA(wallet)
    
    # Simulation Loop
    print("Simulating Market...")
    timestamps = df['Timestamp'].unique()
    timestamps = np.sort(timestamps)
    
    for ts in timestamps:
        # Process Ticks for All Symbols
        for sym in symbols:
            if sym not in data_by_sym or ts not in data_by_sym[sym].index: continue
            
            row = data_by_sym[sym].loc[ts]
            price = row['Close']
            
            # Build Indicators Dict
            inds = {
                'rsi_5m': row['rsi_5m'] if 'rsi_5m' in row else 50.0,
                'Open': row['Open']
            }
            
            # Strategy Logic
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
    print("\n--- Backtest Results: RollingDCA (1000 EUR) ---")
    print(f"Final Balance: {wallet.balance_eur:.2f} EUR")
    print(f"Net Profit: {wallet.balance_eur - 1000.0:.2f} EUR")
    print(f"Trades Executed: {len(wallet.trades_history)}") 
    
    if wallet.positions:
        print("\nActive Positions (Trapped?):")
        for pid, p in wallet.positions.items():
            cur = data_by_sym[p['symbol']].iloc[-1]['Close']
            step = p.get('dca_step', 0)
            print(f"- {p['symbol']} AvgEntry: {p['avg_price']:.2f} Current: {cur:.2f} PnL: {wallet.calc_pnl_pct_net(pid, cur):.2f}% | Steps: {step}")

if __name__ == "__main__":
    run_backtest()
