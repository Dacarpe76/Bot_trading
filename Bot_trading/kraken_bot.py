import ccxt
import pandas as pd
import ta
import time
import logging
from datetime import datetime
import config
import database
import telegram_bot

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class KrakenBot:
    def __init__(self, mode='test_1', strategy='standard'):
        """
        mode: 'real', 'test_1' (standard sim), 'test_2' (instant sim)
        strategy: 'standard' (MACD/EMA), 'instant' (aggressive entry)
        """
        self.mode = mode
        self.strategy = strategy
        self.simulation_mode = (mode != 'real')
        
        self.kraken = ccxt.kraken({
            'apiKey': config.KRAKEN_API_KEY,
            'secret': config.KRAKEN_PRIVATE_KEY,
        })
        self.symbols = ['BTC/EUR', 'PAXG/EUR'] 
        self.timeframe = '4h' 
        
    def fetch_data(self, symbol, limit=300):
        """Fetches OHLCV data from Kraken."""
        try:
            ohlcv = self.kraken.fetch_ohlcv(symbol, self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logging.error(f"Error fetching data for {symbol}: {e}")
            return None

    def calculate_indicators(self, df):
        """Calculates MACD (8,17,9), EMA 200, and ATR 14."""
        # MACD (Fast 8, Slow 17, Signal 9)
        macd = ta.trend.MACD(close=df['close'], window_slow=17, window_fast=8, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()

        # EMA 200
        df['ema_200'] = ta.trend.EMAIndicator(close=df['close'], window=200).ema_indicator()

        # ATR 14
        df['atr'] = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        
        return df

    def get_market_price(self, symbol):
        """Fetches current market price."""
        try:
            ticker = self.kraken.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            # Fallback for PAXG if EUR not found (common issue)
            if symbol == 'PAXG/EUR':
                 try:
                     ticker = self.kraken.fetch_ticker('PAXG/USD')
                     return ticker['last']
                 except:
                     pass
            logging.error(f"Error fetching price for {symbol}: {e}")
            return None

    def calculate_position_size(self, capital, atr, price):
        """
        Calculates position size based on ATR for volatility normalization.
        """
        risk_per_trade = capital * 0.01
        stop_distance = 2 * atr
        if stop_distance == 0: return 0
        amount = risk_per_trade / stop_distance
        return amount

    def check_signals(self, df, symbol):
        """Analyzes dataframe for entry/exit signals."""
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        signal = None
        reason = ""

        # STRATEGY 2: INSTANT ENTRY (TEST 2)
        if self.strategy == 'instant':
            # Check if we already have an open trade for this symbol in this mode?
            # For simplicity in this logic block, simply return BUY always if uptrend (or just BUY).
            # To avoid spamming, the caller or DB check should prevent duplicate positions.
            # Let's say: Buy if price > EMA 200 to keep some sanity, but otherwise aggressive.
            signal = 'buy'
            reason = "TEST 2: Instant Entry Mode"
            return signal, reason

        # STRATEGY 1: STANDARD (REAL / TEST 1)
        # Trend Filter: Price > EMA 200
        is_uptrend = last_row['close'] > last_row['ema_200']
        
        if symbol == 'BTC/EUR':
            # MACD Entry: Crossover above signal line + Uptrend
            macd_cross_up = (prev_row['macd'] < prev_row['macd_signal']) and (last_row['macd'] > last_row['macd_signal'])
            
            if is_uptrend and macd_cross_up:
                signal = 'buy'
                reason = "MACD Cross Up + Price > EMA200"
        
        elif symbol == 'PAXG/EUR':
             if is_uptrend and last_row['close'] < last_row['ema_200'] * 1.01: # Near EMA support
                signal = 'buy'
                reason = "Trend pullback (SMC Support Test)"

        return signal, reason

    def execute_trade(self, symbol, side, amount, price, reason):
        """Executes or simulates a trade."""
        cost = amount * price
        
        if self.simulation_mode:
            logging.info(f"[{self.mode.upper()}] SIMULATION: {side.upper()} {amount} {symbol} at {price} EUR. Reason: {reason}")
            database.log_trade(symbol, side, price, amount, cost, trade_type='simulated', status='open', execution_mode=self.mode)
            # Notify Telegram
            telegram_bot.send_message(f"🧪 *{self.mode.upper()} - {side.upper()}*\n{symbol}\nPrecio: {price} €\nCantidad: {amount}\nMotivo: {reason}")
        else:
            # Real execution (Future implementation)
            logging.info(f"[REAL] TRADE: {side.upper()} {amount} {symbol} at {price}")
            # ... ccxt create_order ...

    def run_analysis(self):
        """Main analysis loop for one cycle."""
        print(f"Running analysis cycle at {datetime.now()}")
        
        for symbol in self.symbols:
            df = self.fetch_data(symbol)
            if df is not None:
                df = self.calculate_indicators(df)
                signal, reason = self.check_signals(df, symbol)
                
                if signal == 'buy':
                    price = self.get_market_price(symbol)
                    
                    # Determine Available Capital
                    if self.simulation_mode:
                        available_eur = database.get_simulated_balance(self.mode, initial_capital=500.0)
                    else:
                        # Real mode: ccxt handles this usually, or we verify fetch_balance
                        available_eur = self.get_real_euro_balance() # We need a helper for this specific check if manual

                    # Basic Position Sizing (Risk Based)
                    atr = df.iloc[-1]['atr']
                    amount = self.calculate_position_size(available_eur, atr, price) # Base sizing on remaining capital? Or Fixed Initial?
                    # Specs: "Capital: 500 initial + 50 monthly". Usually sizing is based on Account Equity.
                    # Let's use available_eur for safety so we never spend what we don't have.
                    
                    # REALISTIC CHECK: Cap amount to available cash
                    cost = amount * price
                    if cost > available_eur:
                        logging.warning(f"[{self.mode}] Insufficient funds for calculated size. Adjusting...")
                        # Max affordable amount
                        amount = (available_eur * 0.99) / price # Leave 1% buffer for fees
                        cost = amount * price
                    
                    if amount > 0 and cost > 10.0: # Minimum trade size ~10 eur to avoid dust
                        self.execute_trade(symbol, 'buy', amount, price, reason)
                    else:
                        logging.info(f"[{self.mode}] Trade skipped. amount: {amount}, cost: {cost}, available: {available_eur}")

    def get_real_euro_balance(self):
        try:
             bal = self.kraken.fetch_balance()
             return bal['total'].get('EUR', 0.0)
        except:
            return 0.0

    def get_portfolio_breakdown(self):
        """Returns a dict with value in EUR for: BTC, PAXG, USDC, EUR."""
        breakdown = {'BTC': 0.0, 'PAXG': 0.0, 'USDC': 0.0, 'EUR': 0.0}
        
        if self.simulation_mode:
            # 1. Cash (EUR)
            breakdown['EUR'] = database.get_simulated_balance(self.mode, initial_capital=500.0)
            
            # 2. Positions (BTC, PAXG)
            positions = database.get_open_positions_amounts(self.mode)
            for symbol, amount in positions.items():
                current_price = self.get_market_price(symbol)
                if not current_price: continue
                
                value = amount * current_price
                
                if 'BTC' in symbol: breakdown['BTC'] += value
                elif 'PAXG' in symbol: breakdown['PAXG'] += value
                # Sim doesn't trade USDC, stays 0
                
        else: # REAL MODE
            try:
                bal = self.kraken.fetch_balance()['total']
                
                # EUR Cash
                breakdown['EUR'] = bal.get('EUR', 0.0)
                breakdown['USDC'] = bal.get('USDC', 0.0) # Assuming USDC exists or 1:1 if needed
                
                # Crypto Assets (Convert to EUR)
                # BTC
                btc_amount = bal.get('XXBT', 0.0) + bal.get('BTC', 0.0)
                if btc_amount > 0:
                    price = self.get_market_price('BTC/EUR')
                    breakdown['BTC'] = btc_amount * price if price else 0
                
                # PAXG
                paxg_amount = bal.get('PAXG', 0.0)
                if paxg_amount > 0:
                    price = self.get_market_price('PAXG/EUR')
                    breakdown['PAXG'] = paxg_amount * price if price else 0
                    
                # USDC Value in EUR?
                # If USDC balance > 0, we might want to convert its value to EUR for total sum, 
                # but user asked for "USDC: Saldo en euros". 
                # Usually means "Show me how much my USDC is worth in EUR".
                if breakdown['USDC'] > 0:
                    # Fetch USDC/EUR rate (inverse of EUR/USDC)
                    # or just estimate 0.95
                    try:
                        ticker = self.kraken.fetch_ticker('USDC/EUR')
                        price = ticker['last']
                    except:
                        price = 0.95 # Fallback
                    breakdown['USDC'] = breakdown['USDC'] * price
                    
            except Exception as e:
                logging.error(f"Error fetching real breakdown: {e}")
        
        return breakdown
