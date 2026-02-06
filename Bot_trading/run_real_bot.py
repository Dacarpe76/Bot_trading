
import logging
import sys
import os
import time
import json
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
    from real_portfolio import RealPortfolio # <--- REAL TRADING
except ImportError as e:
    print(f"Error importing Bot_trader modules: {e}")
    sys.exit(1)

# Suppress logs
logging.getLogger().setLevel(logging.ERROR)

STATUS_FILE = "bot_status.json"

class RealBotRunner:
    def __init__(self):
        self.market = MarketData()
        self.strategy = MacroStrategy()
        self.policy = Policy()
        self.portfolio = RealPortfolio() # Real execution
        self.strategy_name = "Macro Policy (REAL)"
        
    def save_status(self, message="Running"):
        """Saves current status to file for the App/API"""
        stats = {}
        try:
             # Get holding/value from portfolio
             # We can't easily get 'pnl' without a fixed start reference in Real mode unless we track it.
             # For now, just show current equity.
             equity = self.portfolio.get_total_value({}) # Prices not needed for equity check in RealPortfolio
             status_data = {
                 "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "equity": equity,
                 "message": message,
                 "holdings": self.portfolio.holdings
             }
             with open(STATUS_FILE, 'w') as f:
                 json.dump(status_data, f)
        except Exception as e:
            print(f"Error saving status: {e}")

    def update_live(self):
        print(f"[{datetime.now().strftime('%H:%M')}] 📡 Monitor: Checking market data...")
        self.save_status("Checking Data...")
        
        # 1. Fetch recent data
        start_active = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")
        active_chunk = self.market.get_market_data(start_date=start_active)
        
        if active_chunk.empty:
            print("   💤 No data.")
            self.save_status("No Data Received")
            return

        # 2. Indicators
        active_chunk = self.strategy.calculate_indicators(active_chunk)
        
        # 3. Process Latest Day (Assume Daily Candle Close Strategy)
        # In real live, we check if the last closed candle (yesterday) signals a change.
        # Or if "Today" is valid? Yahoo finance gives live data for 'today'.
        # Macro Policy usually trades on confirmed daily close.
        # We'll take the LAST row (could be today live or yesterday close).
        
        last_row = active_chunk.iloc[-1]
        last_date = active_chunk.index[-1]
        
        # Macro Data (Simplified fetch)
        # Ideally we fetch fresh PMI/VIX here.
        pmi_val = bot_config.PMI_DEFAULT # Placeholder for live fetch
        vix_val = 20.0
        tips_val = 1.0
        
        print(f"   📅 Date processing: {last_date.strftime('%Y-%m-%d')}")
        
        current_prices = {
            'BTC': last_row['BTC_Close'], 
            'GOLD': last_row['GOLD_Close']
        }
        
        # Logic
        raw_signal = self.strategy.get_signal(last_row, pmi_val)
        regimen = self.policy.detectar_regimen(pmi_val, tips_val, vix_val)
        
        policy_decision = self.policy.aplicar_politica(
            raw_weights=raw_signal,
            current_prices=current_prices,
            holdings=self.portfolio.holdings,
            avg_prices=self.portfolio.avg_price,
            regimen=regimen
        )
        
        print(f"   🤖 Decision: {policy_decision.get('policy_log', [])}")
        
        # EXECUTE
        self.portfolio.rebalance(policy_decision, current_prices, last_date)
        
        self.save_status(f"Active. Last check: {datetime.now().strftime('%H:%M')}")
        print(self.portfolio.get_status_str(current_prices))

def main():
    print("==================================================")
    print("🚀 STARTING REAL KRAKEN BOT")
    print("   WARNING: Real Money Execution Enabled.")
    print("==================================================")
    
    bot = RealBotRunner()
    
    try:
        while True:
            bot.update_live()
            print("   💤 Sleeping 1 hour...")
            # Sleep 1 hour
            for _ in range(60): 
                time.sleep(60) 
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")

if __name__ == "__main__":
    main()
