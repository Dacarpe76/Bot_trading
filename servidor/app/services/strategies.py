import pandas as pd
import ta
import logging

class BaseStrategy:
    def __init__(self, name, allowed_sides=['LONG']):
        self.name = name
        self.allowed_sides = allowed_sides
        self.params = {}

    def analyze(self, df: pd.DataFrame):
        if len(df) < 20: return {}
        # Common Indicators
        close = df['close']
        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        
        # Green Candle
        last = df.iloc[-1]
        is_green = last['close'] > last['open']
        
        # Volatility
        atr = ta.volatility.AverageTrueRange(df['high'], df['low'], close, window=14).average_true_range().iloc[-1]
        
        return {
            'price': last['close'],
            'rsi': rsi,
            'is_green': is_green,
            'atr': atr,
            'timestamp': last['timestamp']
        }

    def check_signal(self, symbol, indicators, position=None):
        return ('HOLD', 0, 0)

# --- 1. Rolling DCA (Peace of Mind) ---
class StrategyRollingDCA(BaseStrategy):
    def __init__(self):
        super().__init__("RollingDCA")
        self.dca_steps = [
            {'drop': 0.015, 'mult': 1.5},
            {'drop': 0.030, 'mult': 2.0},
            {'drop': 0.050, 'mult': 3.0}
        ]
        self.params = {'rsi_entry': 40.0, 'tp_pct': 0.012}

    def check_signal(self, symbol, inds, pos):
        price = inds['price']
        if pos is None:
            if inds['rsi'] < self.params['rsi_entry'] and inds['is_green']:
                return ('OPEN', 1.0, price)
            return ('HOLD', 0, 0)
        
        # Manage
        if price >= pos.avg_price * (1 + self.params['tp_pct']):
            return ('CLOSE', 0, price)
            
        # DCA
        step = pos.dca_step
        if step < len(self.dca_steps):
            cfg = self.dca_steps[step]
            trigger = pos.avg_price * (1 - cfg['drop'])
            if price <= trigger:
                return ('DCA', cfg['mult'], price)
                
        return ('HOLD', 0, 0)

# --- 2. Aggressive (Scalper) ---
class StrategyAggressive(BaseStrategy):
    def __init__(self, sides=['LONG']):
        super().__init__("Aggressive", sides)
        self.params = {'tp': 0.003, 'sl': 0.003, 'rsi_L': 30, 'rsi_S': 70}

    def check_signal(self, symbol, inds, pos):
        price = inds['price']
        rsi = inds['rsi']
        
        if pos is None:
            if 'LONG' in self.allowed_sides and rsi < self.params['rsi_L']:
                return ('OPEN', 1.0, price)
            # Short logic placeholder
            return ('HOLD', 0, 0)
            
        # Manage
        avg = position.avg_price
        pct_diff = (price - avg) / avg
        
        if pct_diff >= self.params['tp']: return ('CLOSE', 0, price)
        if pct_diff <= -self.params['sl']: return ('CLOSE', 0, price)
        return ('HOLD', 0, 0)

# --- 3. NetScalp (DCA + Net PnL) ---
class StrategyNetScalp(BaseStrategy):
    def __init__(self):
        super().__init__("NetScalp")
        self.params = {'rsi_entry': 30, 'tp_usd': 0.05, 'dca_dist': 0.02}
        self.dca_mults = [1.5, 2.0, 3.0] # Simulating martingale

    def check_signal(self, symbol, inds, pos):
        price = inds['price']
        if pos is None:
            if inds['rsi'] < self.params['rsi_entry']:
                return ('OPEN', 1.0, price)
            return ('HOLD', 0, 0)
            
        # Manage (Net Profit in USDT approx)
        cost = pos.total_cost
        val = pos.total_size * price
        pnl_val = val - cost
        
        if pnl_val >= self.params['tp_usd']: 
            return ('CLOSE', 0, price)
            
        # DCA
        step = pos.dca_step
        if step < 3:
            trigger = pos.avg_price * (1 - (self.params['dca_dist'] * (step+1)))
            if price <= trigger:
                 return ('DCA', self.dca_mults[step], price)

        return ('HOLD', 0, 0)

# --- 4. Hybrid Elite (Context) ---
class StrategyHybridElite(BaseStrategy):
    def __init__(self):
        super().__init__("HybridElite")
        self.params = {'rsi_L': 30, 'rsi_S': 60}

    def check_signal(self, symbol, inds, pos):
        if pos is None:
            if inds['rsi'] < self.params['rsi_L'] and inds['is_green']:
                 return ('OPEN', 1.0, inds['price'])
            return ('HOLD', 0, 0)
        
        price = inds['price']
        if price >= pos.avg_price * 1.005:
            return ('CLOSE', 0, price)
        return ('HOLD', 0, 0)
        
# --- 5. Sniper Short (Momentum) ---
class StrategySniperShort(BaseStrategy):
    def __init__(self):
        super().__init__("SniperShort", ['SHORT'])
        self.params = {'rsi_entry': 75}

    def check_signal(self, symbol, inds, pos):
        price = inds['price']
        rsi = inds['rsi']
        is_green = inds['is_green']
        
        if pos is None:
            if rsi > self.params['rsi_entry'] and not is_green:
                # Trigger Short if possible, else ignored by Engine check
                return ('OPEN_SHORT', 1.0, price)
            return ('HOLD', 0, 0)
        
        # PnL Check for Short (Price Drop = Profit)
        pnl = (inds['price'] - pos.avg_price) / pos.avg_price * -1
        if pnl >= 0.015: return ('CLOSE', 0, price) 
        return ('HOLD', 0, 0)

# --- Factory ---
strategies = {
    "RollingDCA": StrategyRollingDCA(),
    "Aggressive": StrategyAggressive(sides=['LONG']),
    "Aggressive_S": StrategyAggressive(sides=['SHORT']),
    "NetScalp": StrategyNetScalp(),
    "HybridElite": StrategyHybridElite(),
    "SniperShort": StrategySniperShort()
}

# Default Active strategy object
strategy = strategies["RollingDCA"]
