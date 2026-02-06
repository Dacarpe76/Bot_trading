
import pandas as pd

class Strategy:
    def check(self, symbol, row, position_size=0):
        """
        Returns (bool, str) -> (signal, reason)
        """
        raise NotImplementedError

class StandardStrategy(Strategy):
    def check(self, symbol, row, position_size=0):
        # Existing logic from backtest.py / kraken_bot.py (Test 1 / Real)
        
        # Guard clauses
        if 'ema_200' not in row or 'macd' not in row: return False, ""
        if pd.isna(row['ema_200']) or pd.isna(row['macd']): return False, ""
        
        # Only buy if we don't have a position (Backtester logic)
        # In real bot we might add to position, but for simple backtest we hold 1 chunk.
        if position_size > 0: return False, ""
        
        signal = False
        reason = ""
        
        if symbol == 'BTC/EUR':
            # Buy if Price > EMA200 AND MACD > Signal
            if row['close'] > row['ema_200'] and row['macd'] > row['macd_signal']:
                signal = True
                reason = "MACD Cross + Trend"
        
        elif symbol == 'PAXG/EUR':
             # Buy Dip: Price > EMA200 AND Price near EMA
             if row['close'] > row['ema_200'] and row['close'] < row['ema_200'] * 1.01:
                 signal = True
                 reason = "Dip to Support"
                 
        return signal, reason

class InstantStrategy(Strategy):
    def check(self, symbol, row, position_size=0):
        # Simpler aggressive logic (Test 2)
        
        if 'ema_200' not in row: return False, ""
        if pd.isna(row['ema_200']): return False, ""
        
        if position_size > 0: return False, ""

        signal = False
        reason = ""
        
        # Buy if price > EMA 200 (Simple Trend Following)
        # This is "Instant" because it enters as soon as trend is established/recovered
        if row['close'] > row['ema_200']:
            signal = True
            reason = "Price > EMA200 (Instant)"
            
        return signal, reason

class InstantV2Strategy(Strategy):
    def __init__(self):
        self.rolling_max = {} # symbol -> max_price

    def check(self, symbol, row, position_size=0):
        # Enhanced Instant Strategy (Test 3)
        # Entry: Price > EMA 200
        # Exit: Price < EMA 200 * 0.98 OR Price < Rolling Max * 0.85 (Trailing Stop)
        
        if 'ema_200' not in row or pd.isna(row['ema_200']): return False, ""
        
        current_price = row['close']
        
        # Trailing Stop Logic
        if symbol not in self.rolling_max:
            self.rolling_max[symbol] = current_price
        
        if position_size > 0:
            # Update peak if holding
            if current_price > self.rolling_max[symbol]:
                self.rolling_max[symbol] = current_price
        else:
            # Reset peak if not holding
            self.rolling_max[symbol] = current_price

        # Default action
        action = False
        reason = ""

        if position_size == 0:
            # ENTRY LOGIC
            if current_price > row['ema_200']:
                action = 'buy'
                reason = "Price > EMA200 (Entry)"
        else:
            # EXIT LOGIC
            # 1. Trend Break (with buffer)
            if current_price < (row['ema_200'] * 0.98):
                action = 'sell'
                reason = "Trend Break (< EMA200)"
            
            # 2. Trailing Stop (10%)
            elif current_price < (self.rolling_max[symbol] * 0.90):
                action = 'sell'
                reason = "Trailing Stop (-10%)"

        return action, reason

class InstantV3Strategy(Strategy):
    def __init__(self):
        self.rolling_max = {} # symbol -> max_price

    def check(self, symbol, row, position_size=0):
        # Instant V3: Smart Peak Exit
        # Entry: Price > EMA 200
        # Exit 1 (Smart Peak): RSI > 70 AND MACD Cross Down (Signal > MACD)
        # Exit 2 (Trend Break): Price < EMA 200 * 0.98
        # Exit 3 (Safety Net): Trailing Stop 10%
        
        if 'ema_200' not in row or pd.isna(row['ema_200']): return False, ""
        if 'rsi' not in row or pd.isna(row['rsi']): return False, ""
        if 'macd' not in row: return False, ""
        
        current_price = row['close']
        
        # Trailing Stop Logic (Safety Net)
        if symbol not in self.rolling_max:
            self.rolling_max[symbol] = current_price
        
        if position_size > 0:
            if current_price > self.rolling_max[symbol]:
                self.rolling_max[symbol] = current_price
        else:
            self.rolling_max[symbol] = current_price

        action = False
        reason = ""

        if position_size == 0:
            # ENTRY (Agresiva)
            if current_price > row['ema_200']:
                action = 'buy'
                reason = "Price > EMA200 (Entry)"
        else:
            # EXIT LOGIC
            
            # 1. SMART PEAK EXIT (Tomar ganancias arriba)
            # Si RSI indica sobrecompra y el MACD pierde fuerza... salimos.
            if row['rsi'] > 70 and row['macd'] < row['macd_signal']:
                action = 'sell'
                reason = f"Smart Exit (RSI {row['rsi']:.0f} + MACD Drop)"

            # 2. Trend Break
            elif current_price < (row['ema_200'] * 0.98):
                action = 'sell'
                reason = "Trend Break (< EMA200)"
            
            # 3. Safety Net (Trailing Stop 10%)
            elif current_price < (self.rolling_max[symbol] * 0.90):
                action = 'sell'
                reason = "Safety Net (-10%)"

        return action, reason

class InstantV4Strategy(Strategy):
    def check(self, symbol, row, position_size=0):
        # Instant V4: Long/Short + Smart Top Exit
        # 1. Long Criteria: Price > EMA 200
        # 2. Short Criteria: Price < EMA 200
        # 3. Smart Top Exit: RSI > 75 + Price > BB High (Sell Longs early)
        
        required = ['ema_200', 'rsi', 'bb_high']
        for col in required:
            if col not in row or pd.isna(row[col]): return False, ""
        
        current_price = row['close']
        action = False
        reason = ""

        if position_size == 0:
            # NO POSITION -> Check for Entry
            if current_price > row['ema_200']:
                action = 'buy'
                reason = "Bull Trend (> EMA200)"
            elif current_price < row['ema_200']:
                action = 'short'
                reason = "Bear Trend (< EMA200)"
                
        elif position_size > 0:
            # HOLDING LONG -> Check for Exit
            
            # 1. Smart Top Take Profit (Euforia)
            if row['rsi'] > 75 and current_price > row['bb_high']:
                action = 'sell'
                reason = "Smart Top TP (RSI>75 + BB)"
                
            # 2. Trend Reversal
            elif current_price < row['ema_200']:
                action = 'sell'
                reason = "Trend Reversal (< EMA200)"
                
        elif position_size < 0:
            # HOLDING SHORT -> Check for Cover
            
            # 1. Trend Reversal
            if current_price > row['ema_200']:
                action = 'cover'
                reason = "Trend Reversal (> EMA200)"

        return action, reason
