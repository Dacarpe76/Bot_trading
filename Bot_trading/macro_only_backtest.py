
import logging
import sys
import os
import time
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Add Bot_trader to path FIRST to ensure finding its modules
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

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
        # Try to use local pmi_history.csv if available (created in previous steps)
        # The data_loader.get_pmi_data_fred logic we saw earlier actually tries to load local file first!
        # So we just call it.
        pmi_series = self.market.get_pmi_data_fred(start_date=hist_data.index[0], end_date=hist_data.index[-1])
        macro_series = self.market.get_macro_data(start_date=hist_data.index[0], end_date=hist_data.index[-1])
        
        # Filter for Simulation
        backtest_data = hist_data.loc[start_fmt:].copy()
        
        # Join Macro
        # Ensure we map PMI correctly. pmi_series index is datetime.
        # backtest_data index is datetime.
        # We need to be careful with timezone matching if indices are tz-aware/naive.
        # usually get_market_data strips tz. get_pmi_data_fred logic also does some parsing.
        
        # Safe map
        backtest_data['PMI'] = backtest_data.index.map(lambda d: pmi_series.loc[d]['PMI'] if d in pmi_series.index else bot_config.PMI_DEFAULT)
        # Forward fill PMI gaps
        backtest_data['PMI'] = backtest_data['PMI'].ffill().fillna(bot_config.PMI_DEFAULT)
        
        backtest_data = backtest_data.join(macro_series, how='left')
        backtest_data['VIX'] = backtest_data['VIX'].ffill().fillna(20.0)
        backtest_data['TIPS'] = backtest_data['TIPS'].ffill().fillna(1.0)
        
        print(f"   ⚙️  Simulating {len(backtest_data)} days...")

        for date, row in backtest_data.iterrows():
            self.process_daily_step(date, row)
            
        # Final Stats
        return self.get_current_stats()

    def process_daily_step(self, date, row):
        current_prices = {'BTC': row['BTC_Close'], 'GOLD': row['GOLD_Close']}
        pmi_val = row['PMI']
        tips_val = row['TIPS'] if 'TIPS' in row else 1.0
        vix_val = row['VIX'] if 'VIX' in row else 20.0
            
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
        
        # Record equity
        total_val = self.portfolio.get_total_value(current_prices)
        self.daily_equity.append({
            'date': date.strftime("%Y-%m-%d"),
            'equity': total_val
        })

    def get_current_stats(self):
        last_prices = {'BTC': 0, 'GOLD': 0}
        # We don't keep full history object in this simplified version like run_macro_live
        # But we can get last prices from the last step or portfolio logs?
        # Actually portfolio might not store current market prices if we don't hold them.
        # But for 'daily_equity' correctness we need them.
        # Simplification: just take the last equity value.
        
        final_equity = self.daily_equity[-1]['equity'] if self.daily_equity else self.initial_capital
        trades_count = len(self.portfolio.trade_log)
        return {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'pnl': final_equity - self.initial_capital,
            'pnl_percent': (final_equity - self.initial_capital) / self.initial_capital * 100,
            'trades': trades_count
        }


def run_macro_vs_sp500():
    start_date_str = "01/01/2020" # Explicit string format expected by runner
    initial_capital = 1000.0
    
    print(f"🚀 Starting Macro Policy vs S&P 500 Comparison")
    print(f"📅 Start Date: {start_date_str}")
    print(f"💰 Initial Capital: {initial_capital} €")
    print("-" * 50)
    
    # 1. Run Macro Policy
    print("\n[1/2] Running Macro Policy Simulation...")
    bot = MacroPolicyBacktester(initial_capital)
    res = bot.run_simulation(start_date_str, quiet=False)
    
    print(f"   ✅ Macro Policy Final: {res['final_equity']:.2f} € (+{res['pnl_percent']:.1f}%)")
    
    # 2. Fetch S&P 500 (SPY)
    print("\n[2/2] Fetching S&P 500 (SPY) Data...")
    
    # Needs YYYY-MM-DD
    yf_start = datetime.strptime(start_date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    
    try:
        spy = yf.download("SPY", start=yf_start, progress=False, auto_adjust=False)
        
        # Clean columns if MultiIndex
        if isinstance(spy.columns, pd.MultiIndex):
            # Flatten to 'Price_Ticker' but mainly we want Adj Close or Close
            spy.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in spy.columns.values]
            
        # Find close col
        close_col = next((c for c in spy.columns if 'Adj Close' in c), None)
        if not close_col:
            close_col = next((c for c in spy.columns if 'Close' in c), None)
            
        if not close_col:
            print("❌ Error: Could not find Close column for SPY.")
            return

        spy = spy[[close_col]].copy()
        spy.rename(columns={close_col: 'SP500_Price'}, inplace=True)
        if spy.index.tz is not None: spy.index = spy.index.tz_localize(None)
        
        print(f"   ✅ Fetched {len(spy)} days of SPY data.")
        
    except Exception as e:
        print(f"❌ Error fetching SPY: {e}")
        return

    # 3. Compare
    print("\n📊 Generating Comparison...")
    
    macro_df = pd.DataFrame(bot.daily_equity)
    macro_df['date'] = pd.to_datetime(macro_df['date'])
    macro_df.set_index('date', inplace=True)
    macro_df.rename(columns={'equity': 'Macro_Policy'}, inplace=True)
    
    # Merge
    combined = macro_df.join(spy, how='inner')
    
    if combined.empty:
        print("❌ No overlapping dates found.")
        return
        
    # Scale SP500
    # SP500 Equity = (Price / StartPrice) * InitialCapital
    start_price_spy = combined['SP500_Price'].iloc[0]
    start_equity_macro = combined['Macro_Policy'].iloc[0] # Should be close to 1000
    
    combined['S&P_500'] = (combined['SP500_Price'] / start_price_spy) * start_equity_macro
    
    # Calculate Final Stats
    final_macro = combined['Macro_Policy'].iloc[-1]
    final_spy = combined['S&P_500'].iloc[-1]
    
    ret_macro = (final_macro - start_equity_macro) / start_equity_macro * 100
    ret_spy = (final_spy - start_equity_macro) / start_equity_macro * 100
    
    print("\n" + "="*60)
    print(f"{'STRATEGY':<20} | {'FINAL EQUITY (€)':<18} | {'RETURN (%)':<10}")
    print("-" * 60)
    print(f"{'Macro Policy':<20} | {final_macro:<18.2f} | {ret_macro:<+10.1f}")
    print(f"{'S&P 500 (SPY)':<20} | {final_spy:<18.2f} | {ret_spy:<+10.1f}")
    print("="*60)
    
    # Save CSV
    combined.to_csv("macro_vs_sp500_results.csv")
    print(f"\n💾 Data saved to: macro_vs_sp500_results.csv")
    
    # Plot
    plt.style.use('bmh')
    plt.figure(figsize=(12, 6))
    plt.plot(combined.index, combined['Macro_Policy'], label=f'Macro Policy ({ret_macro:+.1f}%)', color='green', linewidth=2)
    plt.plot(combined.index, combined['S&P_500'], label=f'S&P 500 ({ret_spy:+.1f}%)', color='blue', alpha=0.7)
    
    plt.title('Performance Comparison: Macro Policy vs S&P 500')
    plt.xlabel('Date')
    plt.ylabel('Equity (EUR)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plot_path = "macro_vs_sp500_plot.png"
    plt.savefig(plot_path)
    print(f"📈 Chart saved to: {plot_path}")

if __name__ == "__main__":
    run_macro_vs_sp500()
