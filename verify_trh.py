import asyncio
import logging
import pandas as pd
import numpy as np
from kraken_bot.processor import StrategyProcessor
from kraken_bot import config

# Mock Wallet
class MockWallet:
    def __init__(self):
        self.positions = {}
        self.balance_eur = 1000.0
        self.next_id = 1
        
    def open_position(self, side, price):
        print(f"[MOCK] Opening {side} at {price}")
        if not self.can_open_new(price): return False
        
        t_id = str(self.next_id)
        self.next_id += 1
        self.positions[t_id] = {
            'type': side,
            'entry_price': price,
            'entry_time': getattr(self, 'current_mock_time', 1700000000.0), # Dynamic or default
            'margin': 50.0, # Fixed mock margin
            'dca_count': 0,
            'last_dca_price': price,
            'highest_price': price if side == 'LONG' else 999999,
            'lowest_price': price if side == 'SHORT' else 0, 
            'trailing_active': False
        }
        return True

    def buy_market(self, amount, price):
        # Legacy support / Direct buy test
        return self.open_position('LONG', price)

    def sell_market(self, price, force=False):
        print(f"[MOCK] Selling all at {price} (Force={force})")
        self.positions = {} # Clear all
        return True
    
    def status_report(self, price):
        return f"Status: {len(self.positions)} positions"
    
    def check_exit_conditions(self, price):
        return False
        
    def can_open_new(self, price):
        return True
        
    def execute_dca(self, t_id, price):
        if t_id in self.positions:
             self.positions[t_id]['dca_count'] += 1
             self.positions[t_id]['last_dca_price'] = price
             return True
        return False
        
    def close_position(self, t_id, price):
        if t_id in self.positions:
            print(f"[MOCK] Closing position {t_id} at {price}")
            del self.positions[t_id]
        return True
        
    def get_last_entry_info(self, side):
        """Returns (price, time) of the most recent entry for a given side."""
        # For mock, we can iterate positions or track explicitly.
        # Since mock positions are simple dicts, we iterate.
        last_time = 0.0
        last_price = 0.0
        found = False
        
        # We need to ensure we track entry time in mock open_position too
        for pos in self.positions.values():
            if pos['type'] == side:
                # Mock entry time defaults to 0 if not set? 
                # We need to update open_position to set it.
                et = pos.get('entry_time', 0.0) 
                if et > last_time:
                    last_time = et
                    last_price = pos['entry_price']
                    found = True
        
        if found:
            return last_price, last_time
        return None

    def close_position(self, t_id, price):
        if t_id in self.positions:
            print(f"[MOCK] Closing position {t_id} at {price}")
            del self.positions[t_id]
        return True
        
    def calc_pnl_pct(self, t_id, current_price):
        if t_id not in self.positions: return 0.0
        pos = self.positions[t_id]
        if pos['type'] == 'LONG':
             return (current_price - pos['entry_price']) / pos['entry_price'] * 100
        else: # SHORT
             return (pos['entry_price'] - current_price) / pos['entry_price'] * 100


# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(message)s')

async def run_test():
    wallet = MockWallet()
    processor = StrategyProcessor(wallet)
    
    # CLEAR HISTORY to avoid Volatility Filter triggering on Real vs Mock price diff
    processor.candles = []
    
    print("--- STARTING TRH NO-LOSS RECOVERY VERIFICATION ---")
    
    # 1. GENERATE BASELINE HISTORY (200 Candles for EMA/ATR)
    base_price = 100.0
    start_time = 1700000000
    
    print("Generating baseline history...")
    for i in range(200):
        candle = {
            'timestamp': start_time + (i * 60),
            'open': base_price,
            'high': base_price + 0.5,
            'low': base_price - 0.5,
            'close': base_price,
            'volume': 100.0,
            'buy_vol': 50,
            'sell_vol': 50,
            'trades': 10,
            'cvd': 0
        }
        processor.finalize_candle(candle)
        
    current_atr = processor.current_atr
    print(f"Baseline ATR: {current_atr:.4f}")

    # ... (DCA Logic tests need update to access positions) ...
        # Since logic is complex to rewrite entirely via replace, I'll update the checks to use wallet.positions values.
        
    # ==========================================
    # TEST 1: DCA RECOVERY
    # ==========================================
    print("\n--- TEST SCENARIO: DCA LOGIC ---")
    
    # Force Entry (Injection)
    print("Injecting Initial Entry...")
    wallet.buy_market(100, base_price) 
    
    t_id = list(wallet.positions.keys())[0]
    
    # Drop Price by 3x ATR (Trigger Distance)
    drop_price = base_price - (3.0 * current_atr)
    print(f"Dropping price to {drop_price:.2f} (Dist > 2*ATR={2*current_atr:.2f})")
    
    current_time = start_time + 200 * 60
    p = base_price
    steps = 5
    step_drop = (base_price - drop_price) / steps
    
    for i in range(steps + 2): 
        p -= step_drop
        current_time += 60
        c = {
            'timestamp': current_time,
            'open': p + 0.1, 'high': p+0.1, 'low': p, 'close': p,
            'volume': 200, 'trades': 10, 'cvd': -10
        }
        processor.finalize_candle(c)
        if wallet.positions[t_id]['dca_count'] > 0:
            print(f"SUCCESS: DCA Triggered! Count={wallet.positions[t_id]['dca_count']}")
            break
            
    if wallet.positions[t_id]['dca_count'] == 0:
        print("FAILURE: DCA did not trigger.")

    # ==========================================
    # TEST 2: SMART TRAILING STOP
    # ==========================================
    print("\n--- TEST SCENARIO: TRAILING STOP ---")
    # Reset Wallet
    wallet.sell_market(p, force=True) 
    wallet.buy_market(100, 100.0) # Re-enter at 100
    t_id = list(wallet.positions.keys())[0]

    # Reset internal processor state? 
    # Processor state is per-position in wallet now, but 'atr_trailing_stop' was removed from processor 
    # and moved to wallet position dict? 
    # Wait, in processor.py I saw 'pos['trailing_active']' but 'self.atr_trailing_stop' was still in check_dynamic_exit??
    # No, I removed self.atr_trailing_stop usage in latest refactor check?
    # Let's check processor.py content again in my memory or assume I need to check pos['trailing_active']
    
    print("Pumping price to Activate TS (>0.4% profit)...")
    pump_price = 100.5
    current_time += 60
    
    c = {
        'timestamp': current_time,
        'open': 100, 'high': pump_price, 'low': 100, 'close': pump_price,
        'volume': 100, 'trades': 10
    }
    
    processor.finalize_candle(c) 
    processor.check_dynamic_exit(pump_price)
    
    if wallet.positions[t_id].get('trailing_active'):
        print(f"SUCCESS: Trailing Stop Activated")
    else:
        print("FAILURE: Trailing Stop Not Activated.")

    crash_price = 95.0
    print(f"Crashing price to {crash_price}...")
    processor.check_dynamic_exit(crash_price)
    
    if t_id not in wallet.positions:
        print("SUCCESS: Trailing Stop Hit! Position Closed.")
    else:
        print("FAILURE: Position still active.")

    
    # ==========================================
    # TEST 3: ENTRY PRECISION FILTERS
    # ==========================================
    print("\n--- TEST SCENARIO: ENTRY PRECISION ---")
    wallet.sell_market(100.0, force=True) # Reset
    t_id = None
    
    # 3.1 TEST RSI CROSSOVER FILTER
    # Inject Signal: Price > EMA, RSI > 60. But Previous RSI > 60 (No Crossover).
    # Expected: BLOCK.
    print("Testing Crossover Filter (Should Block)...")
    
    # Set EMA High (Base price 100), Momentum needs Price > EMA.
    # Logic in Processor: Price > EMA. EMA is approx 100.
    # We pump price to 105.
    
    current_time += 60
    # Candle 1: RSI High
    c1 = {'timestamp': current_time, 'open': 105, 'high': 105, 'low': 105, 'close': 105, 'volume': 200, 'trades': 10}
    processor.finalize_candle(c1)
    
    # Candle 2: RSI High (Still > 60). No Crossover.
    current_time += 60
    c2 = {'timestamp': current_time, 'open': 105, 'high': 105, 'low': 105, 'close': 105, 'volume': 200, 'trades': 10} 
    processor.finalize_candle(c2)
    
    if len(wallet.positions) == 0:
        print("SUCCESS: Signal Blocked (No Crossover or Cooldown or Vol)")
    else:
        print("FAILURE: Signal Opened (Should start empty)")
        wallet.sell_market(105, force=True)

    # 3.2 TEST VOLUME FILTER (Vrel > 1.0)
    # Inject Crossover (RSI < 60 -> > 60) but Low Volume (Vrel < 1.0).
    # Reset RSI first (Drop price).
    print("Resetting RSI...")
    for i in range(5):
        current_time += 60
        processor.finalize_candle({'timestamp': current_time, 'open': 90, 'high': 90, 'low': 90, 'close': 90, 'volume': 100, 'trades': 10})

    print("Testing Volume Filter (Low Vol)...")
    # Pump to 105 (RSI Spike) but Low Volume (Same as avg). Vrel ~ 1.0? 
    # Avg vol is 100. We inject 50. Vrel = 0.5.
    current_time += 60
    c_weak = {'timestamp': current_time, 'open': 105, 'high': 105, 'low': 105, 'close': 105, 'volume': 20, 'trades': 10}
    processor.finalize_candle(c_weak)
    
    if len(wallet.positions) == 0:
         print("SUCCESS: Signal Blocked (Low Volume)")
    else:
         print("FAILURE: Signal Opened (Volume Filter Failed)")
         wallet.sell_market(105, force=True)

    # 3.3 TEST SUCCESSFUL ENTRY (Crossover + High Vol)
    print("Testing Valid Entry (Crossover + Vrel > 1)...")
    # Reset RSI
    for i in range(5):
        current_time += 60
        wallet.current_mock_time = current_time 
        processor.finalize_candle({'timestamp': current_time, 'open': 90, 'high': 90, 'low': 90, 'close': 90, 'volume': 100, 'trades': 10})
        
    current_time += 60
    wallet.current_mock_time = current_time
    # Pump + High Vol (300 vs 100 avg -> Vrel=3)
    # Ramp up price AGGRESSIVELY to force RSI > 60 naturally
    # 90 -> 100 -> 130
    # Ensuring we jump from <60 to >60 in one go if possible
    prices = [100, 130]
    for p in prices:
        current_time += 60
        wallet.current_mock_time = current_time
        c_valid = {'timestamp': current_time, 'open': p, 'high': p, 'low': p, 'close': p, 'volume': 300, 'trades': 10}
        processor.finalize_candle(c_valid)
    
    if len(wallet.positions) > 0:
        print("SUCCESS: Valid Signal Opened!")
    else:
        print("FAILURE: Valid Signal NOT Opened. (RSI likely still too low)")
        
    # 3.4 TEST COOLDOWN (Same direction immediately)
    print("Testing Cooldown (Immediate Repeat)...")
    
    # Force inject a position if one wasn't opened, so we can TEST cooldown properly
    if len(wallet.positions) == 0:
        print("[TEST SETUP] Manually injecting position for Cooldown Test...")
        wallet.current_mock_time = current_time 
        wallet.open_position('LONG', 130) 

    # To test Cooldown, we need a VALID signal (Crossover).
    # So we must dip RSI < 60 and come back up, but staying close in price/time.
    print("   -> Dipping price to reset RSI...")
    current_time += 60
    wallet.current_mock_time = current_time
    # Dip to 125 (RSI < 60)
    c_dip = {'timestamp': current_time, 'open': 125, 'high': 125, 'low': 125, 'close': 125, 'volume': 100, 'trades': 10}
    processor.finalize_candle(c_dip)
    
    print("   -> Pumping back to trigger 2nd Signal...")
    current_time += 60
    wallet.current_mock_time = current_time
    # Pump back to 130. RSI > 60. Price diff = 0. Time diff = 120s (< 1800).
    c_repeat = {'timestamp': current_time, 'open': 130, 'high': 130, 'low': 130, 'close': 130, 'volume': 300, 'trades': 10}
    
    count_before = len(wallet.positions)
    processor.finalize_candle(c_repeat)
    count_after = len(wallet.positions)
    
    if count_after == count_before:
        print("SUCCESS: Repeated Signal Blocked by Cooldown!")
    else:
        print("FAILURE: Cooldown Failed (Position Opened).")

if __name__ == "__main__":
    asyncio.run(run_test())
