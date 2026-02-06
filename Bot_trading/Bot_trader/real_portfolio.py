
from datetime import datetime
import pandas as pd
from kraken_connector import KrakenConnector

class RealPortfolio:
    def __init__(self):
        self.connector = KrakenConnector()
        self.trade_log = [] # Local session log
        self.history = [] # Local session history

    @property
    def holdings(self):
        # Fetch live holdings from Kraken
        if not self.connector.exchange:
            return {'BTC': 0.0, 'GOLD': 0.0}
        
        _, bal = self.connector.get_balance_equity()
        # Bal is dict like {'EUR': ..., 'BTC': ..., 'PAXG': ...}
        return {
            'BTC': bal.get('BTC', 0.0) + bal.get('XXBT', 0.0),
            'GOLD': bal.get('PAXG', 0.0) # Mapping Gold to PAXG
        }

    @property
    def avg_price(self):
        # Kraken API doesn't give easy "avg buy price" for current holdings without full history analysis.
        # For Policy logic that relies on this (like HODL protections), we might default to 0 
        # which effectively disables "Sell only if profit" logic, OR we assume current price.
        # For V1 Real, we disable complex HODL logic and trust the Policy weights.
        return {'BTC': 0.0, 'GOLD': 0.0}

    def rebalance(self, policy_result, current_prices, date):
        """
        Executes rebalance via KrakenConnector
        """
        target_btc = policy_result.get('btc_weight', 0.0)
        target_gold = policy_result.get('gold_weight', 0.0)
        
        print(f"⚡ REAL PORTFOLIO: Sending Rebalance Command -> BTC: {target_btc}, GOLD: {target_gold}")
        
        if self.connector.exchange:
            self.connector.execute_rebalance(target_btc, target_gold)
            
            # Log this action (simplified)
            self.trade_log.append({
                'Date': date,
                'Action': 'REBALANCE_ATTEMPT',
                'Details': f"Targets: BTC {target_btc}, GOLD {target_gold}"
            })

    def get_total_value(self, current_prices):
        equity, _ = self.connector.get_balance_equity()
        return equity

    def record_daily_status(self, date, current_prices, pmi_val):
        equity, bal = self.connector.get_balance_equity()
        self.history.append({
            'Date': date,
            'TotalValue': equity,
            'Cash': bal.get('EUR', 0.0),
            'BTC_Units': bal.get('BTC', 0.0),
            'GOLD_Units': bal.get('PAXG', 0.0),
            'PMI': pmi_val
        })

    def get_status_str(self, current_prices):
        equity, bal = self.connector.get_balance_equity()
        eur = bal.get('EUR', 0.0)
        btc = bal.get('BTC', 0.0)
        paxg = bal.get('PAXG', 0.0)
        
        return (f"🏛️ KRAKEN ACCT STATUS:\n"
                f"  Total Equity: {equity:.2f}€\n"
                f"  Cash (EUR):   {eur:.2f}€\n"
                f"  BTC:          {btc:.6f}\n"
                f"  PAXG (Gold):  {paxg:.6f}")
