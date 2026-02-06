
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

        # State Persistence
        self.state = {
            'equity': 0.0,
            'holdings': {},
            'regime': 'Unknown'
        }
        
        # Initial Fetch
        if self.exchange:
            try:
                self.refresh_status()
            except Exception as e:
                logger.error(f"Initial Kraken Fetch Failed: {e}")

    def refresh_status(self):
        """Fetches current balance without trading."""
        if not self.exchange: return
        
        try:
            bal = self.exchange.fetch_balance()
            
            # Fetch Prices (CCXT Normalized)
            # Kraken CCXT usually uses BTC/EUR, not XBT/EUR
            try:
                ticker_btc = self.exchange.fetch_ticker('BTC/EUR')
            except:
                ticker_btc = self.exchange.fetch_ticker('XBT/EUR')
                
            ticker_paxg = self.exchange.fetch_ticker('PAXG/EUR')
            
            price_btc = ticker_btc['last']
            price_paxg = ticker_paxg['last']
            
            # Normalize Keys: CCXT common vs Raw
            # Debug showed: 'BTC', 'PAXG', 'EUR' are present directly in 'total'
            total = bal['total']
            
            holdings = {
                'BTC': total.get('BTC', total.get('XXBT', 0.0)),
                'GOLD': total.get('PAXG', total.get('XDG', 0.0)),
                'EUR': total.get('EUR', total.get('ZEUR', 0.0))
            }
            
            # Calc Total Equity
            equity = holdings['EUR'] + (holdings['BTC'] * price_btc) + (holdings['GOLD'] * price_paxg)
            
            self.state['equity'] = equity
            self.state['holdings'] = holdings
            self.state['prices'] = {'BTC': price_btc, 'GOLD': price_paxg, 'EUR': 1.0}
            logger.info(f"Kraken Status Refreshed: {equity:.2f} EUR")
            
        except Exception as e:
            logger.error(f"Refresh Status Failed: {e}")

    def run(self):
        """Executed daily to update strategy state."""
        logger.info(">>> Running Kraken Real Macro Strategy <<<")
        
        # 1. Update Real Balance & Price
        self.refresh_status()
        
        # 2. Determine Regime (Simple Logic for Now)
        # In a real bot, we would fetch indicators here (like Sim Strategy)
        # For now, we just identify regime based on holdings
        h = self.state['holdings']
        if h['BTC'] > 0.1: # Example threshold
             self.state['regime'] = 'NET_LONG'
        else:
             self.state['regime'] = 'DEFENSIVE'

    def get_status(self):
        """Returns current status for GUI."""
        status = {
            "name": "Kraken Real Macro",
            "active": self.exchange is not None,
            "equity": self.state['equity'],
            "holdings": self.state['holdings'],
            "prices": self.state.get('prices', {}),
            "regime": self.state['regime']
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
        self.current_prices = {}
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
            mode = "SHIELD"
            if inds['fng'] < 20: mode = "ATTACK"
            elif inds['dxy'] < 101 and inds['pmi'] > 50: mode = "CRUISE"
            
            logger.info(f"5 Cubes Mode: {mode} (F&G={inds['fng']}, DXY={inds['dxy']:.1f})")
            
            # 2. Fetch Prices
            prices = {}
            for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PAXG/USDT']:
                tik = self.exchange.fetch_ticker(sym)
                prices[sym.split('/')[0]] = tik['last']
            
            self.current_prices = prices # Update current prices

            # 3. Calculate Portfolio Value
            total_usdt = self.state['balance_usdt']
            for asset, amt in self.state['holdings'].items():
                total_usdt += amt * prices.get(asset, 0)
            
            logger.info(f"Sim Portfolio Val: {total_usdt:.2f} USDT")
            
            # 4. Rebalance (Simulated)
            target_weights = self.MODES[mode]
            
            new_holdings = self.state['holdings'].copy()
            new_cash = total_usdt
            
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
            "prices": self.current_prices,
            "mode": "Unknown" # Ideally cache last mode in state too, but ok
        }


class KrakenNewsStrategy:
    """
    Estrategia Evaluativa con Lectura de Noticias.
    Capital Simulado: 500 EUR.
    Logic: Buy BTC if Sentiment > 0.5, Sell if < -0.5.
    """
    STATE_FILE = "sim_wallet_news.json"
    
    def __init__(self):
        self.initial_capital_eur = 500.0
        self.current_prices = {}
        self.exchange = ccxt.kraken() # For price fetching
        
        # Initial Load or Reset
        if os.path.exists(self.STATE_FILE):
             try:
                 with open(self.STATE_FILE, 'r') as f:
                     self.state = json.load(f)
             except:
                 self.reset_state()
        else:
             self.reset_state()
             
    def reset_state(self):
        self.state = {
            'balance_eur': self.initial_capital_eur,
            'holdings': {'BTC': 0.0},
            'sentiment_history': [],
            'regime': 'NEUTRAL'
        }
        self.save_state()
        
    def save_state(self):
        with open(self.STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=4)
            
    def check_sentiment(self):
        """
        Placeholder for Real News Sentiment Analysis.
        Returns float between -1.0 (Bearish) and 1.0 (Bullish).
        """
        # TODO: Connect to News API (CryptoPanic/LunarCrush)
        # For now, simulate randomized sentiment for evaluation
        import random
        return random.uniform(-0.8, 0.8)
        
    def run(self):
        logger.info(">>> Running Kraken NEWS Strategy (Sim) <<<")
        try:
            # 1. Fetch Price
            ticker = self.exchange.fetch_ticker('BTC/EUR')
            price = ticker['last']
            self.current_prices = {'BTC': price}
            
            # 2. Check Sentiment
            sentiment = self.check_sentiment()
            self.state['sentiment_history'].append({
                'time': time.time(), 
                'score': sentiment
            })
            
            # Keep only last 10
            if len(self.state['sentiment_history']) > 10:
                self.state['sentiment_history'].pop(0)
                
            logger.info(f"News Sentiment Score: {sentiment:.2f}")
            
            # 3. Simplify Regime
            if sentiment > 0.3: self.state['regime'] = 'BULLISH'
            elif sentiment < -0.3: self.state['regime'] = 'BEARISH'
            else: self.state['regime'] = 'NEUTRAL'
            
            # 4. Trading Logic
            balance = self.state['balance_eur']
            btc_amt = self.state['holdings']['BTC']
            
            # BUY SIGNAL
            if sentiment > 0.4 and balance > 10:
                # Invest 50% of available cash
                invest_amt = balance * 0.5
                btc_bought = invest_amt / price
                
                self.state['balance_eur'] -= invest_amt
                self.state['holdings']['BTC'] += btc_bought
                logger.info(f"NEWS SIM BUY: {btc_bought:.6f} BTC @ {price:.2f}")
                
            # SELL SIGNAL
            elif sentiment < -0.4 and btc_amt * price > 10:
                # Sell 100%
                sell_val = btc_amt * price
                self.state['balance_eur'] += sell_val
                self.state['holdings']['BTC'] = 0.0
                logger.info(f"NEWS SIM SELL: {btc_amt:.6f} BTC @ {price:.2f}")
                
            self.save_state()
            
        except Exception as e:
            logger.error(f"News Strategy Failed: {e}")

    def get_status(self):
        # Calculate Equity
        btc_val = self.state['holdings']['BTC'] * self.current_prices.get('BTC', 0)
        equity = self.state['balance_eur'] + btc_val
        
        return {
            "name": "Kraken News (Sim)",
            "active": True,
            "equity": equity,
            "balance_usdt": equity, # Mapping for GUI
            "holdings": self.state['holdings'],
            "prices": self.current_prices,
            "regime": f"{self.state['regime']} (S={self.state['sentiment_history'][-1]['score']:.2f})" if self.state['sentiment_history'] else "WAITING"
        }
