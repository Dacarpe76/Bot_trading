
import os
import ccxt
import time
from dotenv import load_dotenv

# Load env if present
load_dotenv()

class KrakenConnector:
    def __init__(self):
        self.api_key = os.getenv('KRAKEN_API_KEY')
        self.secret_key = os.getenv('KRAKEN_PRIVATE_KEY')
        self.env = os.getenv('KRAKEN_ENV', 'production')
        self.enable_margin = os.getenv('ENABLE_MARGIN_SHORTS', 'false').lower() == 'true'
        
        if not self.api_key or not self.secret_key:
            print("⚠️ WARNING: No API Keys found in .env. Live trading will fail.")
            self.exchange = None
        else:
            self.exchange = ccxt.kraken({
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'enableRateLimit': True,
            })
            if self.env == 'sandbox':
                self.exchange.set_sandbox_mode(True)
                
    def get_balance_equity(self):
        """Returns total equity in EUR and cash balance."""
        if not self.exchange:
            return 0.0, {}
            
        try:
            bal = self.exchange.fetch_balance()
            total_equity = bal['total'].get('EUR', 0.0)
            
            # Estimate BTC value
            btc_amt = bal['total'].get('BTC', 0.0)
            if btc_amt > 0:
                ticker = self.exchange.fetch_ticker('BTC/EUR')
                btc_val = btc_amt * ticker['last']
                total_equity += btc_val
            
            return total_equity, bal['total']
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return 0.0, {}

    def execute_rebalance(self, target_btc_weight, target_gold_weight):
        """
        Adjusts positions to match target weights.
        Positive weight = Long.
        Negative weight = Short (Margin).
        """
        if not self.exchange: return
        
        equity, balances = self.get_balance_equity()
        if equity <= 10.0: 
            print(f"⚠️ Low Equity ({equity:.2f}€). Skipping rebalance.")
            return
        
        print(f"🔄 Rebalancing... Equity: {equity:.2f}€ | Targets: BTC {target_btc_weight:.2%}, GOLD {target_gold_weight:.2%}")

        # --- 1. BTC Management ---
        current_btc = balances.get('BTC', 0.0) + balances.get('XXBT', 0.0)
        try:
            ticker_btc = self.exchange.fetch_ticker('BTC/EUR')
            price_btc = ticker_btc['last']
            
            target_btc_val = equity * target_btc_weight
            current_btc_val = current_btc * price_btc
            diff_btc = target_btc_val - current_btc_val
            
            # Threshold: 10 EUR
            if abs(diff_btc) > 10.0:
                amount = abs(diff_btc) / price_btc
                if diff_btc > 0:
                    # Buy
                    print(f"🚀 EXECUTING BUY: {amount:.6f} BTC (~{diff_btc:.2f}€)")
                    self.exchange.create_market_buy_order('BTC/EUR', amount)
                else:
                    # Sell
                    print(f"🔻 EXECUTING SELL: {amount:.6f} BTC (~{diff_btc:.2f}€)")
                    self.exchange.create_market_sell_order('BTC/EUR', amount)
        except Exception as e:
            print(f"❌ Error managing BTC: {e}")

        # --- 2. GOLD (PAXG) Management ---
        # Kraken uses PAXG for Gold usually.
        current_paxg = balances.get('PAXG', 0.0)
        try:
            # Check if PAXG/EUR exists, else try PAXG/USD or XAU?
            # Assuming PAXG/EUR for now as per previous scripts
            pair = 'PAXG/EUR'
            ticker_paxg = self.exchange.fetch_ticker(pair)
            price_paxg = ticker_paxg['last']
            
            target_paxg_val = equity * target_gold_weight
            current_paxg_val = current_paxg * price_paxg
            diff_paxg = target_paxg_val - current_paxg_val
            
            if abs(diff_paxg) > 10.0:
                amount = abs(diff_paxg) / price_paxg
                if diff_paxg > 0:
                    print(f"✨ EXECUTING BUY: {amount:.6f} PAXG (~{diff_paxg:.2f}€)")
                    self.exchange.create_market_buy_order(pair, amount)
                else:
                    print(f"🔸 EXECUTING SELL: {amount:.6f} PAXG (~{diff_paxg:.2f}€)")
                    self.exchange.create_market_sell_order(pair, amount)
        except Exception as e:
            print(f"❌ Error managing PAXG (Gold): {e}")

    def panic_close_all(self):
        """SELL EVERYTHING TO EUR"""
        if not self.exchange: return "No Connection"
        
        print("🚨 PANIC PROTOCOL INITIATED")
        try:
            self.exchange.cancel_all_orders()
            
            bal = self.exchange.fetch_balance()
            
            # Close BTC
            btc_amt = bal['total'].get('BTC', 0)
            if btc_amt > 0.0001: # Dust threshold
                print(f"Selling {btc_amt} BTC...")
                self.exchange.create_market_sell_order('BTC/EUR', btc_amt)
            
            # Close other assets if mapped...
            
            return "SUCCESS: All positions closed."
        except Exception as e:
            return f"PANIC FAIL: {e}"
