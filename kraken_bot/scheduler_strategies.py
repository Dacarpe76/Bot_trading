
import ccxt
import pandas as pd
import yfinance as yf
import requests
import json
import os
import time
import datetime
import logging
from kraken_bot import config
from kraken_bot import policy

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SchedulerStrategies")

class IndicatorFetcher:
    """Helper to fetch Macro Indicators (PMI, VIX, DXY, F&G)."""
    @staticmethod
    def fetch_all():
        data = {}
        
        # 1. Fear & Greed
        try:
            resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
            fng = int(resp.json()['data'][0]['value'])
            data['fng'] = fng
        except Exception:
            data['fng'] = 50

        # 2. DXY
        try:
            dxy = yf.Ticker("DX-Y.NYB").history(period="5d")
            if dxy.empty: dxy = yf.Ticker("DX=F").history(period="5d")
            data['dxy'] = dxy['Close'].iloc[-1] if not dxy.empty else 100.0
        except: data['dxy'] = 100.0

        # 3. VIX
        try:
            vix = yf.Ticker("^VIX").history(period="5d")
            data['vix'] = vix['Close'].iloc[-1] if not vix.empty else 20.0
        except: data['vix'] = 20.0
        
        # 4. TIPS (10Y Real Yield) - Proxy via ETF (TIP) vs Treasury (IEF)?
        # Or fetch directly via Treasury API? Hard.
        # Approximation: US10Y - Inflation Breakeven?
        # Let's use a fixed placeholder or simple proxy via yfinance if possible.
        # Using proxy: Rate used in Policy is around 1.5-2.5.
        data['tips'] = 1.8 # Placeholder

        # 5. PMI
        # Hard to get free real-time. Use manual setting or valid placeholder.
        data['pmi'] = 49.0 # Placeholder: Neutral/Contraction
        
        return data

class KrakenMacroStrategy:
    """
    Real execution on Kraken based on Macro Policy.
    Runs every 24h.
    """
    def __init__(self):
        self.api_key = config.KRAKEN_API_KEY
        self.secret = config.KRAKEN_PRIVATE_KEY
        self.policy_engine = policy.Policy()
        
        if self.api_key and self.secret:
            self.exchange = ccxt.kraken({
                'apiKey': self.api_key,
                'secret': self.secret,
                'enableRateLimit': True
            })
        else:
            self.exchange = None
            logger.warning("Kraken Keys missing. Real Strategy will run in DRY MODE.")

    def run(self):
        logger.info(">>> Running Kraken Macro Strategy (Real) <<<")
        
        # 1. Get Indicators
        inds = IndicatorFetcher.fetch_all()
        regime = self.policy_engine.detectar_regimen(
            pmi=inds['pmi'], tips=inds['tips'], vix=inds['vix']
        )
        logger.info(f"Market Regime: {regime} (PMI={inds['pmi']}, VIX={inds['vix']:.1f})")
        
        if not self.exchange:
            logger.info("Exchange not connected. Skipping execution.")
            return

        try:
            # 2. Fetch Balance & Prices
            bal = self.exchange.fetch_balance()
            total_equity = bal['total']['EUR'] # Base in EUR? Or sum of assets?
            # Kraken 'total' usually gives amounts. We need value.
            
            # Fetch Prices
            ticker_btc = self.exchange.fetch_ticker('XBT/EUR')
            ticker_paxg = self.exchange.fetch_ticker('PAXG/EUR')
            
            price_btc = ticker_btc['last']
            price_paxg = ticker_paxg['last']
            
            holdings = {
                'BTC': bal['total'].get('XXBT', bal['total'].get('BTC', 0.0)),
                'GOLD': bal['total'].get('PAXG', 0.0),
                'EUR': bal['total'].get('ZEUR', bal['total'].get('EUR', 0.0))
            }
            
            # Calc Total Equity
            equity = holdings['EUR'] + (holdings['BTC'] * price_btc) + (holdings['GOLD'] * price_paxg)
            logger.info(f"Total Equity: {equity:.2f} EUR")
            
            curr_weights = {
                'btc_weight': (holdings['BTC'] * price_btc) / equity,
                'gold_weight': (holdings['GOLD'] * price_paxg) / equity
            }
            
            # 3. Policy Calculation
            # Need avg prices for logic. Fetch from trades history or estimation?
            # For V1, assume avg = current (disable gain-based logic unless we track it locally)
            avg_prices = {'BTC': price_btc, 'GOLD': price_paxg} 
            
            policy_res = self.policy_engine.aplicar_politica(
                curr_weights, 
                {'BTC': price_btc, 'GOLD': price_paxg}, 
                holdings, avg_prices, regime
            )
            
            logger.info(f"Policy Result: {policy_res}")
            
            # 4. Execution (Rebalance)
            self.execute_rebalance(policy_res, equity, holdings, {'BTC': price_btc, 'GOLD': price_paxg})

        except Exception as e:
            logger.error(f"Kraken Execution Failed: {e}")

    def execute_rebalance(self, result, equity, holdings, prices):
        """Simplistic Rebalancer: Target Value - Current Value."""
        
        targets = {
            'BTC': result['btc_weight'] * equity,
            'GOLD': result['gold_weight'] * equity,
        }
        # EUR is residual
        
        # BTC
        diff_btc_val = targets['BTC'] - (holdings['BTC'] * prices['BTC'])
        if abs(diff_btc_val) > 10.0: # Threshold 10 EUR
            amt = abs(diff_btc_val) / prices['BTC']
            side = 'buy' if diff_btc_val > 0 else 'sell'
            logger.info(f"ORDER: {side.upper()} BTC {amt:.6f} (~{abs(diff_btc_val):.2f} EUR)")
            try:
                self.exchange.create_order('XBT/EUR', 'market', side, amt)
            except Exception as e:
                logger.error(f"Order Failed: {e}")

        # GOLD
        diff_gold_val = targets['GOLD'] - (holdings['GOLD'] * prices['GOLD'])
        if abs(diff_gold_val) > 10.0:
            amt = abs(diff_gold_val) / prices['GOLD']
            side = 'buy' if diff_gold_val > 0 else 'sell'
            logger.info(f"ORDER: {side.upper()} PAXG {amt:.6f} (~{abs(diff_gold_val):.2f} EUR)")
            try:
                self.exchange.create_order('PAXG/EUR', 'market', side, amt)
            except Exception as e:
                logger.error(f"Order Failed: {e}")

    def get_status(self):
        """Returns current status for GUI."""
        # Simple text summary or dict
        status = {
            "name": "Kraken Real Macro",
            "active": self.exchange is not None,
            "equity": 0.0,
            "holdings": {},
            "regime": "Unknown"
        }
        return status


class FiveCubesSimStrategy:
    """
    Simulated Execution on Binance (Five Cubes Logic).
    Initial Capital: 500 EUR (converted to USDT for calc).
    Runs every 24h.
    """
    STATE_FILE = "sim_wallet_fivecubes.json"
    
    def __init__(self):
        self.exchange = ccxt.binance() # Public only needed
        self.initial_capital_eur = 500.0
        self.load_state()
        
        # 5 Cubes Modes
        self.MODES = {
            'ATTACK': {'SOL': 0.40, 'ETH': 0.30, 'BTC': 0.30, 'PAXG': 0.0, 'STABLE': 0.0},
            'CRUISE': {'BTC': 0.40, 'ETH': 0.30, 'SOL': 0.30, 'PAXG': 0.0, 'STABLE': 0.0},
            'SHIELD': {'BTC': 0.40, 'ETH': 0.0, 'SOL': 0.0, 'PAXG': 0.40, 'STABLE': 0.20}
        }

    def load_state(self):
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, 'r') as f:
                    self.state = json.load(f)
            except:
                self.reset_state()
        else:
            self.reset_state()
            
    def reset_state(self):
        # Start with 500 EUR equivalent in USDT
        # Assume EUR/USDT = 1.05 approx
        usdt_start = self.initial_capital_eur * 1.05 
        self.state = {
            'balance_usdt': usdt_start,
            'holdings': {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0},
            'history': []
        }
        self.save_state()

    def save_state(self):
        with open(self.STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=4)

    def run(self):
        logger.info(">>> Running Five Cubes Sim (Binance) <<<")
        try:
            # 1. Indicators & Mode
            inds = IndicatorFetcher.fetch_all()
            
            # Logic from five_cubes_bot.py
            # F&G < 20 -> ATTACK
            # DXY < 101 & PMI > 50 -> CRUISE
            # Else -> SHIELD
            mode = "SHIELD"
            if inds['fng'] < 20: mode = "ATTACK"
            elif inds['dxy'] < 101 and inds['pmi'] > 50: mode = "CRUISE"
            
            logger.info(f"5 Cubes Mode: {mode} (F&G={inds['fng']}, DXY={inds['dxy']:.1f})")
            
            # 2. Fetch Prices
            prices = {}
            for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PAXG/USDT']:
                tik = self.exchange.fetch_ticker(sym)
                prices[sym.split('/')[0]] = tik['last']
            
            # 3. Calculate Portfolio Value
            total_usdt = self.state['balance_usdt']
            for asset, amt in self.state['holdings'].items():
                total_usdt += amt * prices.get(asset, 0)
            
            logger.info(f"Sim Portfolio Val: {total_usdt:.2f} USDT")
            
            # 4. Rebalance (Simulated)
            target_weights = self.MODES[mode]
            
            new_holdings = self.state['holdings'].copy()
            new_cash = total_usdt
            
            # Sell Everything logic first? Or smart rebal?
            # Simplest: Sell all to cash, buy targets. (Frictionless sim)
            # Real rebal: Diff.
            
            # Let's do Diff rebalance to check minimums
            
            # Target Values
            targets = {k: total_usdt * w for k, w in target_weights.items() if k != 'STABLE'}
            
            # Execute Sells
            for asset, amt in self.state['holdings'].items():
                current_val = amt * prices.get(asset, 0)
                target_val = targets.get(asset, 0)
                
                if current_val > target_val:
                    sell_val = current_val - target_val
                    if sell_val > 5: # Threshold
                        sell_amt = sell_val / prices[asset]
                        new_holdings[asset] -= sell_amt
                        self.state['balance_usdt'] += sell_val # Cash in
                        logger.info(f"SIM SELL {asset}: {sell_amt:.4f} (~{sell_val:.2f} USDT)")
            
            # Execute Buys
            current_cash = self.state['balance_usdt'] # Updated after sells
            
            # Recalc targets based on actual Total (slightly different due to price moves?) No, Total is invariant here ignoring fees.
            
            for asset, target_val in targets.items():
                current_amt = new_holdings.get(asset, 0)
                current_val = current_amt * prices.get(asset, 0)
                
                if current_val < target_val:
                    buy_val = target_val - current_val
                    # Cap by available cash
                    if buy_val > self.state['balance_usdt']: buy_val = self.state['balance_usdt']
                    
                    if buy_val > 5:
                        buy_amt = buy_val / prices[asset]
                        new_holdings[asset] += buy_amt
                        self.state['balance_usdt'] -= buy_val
                        logger.info(f"SIM BUY {asset}: {buy_amt:.4f} (~{buy_val:.2f} USDT)")
            
            self.state['holdings'] = new_holdings
            self.save_state()
            
        except Exception as e:
            logger.error(f"Five Cubes Sim Failed: {e}")

    def get_status(self):
        return {
            "name": "Binance 5 Cubes (Sim)",
            "balance_usdt": self.state.get('balance_usdt', 0),
            "holdings": self.state.get('holdings', {}),
            "mode": "Unknown" # Ideally cache last mode
        }

