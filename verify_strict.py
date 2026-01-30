import asyncio
import logging
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot.processor import StrategyProcessor
import pandas as pd
import os

# --- MOCK CLASSES ---
class MockWallet(PaperWallet):
    def __init__(self):
        super().__init__()
        self.positions = {}
        self.next_id = 1
        self.balance_eur = 1000.0
        
    def open_position(self, side, price):
        t_id = super().open_position(side, price)
        if t_id:
             # Add mock time to verify cooldown if needed, but we testing exclusivity
             self.positions[t_id]['entry_time'] = 0.0 
        return t_id

async def run_test():
    wallet = MockWallet()
    processor = StrategyProcessor(wallet)
    processor.fetch_history = lambda: None # Disable HTTP
    
    # 1. SETUP INDICATORS
    # We need EMA200, RSI, VolMA seeded. 
    # We'll create a synthetic history.
    print("--- 1. SEEDING DATA ---")
    data = []
    base_price = 100.0
    import math
    for i in range(250):
        # Oscillate to avoid RSI NaN (0/0)
        p = base_price + math.sin(i/10.0) * 2 
        data.append({
            'timestamp': 1000 + i*60,
            'open': p, 'high': p+0.5, 'low': p-0.5, 'close': p,
            'volume': 100.0, 'trades': 10
        })
    df_seed = pd.DataFrame(data)
    processor.analyze_market(df_seed) # Seed Indicators (EMA flat at 100, RSI 50)
    
    # 2. TEST LONG ENTRY (Strict)
    # Require: Vrel > 3.5, ERR > 3.0, RSI < 25
    print("\n--- 2. TEST STRICT LONG ENTRY ---")
    
    # Attempt Weak Signal (Vrel 2.0 -> Should Fail)
    c_weak = {'timestamp': 2000, 'open': 95, 'high': 95, 'low': 95, 'close': 95, 'volume': 200, 'trades': 10}
    # We need to manually inject VOL MA context. The processor calculates from history.
    # History has vol 100. 200 is Vrel=2.0.
    processor.finalize_candle(c_weak)
    print(f"Weak Signal OpenPos: {len(wallet.positions)} (Expected 0)")
    
    # Attempt Strong Signal (Vrel 400 -> 4.0, RSI needs to be < 25)
    # To get RSI < 25, we need price drop sequence.
    # Manual injection of drops.
    print("Driving RSI down...")
    p = 95
    for i in range(10):
        p -= 2
        processor.finalize_candle({'timestamp': 3000+i*60, 'open': p, 'high': p, 'low': p, 'close': p, 'volume': 100, 'trades': 10})
    
    # Now RSI should be low. Inject HIGH VOL Candle.
    # Spread needs to be small for high ERR (Vrel/Srel). 
    # Spread=0 doesn't work (div 0 protection probably makes ERR 0).
    # Spread=0.1. Avg Spread=0 from flat history? 
    # We need SpreadMA > 0.
    # Let's inject some spread history first.
    print("Seeding Spreads (with slight drop to keep RSI low)...")
    for i in range(20):
         p -= 0.2 # Slight drift down
         processor.finalize_candle({'timestamp': 4000+i*60, 'open': p, 'high': p+1, 'low': p, 'close': p, 'volume': 100, 'trades': 10})
    
    # Trigger Candle
    # Vrel > 3.5 (Vol > 350)
    # Spread small (0.1) vs Avg (1.0). Srel = 0.1. ERR = Vrel/Srel = 3.5/0.1 = 35.
    print("Injecting Trigger...")
    c_trigger = {'timestamp': 5000, 'open': p, 'high': p+0.1, 'low': p, 'close': p, 'volume': 600, 'trades': 10}
    processor.finalize_candle(c_trigger)
    
    if len(wallet.positions) == 1:
        print("SUCCESS: Strict Long Opened!")
    else:
        print(f"FAILURE: No Long Opened. (Pos: {len(wallet.positions)})")
        # debug
        last = processor.candles[-1]
        print(f"DEBUG: RSI={last.get('rsi')} Vol={last.get('volume')} EMA={last.get('ema200', 0)}")

    # 3. TEST EXCLUSIVITY & STRICT DCA
    print("\n--- 3. TEST EXCLUSIVITY & DCA ---")
    # Try another signal immediately same price -> Should Block (Exclusivity)
    processor.finalize_candle(c_trigger)
    print(f"Immediate Re-Signal Pos Count: {len(wallet.positions)} (Expected 1)")
    
    # Try DCA with Distance but NO SIGNAL -> Should Block
    p_dca = p * 0.98 # 2% drop
    c_drop = {'timestamp': 6000, 'open': p_dca, 'high': p_dca, 'low': p_dca, 'close': p_dca, 'volume': 100, 'trades': 10}
    processor.finalize_candle(c_drop) # Low vol
    print(f"Drop without Signal DCA Count: {wallet.positions.get(1, {}).get('dca_count', 0)} (Expected 0)")
    
    # Try DCA with Distance AND SIGNAL
    c_dca_valid = {'timestamp': 7000, 'open': p_dca, 'high': p_dca+0.1, 'low': p_dca, 'close': p_dca, 'volume': 800, 'trades': 10}
    processor.finalize_candle(c_dca_valid)
    dca_c = wallet.positions.get(1, {}).get('dca_count', 0)
    if dca_c == 1:
        print("SUCCESS: DCA Executed with Strict Signal!")
    else:
        print(f"FAILURE: DCA Note Executed. count={dca_c}")

    # 4. CSV CHECK
    print("\n--- 4. CSV CHECK ---")
    if os.path.exists("trading_study.csv"):
        print("SUCCESS: trading_study.csv exists.")
        with open("trading_study.csv", 'r') as f:
            lines = f.readlines()
            print(f"Logged Lines: {len(lines)}")
    else:
        print("FAILURE: CSV not found.")
        
    # Cleanup
    if os.path.exists("trading_study.csv"):
        os.remove("trading_study.csv")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_test())
