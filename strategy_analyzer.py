import pandas as pd
import glob
import os
import logging
from datetime import datetime
from kraken_bot import strategies
from kraken_bot import config
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(message)s')

class MockWallet:
    def __init__(self, strategy_id, initial_balance=10000.0, investment_amount=10.0):
        self.strategy_id = strategy_id
        self.balance_eur = initial_balance
        self.initial_capital = initial_balance
        self.investment_amount = investment_amount
        self.positions = {}
        self.trades_history = []
        self.next_trade_id = 1
        self.current_time = None # Set during simulation

    def update_max_stats(self, t_id, price):
        if t_id not in self.positions: return
        pos = self.positions[t_id]
        if 'highest_price' not in pos: pos['highest_price'] = price
        if 'lowest_price' not in pos: pos['lowest_price'] = price
        
        pos['highest_price'] = max(pos['highest_price'], price)
        pos['lowest_price'] = min(pos['lowest_price'], price)

    def send_telegram_notification(self, *args, **kwargs):
        pass # No notifications during simulation

    def save_state(self):
        pass # No saving state during simulation

    def can_open_new(self, symbol, side, current_prices=None):
        # Simplify: Check if we have enough cash for investment + fees
        fee_rate = config.FEE_SPOT_TAKER if side == 'LONG' else config.FEE_FUTURES_TAKER
        needed = self.investment_amount * (1 + fee_rate)
        if self.balance_eur < needed:
            return False, "Insufficient cash"
        
        return True, "OK"

    def open_position(self, symbol, side, price, quantity=0.0):
        can, reason = self.can_open_new(symbol, side)
        if not can: return None

        size = self.investment_amount / price
        margin_cost = self.investment_amount
        
        fee_rate = config.FEE_SPOT_TAKER if side == 'LONG' else config.FEE_FUTURES_TAKER
        fee_eur = margin_cost * fee_rate
        
        self.balance_eur -= (margin_cost + fee_eur)
        
        t_id = self.next_trade_id
        self.next_trade_id += 1
        
        self.positions[t_id] = {
            'symbol': symbol,
            'type': side,
            'size': size,
            'margin': margin_cost,
            'avg_price': price,
            'entry_price': price,
            'entry_time': self.current_time.timestamp() if hasattr(self.current_time, 'timestamp') else 0,
            'entry_time_dt': self.current_time, # Keep DT for duration
            'itemized_fees': fee_eur,
            'dca_count': 0
        }
        return t_id

    def close_position(self, trade_id, price, reason="Exit"):
        if trade_id not in self.positions: return
        pos = self.positions[trade_id]
        
        # Exit fee
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        exit_val = pos['size'] * price
        fee_exit = exit_val * fee_rate
        
        # PnL Gross
        if pos['type'] == 'LONG':
            gross_pnl = (price - pos['avg_price']) * pos['size']
        else: # SHORT
            gross_pnl = (pos['avg_price'] - price) * pos['size']
            
        net_pnl = gross_pnl - pos['itemized_fees'] - fee_exit
        
        duration = (self.current_time - pos['entry_time_dt']).total_seconds() / 60.0 # in minutes
        
        self.balance_eur += (pos['margin'] + gross_pnl - fee_exit)
        
        self.trades_history.append({
            'symbol': pos['symbol'],
            'type': pos['type'],
            'final_pnl': net_pnl,
            'duration_mins': duration,
            'close_time': self.current_time,
            'reason': reason
        })
        del self.positions[trade_id]

    # Simplified helpers for strategies
    def calc_pnl_gross(self, t_id, price):
        pos = self.positions[t_id]
        if pos['type'] == 'LONG': return (price - pos['avg_price']) * pos['size']
        return (pos['avg_price'] - price) * pos['size']

    def calc_pnl_pct_net(self, t_id, price):
        if t_id not in self.positions: return 0
        pos = self.positions[t_id]
        gross = self.calc_pnl_gross(t_id, price)
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        fee_exit = (pos['size'] * price) * fee_rate
        net_pnl = gross - pos['itemized_fees'] - fee_exit
        if pos['margin'] == 0: return 0
        return (net_pnl / pos['margin']) * 100

    def add_to_position(self, trade_id, price, quantity=0.0):
        # Simplified DCA: same investment amount again
        if trade_id not in self.positions: return False
        pos = self.positions[trade_id]
        
        needed = self.investment_amount * (1 + config.FEE_SPOT_TAKER)
        if self.balance_eur < needed: return False
        
        size = self.investment_amount / price
        fee = self.investment_amount * config.FEE_SPOT_TAKER
        
        self.balance_eur -= (self.investment_amount + fee)
        
        old_val = pos['size'] * pos['avg_price']
        new_val = size * price
        pos['size'] += size
        pos['avg_price'] = (old_val + new_val) / pos['size']
        pos['margin'] += self.investment_amount
        pos['itemized_fees'] += fee
        pos['dca_count'] += 1
        return True

def run_simulation(preprocessed_data, strategy_class, investment_amount, last_prices, show_progress=False):
    wallet = MockWallet(strategy_class.__name__, investment_amount=investment_amount)
    strategy = strategy_class(wallet)
    
    # Preprocessed_data is a list of (timestamp, indicators_map)
    iterator = preprocessed_data
    if show_progress:
        iterator = tqdm(preprocessed_data, desc=f"      {strategy_class.__name__} {investment_amount}€", leave=False)
        
    for timestamp, indicators_map in iterator:
        wallet.current_time = timestamp
        
        # Optimization: Call on_tick once per symbol. 
        # BaseStrategy.on_tick already calls both check_exit_conditions (all matching positions) 
        # AND check_entry_logic.
        for symbol, indicators in indicators_map.items():
            price = indicators['Close']
            strategy.on_tick(symbol, price, indicators)
            
        if show_progress:
            iterator.set_postfix(balance=f"{wallet.balance_eur:.2f}€", pos=len(wallet.positions))

    # Close remaining positions at last price
    active_ids = list(wallet.positions.keys())
    for t_id in active_ids:
        pos = wallet.positions[t_id]
        if pos['symbol'] in last_prices:
            price = last_prices[pos['symbol']]
            wallet.close_position(t_id, price, reason="SimEnd")
        
    return wallet.trades_history

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run a quick test with subset of data")
    args = parser.parse_args()

    print("🚀 Starting Strategy Performance Analysis...")
    
    # 1. Load Data
    files = sorted(glob.glob("TRH_Research_*.csv"))
    if not files:
        print("❌ No TRH research files found.")
        return
        
    if args.test:
        print("🧪 TEST MODE: Loading only the first file.")
        files = files[:1]

    print(f"📂 Loading {len(files)} files...")
    all_data = []
    for f in tqdm(files, desc="Reading CSVs"):
        try:
            df = pd.read_csv(f, on_bad_lines='skip', low_memory=False)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
            df = df.dropna(subset=['Timestamp', 'Symbol', 'Close'])
            all_data.append(df)
        except Exception as e:
            print(f"\n⚠️ Warning: Could not load {f}: {e}")
    
    if not all_data:
        print("❌ No valid data could be loaded.")
        return

    print("📊 Consolidating data...")
    full_df = pd.concat(all_data).sort_values('Timestamp')
    full_df = full_df.drop_duplicates(subset=['Timestamp', 'Symbol'])
    
    if args.test:
        print("🧪 TEST MODE: Using only first 1000 timestamps.")
        unique_ts = full_df['Timestamp'].unique()[:1000]
        full_df = full_df[full_df['Timestamp'].isin(unique_ts)]

    print(f"✅ Total data points after cleaning: {len(full_df)}")

    print("⚙️  Pre-processing data groups (this speeds up simulations)...")
    preprocessed_data = []
    # Optimization: Use a more direct way to build the indicators map
    grouped = full_df.groupby('Timestamp')
    for timestamp, group in tqdm(grouped, desc="Grouping timestamps"):
        # group.to_dict('records') is often faster than set_index().to_dict('index')
        # But we need symbol as key. 
        indicators = {row['Symbol']: row for row in group.to_dict('records')}
        preprocessed_data.append((timestamp, indicators))

    # Pre-calculate last prices for SimEnd closure
    last_prices = full_df.groupby('Symbol')['Close'].last().to_dict()

    # 2. Strategies to test
    test_strategies = [
        strategies.StrategyAggressive,
        # strategies.StrategyAggressiveCent,
        # strategies.StrategyHybridElite,
        # strategies.StrategyRollingDCA,
        # strategies.StrategyNetScalpDCA
    ]
    if not args.test:
        test_strategies = [
            strategies.StrategyAggressive,
            strategies.StrategyAggressiveCent,
            strategies.StrategyHybridElite,
            strategies.StrategyRollingDCA,
            strategies.StrategyNetScalpDCA
        ]
    
    # 3. Investment Levels
    investments = [1, 2, 5, 10, 20, 50]
    
    results = []
    
    total_sims = len(test_strategies) * len(investments)
    with tqdm(total=total_sims, desc="Overall Progress") as pbar:
        for strat_class in test_strategies:
            strat_name = strat_class.__name__
            
            for amt in investments:
                pbar.set_postfix(strategy=strat_name, investment=f"{amt}€")
                trades = run_simulation(preprocessed_data, strat_class, amt, last_prices, show_progress=True)
                
                if not trades:
                    results.append({
                        'Strategy': strat_name,
                        'Investment': amt,
                        'PnL': 0,
                        'WinRate': 0,
                        'AvgDuration': 0,
                        'Trades': 0
                    })
                else:
                    total_pnl = sum(t['final_pnl'] for t in trades)
                    wins = len([t for t in trades if t['final_pnl'] >= 0])
                    win_rate = (wins / len(trades)) * 100
                    avg_duration = sum(t['duration_mins'] for t in trades) / len(trades)
                    
                    results.append({
                        'Strategy': strat_name,
                        'Investment': amt,
                        'PnL': total_pnl,
                        'WinRate': win_rate,
                        'AvgDuration': avg_duration,
                        'Trades': len(trades)
                    })
                pbar.update(1)
    
    # 4. Generate Report
    print("\n✅ Analysis Complete. Generating Report...")
    report_df = pd.DataFrame(results)
    
    report_md = "# 📈 Strategy Performance Report\n\n"
    report_md += f"*Analysis period: {full_df['Timestamp'].min()} to {full_df['Timestamp'].max()}*\n\n"
    
    for strat in report_df['Strategy'].unique():
        report_md += f"## Strategy: {strat}\n"
        subset = report_df[report_df['Strategy'] == strat]
        report_md += subset[['Investment', 'PnL', 'WinRate', 'AvgDuration', 'Trades']].to_markdown(index=False)
        report_md += "\n\n"
        
    with open("strategy_performance_report.md", "w") as f:
        f.write(report_md)
        
    print("✨ Report generated: strategy_performance_report.md")

if __name__ == "__main__":
    main()
