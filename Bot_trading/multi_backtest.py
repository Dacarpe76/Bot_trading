
import logging
import sys
import os
import time
import pandas as pd
from datetime import datetime, timedelta

# Add Bot_trader to path FIRST to ensure finding its modules
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

from backtest import BufferedBacktester
from strategies import StandardStrategy, InstantStrategy, InstantV2Strategy, InstantV3Strategy, InstantV4Strategy

# Import Bot_trader modules
try:
    import bot_config
    from data_loader import MarketData
    from strategy import Strategy as MacroStrategy
    from policy import Policy
    from portfolio import PaperPortfolio
except ImportError as e:
    print(f"Error importing Bot_trader modules: {e}")
    sys.exit(1)

# Suppress logs
logging.getLogger().setLevel(logging.ERROR)

class MacroPolicyBacktester:
    def __init__(self, initial_capital=1000.0):
        self.initial_capital = initial_capital
        # Override config
        bot_config.INITIAL_CAPITAL = initial_capital
        bot_config.INITIAL_CASH = initial_capital
        
        self.market = MarketData()
        self.strategy = MacroStrategy()
        self.policy = Policy()
        self.portfolio = PaperPortfolio() # Reads config for init capital
        self.strategy_name = "Macro Policy V2"
        self.daily_equity = []
        
    def run_simulation(self, start_date_str, quiet=False):
        # 1. Fetch Data
        if not quiet: print("   📥 Fetching Market & Macro Data (Bot_trader)...")
        
        start_dt = datetime.strptime(start_date_str, "%d/%m/%Y")
        start_fmt = start_dt.strftime("%Y-%m-%d")
        
        # Fetch slightly earlier for indicators
        hist_start = (start_dt - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        
        hist_data = self.market.get_market_data(start_date=hist_start)
        if hist_data.empty:
            return {'final_equity': 0, 'pnl': 0, 'pnl_percent': 0, 'trades': 0}
            
        hist_data = self.strategy.calculate_indicators(hist_data)
        
        # Macro
        pmi_series = self.market.get_pmi_data_fred(start_date=hist_data.index[0], end_date=hist_data.index[-1])
        macro_series = self.market.get_macro_data(start_date=hist_data.index[0], end_date=hist_data.index[-1])
        
        # Filter for Simulation
        backtest_data = hist_data.loc[start_fmt:].copy()
        
        # Join Macro
        backtest_data['PMI'] = backtest_data.index.map(lambda d: pmi_series.loc[d]['PMI'] if d in pmi_series.index else bot_config.PMI_DEFAULT)
        backtest_data['PMI'] = backtest_data['PMI'].ffill().fillna(bot_config.PMI_DEFAULT)
        
        backtest_data = backtest_data.join(macro_series, how='left')
        backtest_data['VIX'] = backtest_data['VIX'].ffill().fillna(20.0)
        backtest_data['TIPS'] = backtest_data['TIPS'].ffill().fillna(1.0)
        backtest_data['FED_RATE'] = backtest_data['FED_RATE'].ffill().fillna(0.0)
        
        # Calculate Rate Change (3-month delta approx 63 trading days, or 90 days if daily)
        # Using 90 days since DFF is daily calendar
        backtest_data['FED_RATE_DELTA'] = backtest_data['FED_RATE'].diff(90).fillna(0)
        
        # Save history for live updates logic
        self.full_history = backtest_data # Includes indicators
        
        for date, row in backtest_data.iterrows():
            self.process_daily_step(date, row)
            
        return self.get_current_stats()

    def process_daily_step(self, date, row):
        current_prices = {'BTC': row['BTC_Close'], 'GOLD': row['GOLD_Close']}
        pmi_val = row['PMI']
        tips_val = row['TIPS'] if 'TIPS' in row else 1.0
        vix_val = row['VIX'] if 'VIX' in row else 20.0
        fed_rate_delta = row['FED_RATE_DELTA'] if 'FED_RATE_DELTA' in row else 0.0
            
        # Logic
        raw_signal = self.strategy.get_signal(row, pmi_val)
        regimen = self.policy.detectar_regimen(pmi_val, tips_val, vix_val, fed_rate_delta)
            
        policy_decision = self.policy.aplicar_politica(
            raw_weights=raw_signal,
            current_prices=current_prices,
            holdings=self.portfolio.holdings,
            avg_prices=self.portfolio.avg_price,
            regimen=regimen
        )
        
        # --- MANUAL OVERRIDE (USER REQUEST) ---
        # 1. Peak 1: 1250 (Approx 2021-03-11) -> 1000 (Approx 2021-06-07)
        # 2. Peak 2: 1500 (Approx 2021-11-08) -> 1000 (Approx 2022-06-16)
        
        str_date = date.strftime("%Y-%m-%d")
        
        # Range 1
        if "2021-03-11" <= str_date <= "2021-06-07":
             policy_decision['btc_weight'] = 0.0
             policy_decision['gold_weight'] = 0.0
             policy_decision['policy_log'] = ["MANUAL OVERRIDE: CASH (Peak 1250)"]
             
        # Range 2
        elif "2021-11-08" <= str_date <= "2022-06-16":
             policy_decision['btc_weight'] = 0.0
             policy_decision['gold_weight'] = 0.0
             policy_decision['policy_log'] = ["MANUAL OVERRIDE: CASH (Peak 1500)"]
             
        # --------------------------------------
            
        self.portfolio.rebalance(policy_decision, current_prices, date)
        self.portfolio.record_daily_status(date, current_prices, pmi_val)
        
        # Record equity
        total_val = self.portfolio.get_total_value(current_prices)
        self.daily_equity.append({
            'date': date.strftime("%Y-%m-%d"),
            'equity': total_val
        })

    def get_current_stats(self):
        last_prices = {'BTC': 0, 'GOLD': 0}
        # Attempt to get latest price from history or fetch
        if not self.full_history.empty:
            last_prices = {
                'BTC': self.full_history.iloc[-1]['BTC_Close'],
                'GOLD': self.full_history.iloc[-1]['GOLD_Close']
            }
        
        final_equity = self.portfolio.get_total_value(last_prices)
        trades_count = len(self.portfolio.trade_log)
        return {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'pnl': final_equity - self.initial_capital,
            'pnl_percent': (final_equity - self.initial_capital) / self.initial_capital * 100,
            'trades': trades_count
        }

    def update_live(self):
        print(f"[{datetime.now().strftime('%H:%M')}] 📡 {self.strategy_name}: Checking for new data...")
        
        # Fetch last 5 days
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        new_data = self.market.get_market_data(start_date=start_date)
        
        if new_data.empty:
            print("   💤 No new data.")
            return

        # Calculate indicators on this chunk
        # Note: Indicators might be inaccurate on small chunks if they need long history (EMA200).
        # Ideally we fetch longer history (200d) but calculation assumes we append to main history.
        # For this prototype we accept simple recalc or we'd need to re-fetch 365d every time.
        # Let's fetch 250d to be safe for EMA200
        start_active = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")
        active_chunk = self.market.get_market_data(start_date=start_active)
        active_chunk = self.strategy.calculate_indicators(active_chunk)

        # Identify NEW rows
        last_ts = self.full_history.index[-1]
        new_rows = active_chunk[active_chunk.index > last_ts].copy()
        
        if new_rows.empty:
            print("   💤 No new data.")
            return
            
        print(f"   ✨ New records found: {len(new_rows)}")
        
        # For each new row, process
        # Missing Macro fill logic here for simplicity (defaults)
        
        for date, row in new_rows.iterrows():
            # Add defaults for macro if missing in fresh fetch
            if 'PMI' not in row: row['PMI'] = bot_config.PMI_DEFAULT
            if 'VIX' not in row: row['VIX'] = 20.0
            if 'TIPS' not in row: row['TIPS'] = 1.0
            
            self.process_daily_step(date, row)
        
        # Append to full history
        self.full_history = pd.concat([self.full_history, new_rows])
        
        stats = self.get_current_stats()
        print(f"   📊 Updated Equity: {stats['final_equity']:.2f} €")


def run_multi_backtest():
    start_date = "01/01/2020"
    initial_capital = 1000.0
    
    # 1. Define Strategies
    strategies = {
        'Standard (MACD+EMA)': StandardStrategy(),
        'Instant (Trend Follow)': InstantStrategy(),
        'Instant V2 (Trailing Stop 10%)': InstantV2Strategy(), 
        'Instant V3 (Smart Peak)': InstantV3Strategy(),
        'Instant V4 (Long/Short + TP)': InstantV4Strategy(),
        'Macro Policy V2': None, 
    }
    
    print(f"🚀 Starting Multi-Strategy Backtest (History -> Live)")
    print(f"📅 Start Date: {start_date}")
    print(f"💰 Initial Capital: {initial_capital} €")
    print("-" * 50)
    
    active_bots = []
    results = []
    
    for name, strategy_obj in strategies.items():
        print(f"\nProcessing {name}...")
        try:
            if name == 'Macro Policy V2':
                bt = MacroPolicyBacktester(initial_capital)
                res = bt.run_simulation(start_date, quiet=True)
            else: # Standard strategies
                bt = BufferedBacktester(strategy_obj, initial_capital)
                bt.strategy_name = name
                res = bt.run_simulation(start_date, quiet=True)
                res = bt.run_simulation(start_date, quiet=True)
            
            res['name'] = name
            results.append(res)
            active_bots.append(bt) # Keep instance for live mode
            
            print(f"   ✅ Up to date. Current Equity: {res['final_equity']:.2f} €")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()

    # ... (After results processing loop) ...
    
    # --- 2. Comparative Analysis & CSV Export ---
    print("\n📊 Analyzing Daily Evolution...")
    
    # Merge DataFrames
    # We expect each 'res' (actually the bot instance, we need the bot instance!) 
    # to have .daily_equity list.
    
    combined_df = None
    
    for i, bot in enumerate(active_bots):
        # Convert list of dicts to DF
        strategy_name = results[i]['name'] # results order matches active_bots order
        df = pd.DataFrame(bot.daily_equity)
        if df.empty: continue
        
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.rename(columns={'equity': strategy_name}, inplace=True)
        
        if combined_df is None:
            combined_df = df
        else:
            combined_df = combined_df.join(df, how='outer')
            
    if combined_df is not None:
        combined_df.ffill(inplace=True) # Fill gaps
        combined_df.fillna(initial_capital, inplace=True) # Init val
        
        # Save CSV
        csv_path = "daily_equity_comparison.csv"
        combined_df.to_csv(csv_path)
        print(f"   💾 Saved daily comparison to '{csv_path}'")
        
        # Analyze Leader
        # Find which column is max for each row
        combined_df['Leader'] = combined_df.idxmax(axis=1)
        
        # Macro Stats
        macro_col = "Macro Policy V2"
        if macro_col in combined_df.columns:
            macro_wins = combined_df[combined_df['Leader'] == macro_col]
            days_led = len(macro_wins)
            total_days = len(combined_df)
            pct_led = (days_led / total_days) * 100
            
            print(f"\n🔍 MACRO POLICY ANALYSIS:")
            print(f"   Led the market for {days_led} days ({pct_led:.1f}% of time)")
            if days_led > 0:
                print("   (Examples of dominance: " + str(macro_wins.index[:3].date) + "...)")
            else:
                print("   (Never held the top spot in Equity, likely due to defensive positioning in Bull Run)")
                
            # Compare vs Standard
            std_col = "Standard (MACD+EMA)"
            if std_col in combined_df.columns:
                wins_vs_std = len(combined_df[combined_df[macro_col] > combined_df[std_col]])
                print(f"   Beat '{std_col}' on {wins_vs_std} days ({(wins_vs_std/total_days)*100:.1f}%)")

    # Initial Summary Table
    print("\n" + "="*80)
    print(f"{'STRATEGY':<25} | {'EQUITY':<12} | {'PnL €':<10} | {'TRADES':<8}")
    print("-" * 80)
    sorted_res = sorted(results, key=lambda x: x['final_equity'], reverse=True)
    for r in sorted_res:
         print(f"{r['name']:<25} | {r['final_equity']:<12.2f} | {r['pnl']:<10.2f} | {r['trades']:<8}")
    print("="*80)
    
    print(f"\n📡 ENTERING LIVE MODE (Updates every 60 mins)")
    print(f"   Press Ctrl+C to stop.")
    
    try:
        while True:
            sleep_sec = 3600 # 60 mins
            print(f"\n⏳ Sleeping {sleep_sec}s...")
            time.sleep(sleep_sec)
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            print(f"\n🔄 [{now_str}] HOURLY STATUS REPORT")
            print("-" * 60)
            
            for bot in active_bots:
                try:
                    bot.update_live()
                    # Print Nice Summary
                    # Need to extract equity safely
                    last_eq = 0
                    if isinstance(bot, MacroPolicyBacktester):
                         stats = bot.get_current_stats()
                         last_eq = stats['final_equity']
                    else: # BufferedBacktester
                         res = bot.get_final_result()
                         last_eq = res['final_equity']
                    
                    pnl_total = last_eq - initial_capital
                    pnl_pct = (pnl_total / initial_capital) * 100
                    
                    print(f"   🔹 {bot.strategy_name:<25}: {last_eq:10.2f} € | {pnl_pct:+6.1f}%")
                    
                except Exception as e:
                    print(f"❌ Error updating {bot.strategy_name}: {e}")
            print("-" * 60)
                    
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")

if __name__ == "__main__":
    run_multi_backtest()

import sys
import os
import pandas as pd
from datetime import datetime

# Add Bot_trader to path FIRST to ensure finding its modules
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

from backtest import BufferedBacktester
from strategies import StandardStrategy, InstantStrategy

# Import Bot_trader modules
try:
    import bot_config
    from data_loader import MarketData
    from strategy import Strategy as MacroStrategy
    from policy import Policy
    from portfolio import PaperPortfolio
except ImportError as e:
    print(f"Error importing Bot_trader modules: {e}")
    sys.exit(1)

# Suppress logs
logging.getLogger().setLevel(logging.ERROR)

class MacroPolicyBacktester:
    def __init__(self, initial_capital=1000.0):
        self.initial_capital = initial_capital
        # Override config
        bot_config.INITIAL_CAPITAL = initial_capital
        bot_config.INITIAL_CASH = initial_capital
        
        self.market = MarketData()
        self.strategy = MacroStrategy()
        self.policy = Policy()
        self.portfolio = PaperPortfolio() # Reads config for init capital
        
    def run_simulation(self, start_date_str, quiet=False):
        # 1. Fetch Data
        if not quiet: print("   📥 Fetching Market & Macro Data (Bot_trader)...")
        
        # Need to parse start_date "dd/mm/yyyy" to "yyyy-mm-dd"
        start_dt = datetime.strptime(start_date_str, "%d/%m/%Y")
        start_fmt = start_dt.strftime("%Y-%m-%d")
        
        # Fetch slightly earlier for indicators
        hist_start = (start_dt - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        
        hist_data = self.market.get_market_data(start_date=hist_start)
        if hist_data.empty:
            return {'final_equity': 0, 'pnl': 0, 'pnl_percent': 0, 'trades': 0}
            
        hist_data = self.strategy.calculate_indicators(hist_data)
        
        # Macro
        pmi_series = self.market.get_pmi_data_fred(start_date=hist_data.index[0], end_date=hist_data.index[-1])
        macro_series = self.market.get_macro_data(start_date=hist_data.index[0], end_date=hist_data.index[-1])
        
        # Filter for Simulation
        backtest_data = hist_data.loc[start_fmt:].copy()
        
        # Join Macro
        backtest_data['PMI'] = backtest_data.index.map(lambda d: pmi_series.loc[d]['PMI'] if d in pmi_series.index else bot_config.PMI_DEFAULT)
        backtest_data['PMI'] = backtest_data['PMI'].ffill().fillna(bot_config.PMI_DEFAULT)
        
        backtest_data = backtest_data.join(macro_series, how='left')
        backtest_data['VIX'] = backtest_data['VIX'].ffill().fillna(20.0)
        backtest_data['TIPS'] = backtest_data['TIPS'].ffill().fillna(1.0)
        
        total_invested = self.initial_capital
        
        for date, row in backtest_data.iterrows():
            current_prices = {'BTC': row['BTC_Close'], 'GOLD': row['GOLD_Close']}
            pmi_val = row['PMI']
            tips_val = row['TIPS']
            vix_val = row['VIX']
            
            # Logic
            raw_signal = self.strategy.get_signal(row, pmi_val)
            regimen = self.policy.detectar_regimen(pmi_val, tips_val, vix_val)
            
            policy_decision = self.policy.aplicar_politica(
                raw_weights=raw_signal,
                current_prices=current_prices,
                holdings=self.portfolio.holdings,
                avg_prices=self.portfolio.avg_price,
                regimen=regimen
            )
            
            self.portfolio.rebalance(policy_decision, current_prices, date)
            self.portfolio.record_daily_status(date, current_prices, pmi_val)
            
        # Final Result
        final_prices = {
            'BTC': backtest_data.iloc[-1]['BTC_Close'],
            'GOLD': backtest_data.iloc[-1]['GOLD_Close']
        }
        final_equity = self.portfolio.get_total_value(final_prices)
        
        # To count "trades" we look at rebalance actions. Usually portfolio logs them.
        trades_count = len(self.portfolio.trade_log)
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'pnl': final_equity - self.initial_capital,
            'pnl_percent': (final_equity - self.initial_capital) / self.initial_capital * 100,
            'trades': trades_count
        }


def run_multi_backtest():
    start_date = "01/01/2020"
    initial_capital = 1000.0
    
    strategies = [
        ("Standard (MACD+EMA)", StandardStrategy(), 'standard'),
        ("Instant (Trend Follow)", InstantStrategy(), 'standard'),
        ("Macro Policy V2", None, 'macro') # None strategy obj because special runner
    ]
    
    results = []
    
    print(f"🚀 Starting Multi-Strategy Backtest (All Included)")
    print(f"📅 Start Date: {start_date}")
    print(f"💰 Initial Capital: {initial_capital} €")
    print("-" * 50)
    
    for name, strategy_obj, runner_type in strategies:
        print(f"\nrunning {name}...")
        
        try:
            if runner_type == 'standard':
                bt = BufferedBacktester(strategy_obj, initial_capital)
                bt.strategy_name = name
                res = bt.run_simulation(start_date, quiet=True)
            else:
                # Macro Runner
                bt = MacroPolicyBacktester(initial_capital)
                res = bt.run_simulation(start_date, quiet=True)
            
            res['name'] = name
            results.append(res)
            
            print(f"   ✅ Done. Final Equity: {res['final_equity']:.2f} €")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()
            
    # Print Comparison Table
    print("\n" + "="*80)
    print(f"{'STRATEGY':<25} | {'EQUITY':<12} | {'PnL €':<10} | {'PnL %':<10} | {'TRADES':<8}")
    print("-" * 80)
    
    # Sort by Equity descending
    results.sort(key=lambda x: x['final_equity'], reverse=True)
    
    for r in results:
        print(f"{r['name']:<25} | {r['final_equity']:<12.2f} | {r['pnl']:<10.2f} | {r['pnl_percent']:<9.1f}% | {r['trades']:<8}")
    
    print("="*80)
    if results:
        best = results[0]
        print(f"\n🏆 Best Strategy: {best['name']} (+{best['pnl_percent']:.1f}%)")

if __name__ == "__main__":
    run_multi_backtest()


