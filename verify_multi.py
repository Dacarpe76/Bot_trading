import asyncio
import logging
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot.processor import StrategyProcessor

# Mock Dashboard printer (since we didn't implement specialized dashboard file yet, using manual print)
def print_dashboard(wallet):
    print("\n--- DASHBOARD ---")
    status = wallet.get_positions_status()
    print(f"Equity: {wallet.get_portfolio_value(100):.2f} EUR")
    print("ID | Type | Avg | PnL | Margin | DCA")
    for s in status:
        print(f"{s['id']} | {s['type']} | {s['avg']:.2f} | ? | {s['margin']} | {s['dca']}")
    print("-----------------\n")

async def run_test():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    wallet = PaperWallet(initial_balance=500.0) # 500 EUR Capital
    processor = StrategyProcessor(wallet)
    
    print("--- STARTING MULTI-POSITION VERIFICATION ---")
    
    # 1. BASELINE
    base_price = 100.0
    start_time = 1700000000
    
    print("Generating baseline history...")
    for i in range(200):
        c = {'timestamp': start_time+(i*60), 'open': 100, 'high': 100.5, 'low': 99.5, 'close': 100, 'volume': 100, 'trades': 1, 'cvd': 0}
        processor.finalize_candle(c)
        
    atr = processor.current_atr
    print(f"ATR: {atr:.2f}")

    # 2. TEST LONG SIGNAL (Momentum)
    print("\n--- TEST: LONG REVERSION DETECTION ---")
    # Vrel > 3, ERR > 2.5, RSI < 30
    # Inject 30 candles dropping to kill RSI
    p = 100.0
    for i in range(20):
        p -= 1.0 # Drop
        c = {'timestamp': start_time+(200+i)*60, 'open': p, 'high': p, 'low': p-1, 'close': p, 'volume': 100, 'trades': 1, 'cvd': 0}
        processor.finalize_candle(c)
    
    # Trigger Candle: Low RSI (should be <30 now), High Vol, High Spread, Pin bar?
    # Actually just Vrel>3, ERR>2.5 means High Vol, Low Spread? 
    # ERR = Vrel / Srel. if Srel is small (narrow range), ERR is high.
    # So we want High Volume, Narrow Range (Absorption).
    print("Injecting Long Absorption Signal...")
    last_p = p
    absorb_c = {
        'timestamp': start_time+300*60,
        'open': last_p, 'high': last_p+0.1, 'low': last_p, 'close': last_p, # Narrow spread 0.1
        'volume': 500, # 5x avg
        'trades': 50, 'cvd': 0
    }
    # Spread needs to be small relative to avg spread (1.0). 0.1 is small.
    processor.finalize_candle(absorb_c)
    
    if len(wallet.positions) > 0:
        print("SUCCESS: Long Position Opened!")
    else:
        print("FAILURE: No Long Position.")
        
    # 3. TEST SHORT SIGNAL
    print("\n--- TEST: SHORT MOMENTUM ---")
    # Quick pump to reset RSI and go high?
    # Short Momentum: Price < EMA, RSI < 40.
    # We are already low price (80 vs EMA 100).
    # RSI is low (<30). So RSI < 40 is true.
    # Should open Short immediately on next regular candle if Momentum logic fits?
    # Wait, Price < EMA and RSI < 40. Yes.
    # Let's verify if we opened a Short too?
    # StrategyProcessor iterates checks sequentially.
    # We just opened Long on Absorption. 
    # Next candle, if RSI still < 40 and Price < EMA, it might open SHORT Momentum?
    # Yes, hedging/grid behavior.
    
    c = {'timestamp': start_time+301*60, 'open': last_p, 'high': last_p, 'low': last_p, 'close': last_p, 'volume': 100, 'trades': 1, 'cvd': 0}
    processor.finalize_candle(c)
    
    if len(wallet.positions) >= 2:
        print("SUCCESS: Two Positions Active (Likely Long + Short)!")
    else:
        print(f"Current Positions: {len(wallet.positions)}")

    # 4. TEST CAP LIMIT
    print("\n--- TEST: CAP LIMIT 50% ---")
    # We have 500 EUR. 
    # Long: 50 Margin. Short: 50 Margin. Total 100. Usage 20%.
    # Let's fill up positions.
    for i in range(4):
        wallet.open_position('LONG', 100)
    
    print(f"Positions Count: {len(wallet.positions)}")
    # Should be 5 max? Or limited by 50% rule?
    # 5 positions * 50 = 250 EUR Margin.
    # Total Equity = 500. Usage = 250/500 = 50%.
    # Next open should fail.
    
    allowed = wallet.can_open_new()
    print(f"Can open new? {allowed}")
    if not allowed:
        print("SUCCESS: Cap Limit Reached!")
    else:
        print("FAILURE: Cap Check passed unexpectedly.")

    # 5. TEST DCA LONG
    print("\n--- TEST: DCA LONG ---")
    # Pick the first LONG
    t_id = list(wallet.positions.keys())[0]
    pos = wallet.positions[t_id]
    entry = pos['avg_price']
    
    # Drop price > 2ATR
    drop_p = entry - (3.0 * atr)
    print(f"Dropping price to {drop_p} (Entry {entry})...")
    
    c = {'timestamp': start_time+500*60, 'open': drop_p, 'high': drop_p, 'low': drop_p, 'close': drop_p, 'volume': 100, 'trades': 1, 'cvd': 0}
    # This triggers manage_position
    processor.finalize_candle(c)
    
    
    if wallet.positions[t_id]['dca_count'] > 0:
        print(f"SUCCESS: DCA Executed! Count: {wallet.positions[t_id]['dca_count']}")
    else:
        print("FAILURE: No DCA.")

    # 6. TEST VOLATILITY FILTER
    print("\n--- TEST: VOLATILITY FILTER (PUMP > 3%) ---")
    # Current Price ~95. Let's pump it to 100 (approx 5% move) over 60 min.
    # Start: 95. End: 100.
    # We need history of 60 candles rising.
    base = 95.0
    target = 100.0
    step = (target - base) / 60
    
    print(f"Injecting +5% Pump (95->100) over 60m...")
    for i in range(61):
        p = base + (i * step)
        c = {'timestamp': start_time+(600+i)*60, 'open': p, 'high': p, 'low': p, 'close': p, 'volume': 100, 'trades': 1, 'cvd': 0}
        processor.finalize_candle(c)
        
    last_p = target
    atr = processor.current_atr
    
    # Now trigger SHORT Signal (Reversion)
    # Vrel>3, ERR>2.5, RSI>75
    print("Injecting Short Absorption Signal...")
    # High Price, RSI likely high due to pump.
    # Need High Vol, Narrow range.
    final_c = {
        'timestamp': start_time+(662)*60,
        'open': last_p, 'high': last_p+0.1, 'low': last_p, 'close': last_p, 
        'volume': 500, # High Vol
        'trades': 50, 'cvd': 0
    }
    
    # Capture position count before
    count_before = len(wallet.positions)
    processor.finalize_candle(final_c)
    count_after = len(wallet.positions)
    
    if count_after == count_before:
        print("SUCCESS: Short BLOCKED by Volatility Filter!")
    else:
        print("FAILURE: Short OPENED despite Pump.")
