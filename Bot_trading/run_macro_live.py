
import logging
import sys
import os
import time
import pandas as pd
from datetime import datetime, timedelta

# Add Bot_trader to path
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
    def __init__(self, initial_capital=500.0):
        self.initial_capital = initial_capital
        
        # Override config for this instance
        bot_config.INITIAL_CAPITAL = initial_capital
        bot_config.INITIAL_CASH = initial_capital
        
        self.market = MarketData()
        self.strategy = MacroStrategy()
        self.policy = Policy()
        self.portfolio = PaperPortfolio() # Reads config for init capital which we just set
        self.strategy_name = "Macro Policy V2"
        self.daily_equity = []
        self.full_history = pd.DataFrame()
        
    def run_simulation(self, start_date_str, quiet=False, dca_amount=0.0):
        # 1. Fetch Data
        if not quiet: 
            print("==================================================")
            print(f"🚀 Starting Macro Policy V2 (Test Mode)")
            print(f"💰 Initial Capital: {self.initial_capital} €")
            if dca_amount > 0:
                print(f"📅 DCA Mode:       +{dca_amount}€ / month (Day 10)")
            print(f"📅 Start Date:      {start_date_str}")
            print("==================================================")
            print("   📥 Fetching Market & Macro Data (Bot_trader)...")
        
        start_dt = datetime.strptime(start_date_str, "%d/%m/%Y")
        start_fmt = start_dt.strftime("%Y-%m-%d")
        
        # Fetch slightly earlier for indicators
        hist_start = (start_dt - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        
        hist_data = self.market.get_market_data(start_date=hist_start)
        if hist_data.empty:
            print("❌ Error: No historic data provided.")
            return {'final_equity': 0, 'pnl': 0, 'pnl_percent': 0, 'trades': 0}
            
        hist_data = self.strategy.calculate_indicators(hist_data)
        
        # Macro Data
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
        
        # Save history for live updates logic
        self.full_history = backtest_data
        
        print(f"   ⚙️  Simulating {len(backtest_data)} days...")
        
        for date, row in backtest_data.iterrows():
            # DCA Logic: Add capital on the 10th of every month
            if dca_amount > 0 and date.day == 10:
                self.portfolio.add_monthly_contribution(date=date, amount=dca_amount)
                
            self.process_daily_step(date, row)
            
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
        
        # --- MANUAL OVERRIDE REMOVED ---
        # The strategy will now follow pure algo logic.
        # -------------------------------
            
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
        print(f"[{datetime.now().strftime('%H:%M')}] 📡 Monitor: Checking for new market data...")
        
        # Fetch last 260 days (enough for EMA200)
        start_active = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")
        active_chunk = self.market.get_market_data(start_date=start_active)
        
        if active_chunk.empty:
            print("   💤 No data returned.")
            return

        active_chunk = self.strategy.calculate_indicators(active_chunk)

        # Identify NEW rows
        if self.full_history.empty:
            last_ts = pd.Timestamp("2000-01-01").tz_localize(None)
        else:
            last_ts = self.full_history.index[-1]
            
        # Ensure timezone naiveness for comparison if needed
        if active_chunk.index.tz is not None:
            active_chunk.index = active_chunk.index.tz_localize(None)
        if last_ts.tz is not None:
            last_ts = last_ts.tz_localize(None)

        new_rows = active_chunk[active_chunk.index > last_ts].copy()
        
        if new_rows.empty:
            print("   💤 No new closed candles (Daily).")
            # In a real live bot, we might check hourly, but this strategy assumes Daily granularity.
            return
            
        print(f"   ✨ Processing {len(new_rows)} new day(s)...")
        
        # Fetch latest Macro (simplified: assume defaults if fill fails or fetch real)
        # For simplicity in this test script, we reuse the last known Macro values or defaults
        # To do this properly we'd need to re-fetch Fred/Yahoo Macro data here.
        # Let's assume constant macro for the "live" update gap to avoid complexity unless requested.
        # (Real implementation involves `market.get_pmi_data_fred` again)
        
        for date, row in new_rows.iterrows():
            # Inject defaults for missing columns
            if 'PMI' not in row: row['PMI'] = bot_config.PMI_DEFAULT
            if 'VIX' not in row: row['VIX'] = 20.0
            if 'TIPS' not in row: row['TIPS'] = 1.0
            
            self.process_daily_step(date, row)
            # Append to history
            self.full_history = pd.concat([self.full_history, new_rows.loc[[date]]])

        stats = self.get_current_stats()
        print(f"   ✅ Update Complete. Equity: {stats['final_equity']:.2f} €")

    def start_fresh(self):
        """Fetches history for indicators but does NOT simulate past trades."""
        print("==================================================")
        print(f"🚀 Starting Macro Policy V2 (Fresh Start)")
        print(f"💰 Initial Capital: {self.initial_capital} €")
        print("==================================================")
        print("   📥 Warming up indicators (fetching last 365 days)...")
        
        # Fetch last 365 days for indicators (EMA200, etc)
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        hist_data = self.market.get_market_data(start_date=start_date)
        if hist_data.empty:
            print("❌ Error: No historic data provided.")
            return
            
        # Calculate indicators
        hist_data = self.strategy.calculate_indicators(hist_data)
        
        # Store as history (so we know where we are)
        # But do NOT run process_daily_step (no past trades)
        self.full_history = hist_data
        
        print(f"   ✅ Indicators ready. Last data point: {self.full_history.index[-1].strftime('%Y-%m-%d')}")
        print(f"   🛡️  Portfolio is CLEAN. Starting with {self.initial_capital} EUR.")

def main():
    bot = MacroPolicyBacktester(initial_capital=500.0)
    
    # 1. Start Fresh (No Backtest)
    bot.start_fresh()
    
    print("\n📡 ENTERING LIVE MONITOR MODE")
    print("   The bot will check for new daily candles every hour.")
    print("   (Note: Macro Policy trades on Daily Close)")
    print("   Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(5) # Small buffer
            bot.update_live()
            time.sleep(3600) # Wait 1 hour
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")

if __name__ == "__main__":
    main()
