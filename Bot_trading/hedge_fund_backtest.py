
import sys
import os
import logging
import pandas as pd
import bot_config
from datetime import datetime, timedelta

# Ensure Bot_trader is in path
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

from run_macro_live import MacroPolicyBacktester
from portfolio import PaperPortfolio

class HedgePortfolio(PaperPortfolio):
    def __init__(self):
        super().__init__()
        self.holdings['ETH'] = 0.0
        self.avg_price['ETH'] = 0.0
        # Initialize holdings to 0.0 if not present (PaperPortfolio sets BTC/GOLD)
    
    def add_staking_rewards(self, annual_rate=0.04):
        """Applies daily interest to Cash (USDC Staking)"""
        if self.cash > 0:
            daily_rate = (1 + annual_rate)**(1/365) - 1
            reward = self.cash * daily_rate
            self.cash += reward
            return reward
        return 0.0

    def get_total_value(self, current_prices):
        val = self.cash
        for asset, units in self.holdings.items():
            price = current_prices.get(asset, 0.0)
            val += units * price
        return val

    def rebalance(self, policy_result, current_prices, date):
        # Extend parent rebalance logic to support ETH and SHORTING
        # Note: Parent rebalance hardcodes BTC/GOLD. We need to implement a generic one or override.
        # Since parent is hardcoded, we'll write a generic one here matching the logic.
        
        reasons = policy_result.get('policy_log', [])
        regimen = policy_result.get('regimen', 'UNKNOWN')
        
        total_val = self.get_total_value(current_prices)
        
        # Iterate through target weights
        # We expect policy_result to have keys like 'btc_weight', 'gold_weight', 'eth_weight'
        
        for asset, key_weight in [('BTC', 'btc_weight'), ('GOLD', 'gold_weight'), ('ETH', 'eth_weight')]:
            target_weight = policy_result.get(key_weight, 0.0)
            target_val = total_val * target_weight
            
            current_price = current_prices.get(asset, 0.0)
            if current_price == 0: continue
            
            current_units = self.holdings.get(asset, 0.0)
            current_val = current_units * current_price
            
            diff = target_val - current_val
            
            # Threshold to trade (avoid dust)
            if abs(diff) > 10.0:
                # Execution
                trade_val = abs(diff)
                trade_units = trade_val / current_price
                
                if diff > 0:
                    # BUY (or Cover Short)
                    cost = trade_val
                    # Check cash if we are increasing position (buying)
                    # If we are covering a short (going from -1 to -0.5), we are paying cash too?
                    # Wait, covering short = buying back. Yes cost cash.
                    # Opening long = buying. Cost cash.
                    
                    if self.cash >= cost:
                        self.cash -= cost
                        self.holdings[asset] = current_units + trade_units
                        
                        # Avg Price update (only for Long adds?) Simplification: update always
                        if self.holdings[asset] > 0:
                             old_units = max(0, current_units) # Don't mix short avg
                             # Simple weighted avg
                             self.avg_price[asset] = ((old_units * self.avg_price.get(asset,0)) + (trade_units * current_price)) / self.holdings[asset]
                        
                        self.trade_log.append({
                            'Date': date, 'Action': 'BUY', 'Asset': asset, 'Amount': trade_units, 
                            'Price': current_price, 'Value': -cost, 'Cash_After': self.cash
                        })
                else:
                    # SELL (or Open Short)
                    # Receives Cash
                    self.cash += trade_val
                    self.holdings[asset] = current_units - trade_units
                    
                    self.trade_log.append({
                        'Date': date, 'Action': 'SELL', 'Asset': asset, 'Amount': trade_units, 
                         'Price': current_price, 'Value': trade_val, 'Cash_After': self.cash
                    })

class HedgeFundBacktester(MacroPolicyBacktester):
    def __init__(self, initial_capital=500.0):
        super().__init__(initial_capital)
        self.portfolio = HedgePortfolio()
        self.portfolio.cash = initial_capital # Sync cash
        self.hedge_data = pd.DataFrame()
        self.load_hedge_data()
        
    def load_hedge_data(self):
        try:
            self.hedge_data = pd.read_csv("hedge_data.csv", index_col='date', parse_dates=True)
            print(f"Loaded Hedge Data: {len(self.hedge_data)} rows.")
        except Exception as e:
            print(f"Error loading hedge data: {e}")

    def process_daily_step(self, date, row):
        # 1. Apply Staking Interest (Daily) - "Cubo 3 Optimizado"
        # 4% APY default
        self.portfolio.add_staking_rewards(annual_rate=0.04)
        
        # 2. Get Prices & Macro
        current_prices = {
            'BTC': row['BTC_Close'], 
            'GOLD': row['GOLD_Close']
        }
        
        # Get ETH Price from hedge_data
        eth_price = 0.0
        dxy = 0.0
        fng = 50.0 # Neutral default
        
        if date in self.hedge_data.index:
            h_row = self.hedge_data.loc[date]
            # Handle duplicates if any, take first
            if isinstance(h_row, pd.DataFrame): h_row = h_row.iloc[0]
            
            eth_price = h_row['ETH_Price'] if pd.notna(h_row['ETH_Price']) else 0.0
            dxy = h_row['DXY'] if pd.notna(h_row['DXY']) else 0.0
            fng = h_row['fng_value'] if pd.notna(h_row['fng_value']) else 50.0
        
        # Fallback ETH price if missing (simulation robustness)
        if eth_price == 0: eth_price = current_prices['BTC'] * 0.05 # Mock ratio if missing
        
        current_prices['ETH'] = eth_price
        
        pmi_val = row['PMI']
        tips_val = row['TIPS'] if 'TIPS' in row else 1.0
        vix_val = row['VIX'] if 'VIX' in row else 20.0

        # 3. Base Strategy Signal (Macro Policy)
        raw_signal = self.strategy.get_signal(row, pmi_val)
        regimen = self.policy.detectar_regimen(pmi_val, tips_val, vix_val)
        
        # Get base weights (Risk On vs Risk Off)
        # raw_signal example: {'btc_weight': 0.6, 'gold_weight': 0.4} or cash implied
        # We need to interpret 'policy.aplicar_politica' logic manually to intercept it,
        # OR call it and then modify weights.
        # Let's call standard policy first.
        
        policy_decision = self.policy.aplicar_politica(
            raw_weights=raw_signal,
            current_prices=current_prices,
            holdings=self.portfolio.holdings,
            avg_prices=self.portfolio.avg_price,
            regimen=regimen
        )
        
        # 4. Apply Hedge Fund Logic
        final_decision = policy_decision.copy()
        final_decision['eth_weight'] = 0.0 # Default
        log_notes = []
        
        btc_w = final_decision.get('btc_weight', 0.0)
        gold_w = final_decision.get('gold_weight', 0.0)
        
        # --- LOGIC 1 & 3: Shorting & ETH ---
        
        # Is it Risk ON? (BTC/Gold > 0)
        is_risk_on = (btc_w + gold_w) > 0.1
        
        if not is_risk_on:
            # === RISK OFF (Safe/Liquidity) ===
            # Logic 1: "Hedge" (Short) if DXY > 103 and Greedy
            if dxy > 103 and fng > 50:
                # SHORT BTC
                # Leverage x2? Let's use x1 Short (-100%) or x0.5 (-50%) of portfolio?
                # "abres una posición de Venta (Short) [...] x2"
                # Let's simple model: Target BTC = -0.2 (20% Short) or more aggressive?
                # User said: "simple low leverage". 
                # Let's set target short to be -0.5 (50% of capital shorted).
                final_decision['btc_weight'] = -0.5 
                log_notes.append("HEDGE TRIGGER: SHORT BTC (DXY>103 & FnG>50)")
            else:
                # Just Staking (Cash) - Already handled by stay in cash + add_staking_rewards
                pass
                
        else:
            # === RISK ON (Growth) ===
            # Logic 3: ETH Inclusion
            # Base Risk Bucket typically BTC.
            # "Dividiremos el Cubo 1 (Riesgo) en dos: 70% BTC y 30% ETH."
            # "ETH solo cuando Fear & Greed sea muy bajo (< 30)"
            
            if fng < 30:
                # Split the BTC allocation
                original_btc_w = btc_w
                new_btc_w = original_btc_w * 0.7
                new_eth_w = original_btc_w * 0.3
                
                final_decision['btc_weight'] = new_btc_w
                final_decision['eth_weight'] = new_eth_w
                log_notes.append("ETH OPPORTUNITY: FnG < 30 (Buying Dip)")
            else:
                # Keep as BTC (ETH part stays in BTC)
                pass
        
        if log_notes:
            final_decision['policy_log'] = final_decision.get('policy_log', []) + log_notes

        # 5. Execute Rebalance
        # Logic 4: "Rebalanceo Automático por Volatilidad" 
        # Handled by daily checking diff > 10 EUR in portfolio.rebalance
        
        self.portfolio.rebalance(final_decision, current_prices, date)
        
        # Record history
        # We need custom record daily status to include ETH and Staking Yield accumulation invisible
        # But 'record_daily_status' in portfolio just snapshots.
        
        total_val = self.portfolio.get_total_value(current_prices)
        self.daily_equity.append({
            'date': date.strftime("%Y-%m-%d"),
            'equity': total_val
        })
