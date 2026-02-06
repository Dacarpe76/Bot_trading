import ccxt
import pandas as pd
import ta
import time
from datetime import datetime, timedelta
import config
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

class BufferedBacktester:
    def __init__(self, strategy, initial_capital=500.0):
        self.kraken = ccxt.kraken({
            'apiKey': config.KRAKEN_API_KEY,
            'secret': config.KRAKEN_PRIVATE_KEY,
        })
        self.symbols = ['BTC/EUR', 'PAXG/EUR']
        self.timeframe = '4h'
        self.initial_capital = initial_capital
        
        self.balance = initial_capital
        self.positions = {s: 0.0 for s in self.symbols}
        
        # Buffer: symbol -> DataFrame
        self.data_buffer = {s: pd.DataFrame() for s in self.symbols}
        # Last fetched timestamp per symbol
        self.last_fetched = {s: 0 for s in self.symbols}
        
        # History for indicators (accumulated)
        self.history = {s: pd.DataFrame() for s in self.symbols}
        
        self.strategy = strategy
        self.trade_log = []
        self.daily_equity = []

    def ensure_data_for_date(self, symbol, current_date):
        """No-op for YFinance version, as we fetch all initially."""
        pass
            
    def fetch_full_history(self, start_date):
        """Fetches full history from YFinance since start_date."""
        import yfinance as yf
        
        # Mapping for YF
        mapping = {
            'BTC/EUR': 'BTC-EUR',
            'PAXG/EUR': 'PAXG-EUR'
        }
        
        for s in self.symbols:
            ticker = mapping.get(s, s)
            print(f"📥 Downloading {s} ({ticker}) from Yahoo Finance...")
            
            # Download since start_date until now
            # interval='1d' is safest for long history.
            try:
                df = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), interval="1d", progress=False)
            except Exception as e:
                print(f"⚠️  Error downloading {ticker}: {e}")
                df = pd.DataFrame()
            
            # Fallback for PAXG-EUR if empty
            if df.empty and s == 'PAXG/EUR' and ticker == 'PAXG-EUR':
                print("⚠️  PAXG-EUR failed. Attempting PAXG-USD + EUR=X conversion...")
                try:
                    df_usd = yf.download('PAXG-USD', start=start_date.strftime("%Y-%m-%d"), interval="1d", progress=False)
                    df_eurx = yf.download('EUR=X', start=start_date.strftime("%Y-%m-%d"), interval="1d", progress=False)
                    
                    if not df_usd.empty and not df_eurx.empty:
                        # Flatten columns if MultiIndex
                        for d in [df_usd, df_eurx]:
                             if isinstance(d.columns, pd.MultiIndex):
                                 d.columns = d.columns.droplevel(1)
                        
                        # Forward fill FX data (for weekends/holidays)
                        # Reindex EURX to USD index to match crypto days
                        df_eurx = df_eurx.reindex(df_usd.index, method='ffill')
                        
                        # Calculate EUR price
                        # We use 'Close' for all fields to approximate
                        # ideally we'd do open*open_rate, etc. but 'Close' rate is acceptable proxy for simple backtest
                        rate = df_eurx['Close']
                        
                        df = df_usd.copy()
                        df['Open'] = df['Open'] * rate
                        df['High'] = df['High'] * rate
                        df['Low'] = df['Low'] * rate
                        df['Close'] = df['Close'] * rate
                        
                        # Synthesized OK
                        print("   ✅ Synthesized PAXG/EUR from USD data.")
                except Exception as e:
                    print(f"   ❌ Fallback failed: {e}")

            if df.empty:
                print(f"⚠️  No data found for {s}!")
                continue
                
            # Normalize columns
            # Yfinance > 0.2 returns MultiIndex (Price, Ticker). We need to flatten.
            if isinstance(df.columns, pd.MultiIndex):
                # We only want the level 0 (Price type) if we are downloading single ticker
                # Or just drop the ticker level
                df.columns = df.columns.droplevel(1)
            
            df.reset_index(inplace=True)
            df.columns = [c.lower() for c in df.columns] 
            # YF columns: Date, Open, High, Low, Close, Adj Close, Volume
            # Rename 'date' -> 'timestamp'
            if 'date' in df.columns:
                 df.rename(columns={'date': 'timestamp'}, inplace=True)
            
            # Ensure timestamp is datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            self.data_buffer[s] = df
            self.history[s] = pd.DataFrame() # Start empty
            
            print(f"   ✅ Loaded {len(df)} candles.")

    def fetch_latest_data(self, days=5):
        """Fetches only the last few days to check for new candles (Live Mode)."""
        import yfinance as yf
        
        # Mapping for YF
        mapping = {
            'BTC/EUR': 'BTC-EUR',
            'PAXG/EUR': 'PAXG-EUR'
        }
        
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        for s in self.symbols:
            ticker = mapping.get(s, s)
            try:
                # interval='1d' is standard for this bot
                df = yf.download(ticker, start=start_date, interval="1d", progress=False)
            except Exception:
                df = pd.DataFrame()

            # ... (Reuse Fallback Logic for PAXG if needed, simplified here for "latest") ... 
            # In live mode, fallback usually less critical if we assume history loaded, 
            # but to be safe we skip complex fallback for now to keep it fast, 
            # or copy strictly if critical. Let's assume standard symbols work for now 
            # or user accepts minor gap if PAXG API fails momentarily.
            
            if df.empty: continue
            
            # Normalize
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            
            df.reset_index(inplace=True)
            df.columns = [c.lower() for c in df.columns] 
            if 'date' in df.columns: df.rename(columns={'date': 'timestamp'}, inplace=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            self.data_buffer[s] = df # In this simple design, buffer is "what we look at for today". 
            # CAUTION: If we overwrite data_buffer with just 5 days, 'get_candles_for_day' works fine for TODAY,
            # but we lose history? 
            # Actually run_simulation uses data_buffer solely to extract *that specific day*.
            # The 'history' dict holds the accumulated truth.
            # So overwriting data_buffer with fresh small chunk is fine for 'update_live'.


    def get_candles_for_day(self, symbol, date_obj):
        """Returns 4h candles belonging to this specific day from buffer."""
        self.ensure_data_for_date(symbol, date_obj)
        
        df = self.data_buffer[symbol]
        if df.empty: return pd.DataFrame()
        
        # Filter strictly for this day definition
        # Start: 00:00:00, End: 23:59:59
        day_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        mask = (df['timestamp'] >= day_start) & (df['timestamp'] < day_end)
        return df.loc[mask]

    def run_simulation(self, start_date_str, quiet=False):
        if hasattr(self, 'strategy_name'):
            print(f"--- Running Strategy: {self.strategy_name} ---")
            
        start_dt = datetime.strptime(start_date_str, "%d/%m/%Y")
        
        # Warmup Phase (40 days back)
        warmup_start = start_dt - timedelta(days=40)
        if not quiet:
            print(f"🔥 Warming up (Since {warmup_start.strftime('%d/%m/%Y')})...")
        
        # We manually fetch the warmup chunk
        self.fetch_full_history(warmup_start)
             
        if not quiet:
            print("✅ Ready.\n")
        
        current_date = start_dt
        end_date = datetime.now() # current time
        
        while current_date < end_date:
            if not quiet:
                print(f"📅 Día: {current_date.strftime('%d/%m/%Y')}", end="")

            activity = False
            for s in self.symbols:
                day_candles = self.get_candles_for_day(s, current_date)
                if not day_candles.empty:
                    activity = True
                    # Append to history
                    # Use concat instead of append
                    self.history[s] = pd.concat([self.history[s], day_candles]).drop_duplicates(subset='timestamp').sort_values('timestamp')
                    
            if not activity:
                if not quiet: print(" (Sin datos)")
                current_date += timedelta(days=1)
                continue
            
            if not quiet: print(" ✅")
            
            # Recalculate indicators
            self.update_indicators()
            
            # Check signals (on the just-added day candles)
            self.check_activity_for_day(current_date)
            
            # Record daily equity
            # Infer current prices from last history
            current_prices = {}
            for s in self.symbols:
                if s in self.history and not self.history[s].empty:
                    current_prices[s] = self.history[s].iloc[-1]['close']
                else:
                    current_prices[s] = 0.0
            
            total_equity = self.get_total_equity(current_prices)
            self.daily_equity.append({
                'date': current_date.strftime("%Y-%m-%d"),
                'equity': total_equity
            })
            
            current_date += timedelta(days=1)
            # time.sleep(0.001) # Faster
            
        return self.get_final_result()
            
    def update_indicators(self):
        for s in self.symbols:
            df = self.history[s]
            if df.empty or len(df) < 50: continue
            
            macd = ta.trend.MACD(close=df['close'], window_slow=17, window_fast=8, window_sign=9)
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['ema_200'] = ta.trend.EMAIndicator(close=df['close'], window=200).ema_indicator()
            df['atr'] = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
            df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
            
            # Bollinger Bands
            bb_indicator = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
            df['bb_high'] = bb_indicator.bollinger_hband()
            df['bb_low'] = bb_indicator.bollinger_lband()
            
            # ADX
            df['adx'] = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
            
            self.history[s] = df
            
    def check_activity_for_day(self, date_obj):
        # Scan the candles of this day
        day_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        for s in self.symbols:
            df = self.history[s]
            # Get only today's rows
            today_mask = (df['timestamp'] >= day_start) & (df['timestamp'] < day_end)
            today_rows = df.loc[today_mask]
            
            for i, row in today_rows.iterrows():
                self.check_signal(s, row)
                
    def check_signal(self, symbol, row):
        # Use strategy object
        signal, reason = self.strategy.check(symbol, row, position_size=self.positions[symbol])
        
        # Backward compatibility for boolean signals (True = Buy)
        if isinstance(signal, bool):
            if signal:
                self.execute_trade(symbol, row['close'], row['atr'], reason)
        elif isinstance(signal, str):
            signal = signal.lower()
            if signal == 'buy':
                self.execute_trade(symbol, row['close'], row['atr'], reason)
            elif signal == 'sell':
                self.execute_sell(symbol, row['close'], reason)
            elif signal == 'short':
                self.execute_short(symbol, row['close'], row['atr'], reason)
            elif signal == 'cover':
                self.execute_cover(symbol, row['close'], reason)

    def execute_sell(self, symbol, price, reason):
        amount = self.positions[symbol]
        if amount > 0:
            proceeds = amount * price
            self.balance += proceeds
            self.positions[symbol] = 0.0
            
            self.trade_log.append({
                'date': datetime.now(), 
                'symbol': symbol,
                'type': 'SELL',
                'price': price,
                'amount': amount,
                'cost': proceeds, 
                'balance_after': self.balance,
                'reason': reason
            })

    def execute_short(self, symbol, price, atr, reason):
        # Open a Short position (Sell borrowed asset)
        # We need to ensure we don't already have a position
        if self.positions[symbol] != 0: return # Simplify: only 1 direction at time
        
        risk = self.balance * 0.01
        if pd.isna(atr) or atr == 0: stop_dist = price * 0.05
        else: stop_dist = 2 * atr
            
        amount = risk / stop_dist
        proceeds = amount * price
        
        # Credit balance (selling borrowed asset)
        self.balance += proceeds
        self.positions[symbol] = -amount # Negative position
        
        self.trade_log.append({
            'date': datetime.now(), 
            'symbol': symbol,
            'type': 'SHORT',
            'price': price,
            'amount': amount,
            'cost': proceeds, 
            'balance_after': self.balance,
            'reason': reason
        })

    def execute_cover(self, symbol, price, reason):
        # Close Short position (Buy back)
        amount = self.positions[symbol]
        if amount < 0:
            qty_to_buy = abs(amount)
            cost = qty_to_buy * price
            
            self.balance -= cost
            self.positions[symbol] = 0.0
            
            self.trade_log.append({
                'date': datetime.now(), 
                'symbol': symbol,
                'type': 'COVER',
                'price': price,
                'amount': qty_to_buy,
                'cost': cost, 
                'balance_after': self.balance,
                'reason': reason
            })

    def get_total_equity(self, current_prices):
        """Helper to calculate current total equity (Long + Short)."""
        equity = self.balance
        for s, amt in self.positions.items():
            if amt != 0:
                price = current_prices.get(s, 0.0)
                if price == 0 and s in self.history and not self.history[s].empty:
                     price = self.history[s].iloc[-1]['close']
                
                # If amt > 0 (Long): Equity += Amt * Price 
                # If amt < 0 (Short): Equity += (-Amt) * Price (Wait, this subtracts liability)
                # Correct: Equity += amt * price
                # Example Long: +1 * 50k = +50k
                # Example Short: -1 * 50k = -50k (Liability subtracts from Balance)
                equity += amt * price
        return equity
            
    def execute_trade(self, symbol, price, atr, reason):
        risk = self.balance * 0.01
        
        # If ATR is 0 or nan, use fallback 5%
        if pd.isna(atr) or atr == 0:
            stop_dist = price * 0.05
        else:
            stop_dist = 2 * atr
            
        amount = risk / stop_dist
        cost = amount * price
        
        if cost > self.balance:
            amount = (self.balance * 0.99) / price
            cost = amount * price
            
        if cost > 10:
            self.balance -= cost
            self.positions[symbol] += amount
            # print(f"   🚀 COMPRA {symbol}: {amount:.4f} @ {price:.2f} € | {reason}")
            self.trade_log.append({
                'date': datetime.now(), # In sim this should be step date, but good enough
                'symbol': symbol,
                'type': 'BUY',
                'price': price,
                'amount': amount,
                'cost': cost,
                'balance_after': self.balance,
                'reason': reason
            })
            
            

    def get_final_result(self):
        # Infer current prices from last history
        current_prices = {}
        for s in self.symbols:
            if s in self.history and not self.history[s].empty:
                current_prices[s] = self.history[s].iloc[-1]['close']
            else:
                current_prices[s] = 0.0
                
        equity = self.get_total_equity(current_prices)
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': equity,
            'pnl': equity - self.initial_capital,
            'pnl_percent': (equity - self.initial_capital) / self.initial_capital * 100,
            'trades': len(self.trade_log)
        }

    def update_live(self):
        """Checks for new data, updates indicators, and checks signals."""
        print(f"[{datetime.now().strftime('%H:%M')}] 📡 {self.strategy_name}: Checking for new data...")
        self.fetch_latest_data(days=3) # Get last 3 days
        
        updated = False
        today = datetime.now()
        
        # Check essentially "Yesterday" (finalized) and "Today" (in progress)
        # But our logic runs Day by Day.
        # If we are in live mode, we just want to verify if 'history' is missing the latest available candle.
        
        for s in self.symbols:
            df_recent = self.data_buffer[s]
            if df_recent.empty: continue
            
            last_recorded_ts = self.history[s]['timestamp'].max() if not self.history[s].empty else pd.Timestamp.min
            
            # Find new candles
            new_candles = df_recent[df_recent['timestamp'] > last_recorded_ts].copy()
            
            if not new_candles.empty:
                print(f"   ✨ New candles for {s}: {len(new_candles)}")
                self.history[s] = pd.concat([self.history[s], new_candles]).sort_values('timestamp')
                updated = True
        
        if updated:
            self.update_indicators()
            # Check signals ONLY on the LAST row (Latest data)
            # We treat the live check as "Checking the activity for today/now"
            self.check_activity_for_day(today)
            
            # Print status
            res = self.get_final_result()
            print(f"   📊 Updated Equity: {res['final_equity']:.2f} €")
        else:
            print("   💤 No new data.")

if __name__ == "__main__":
    # Test stub for direct run (legacy)
    from strategies import StandardStrategy
    try:
        date_input = input("Introduce fecha de inicio (dd/mm/aaaa): ")
        bt = BufferedBacktester(StandardStrategy())
        res = bt.run_simulation(date_input)
        print(res)
    except Exception as e:
        print(f"Error: {e}")

