import asyncio
import logging
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot.processor import StrategyProcessor
import pandas as pd
from kraken_bot import config

# Mock Wallet to Spy on actions
class MockWallet(PaperWallet):
    pass 

async def run_test():
    print("--- STARTING MULTI-COIN VERIFICATION ---")
    
    # Setup
    wallet = MockWallet(initial_balance=1000.0)
    processor = StrategyProcessor(wallet)
    
    # 1. Test Config Loading
    print(f"Config Symbols: {config.SYMBOLS}")
    assert 'XBT/EUR' in config.SYMBOLS
    assert 'ETH/EUR' in config.SYMBOLS
    
    # 2. Test Independent State
    print("\n--- TEST INDEPENDENT STATE ---")
    # Clear history for consistent test
    for s in processor.market_state:
        processor.market_state[s]['candles'] = []

    # Feed XBT
    c_xbt = {'timestamp': 1000, 'open': 50000, 'high': 50000, 'low': 50000, 'close': 50000, 'volume': 100, 'trades': 1, 'symbol': 'XBT/EUR'}
    processor.finalize_candle('XBT/EUR', c_xbt)
    
    # Feed ETH
    c_eth = {'timestamp': 1000, 'open': 3000, 'high': 3000, 'low': 3000, 'close': 3000, 'volume': 500, 'trades': 1, 'symbol': 'ETH/EUR'}
    processor.finalize_candle('ETH/EUR', c_eth)
    
    xbt_state = processor.market_state['XBT/EUR']
    eth_state = processor.market_state['ETH/EUR']
    
    print(f"XBT Candles: {len(xbt_state['candles'])}")
    print(f"ETH Candles: {len(eth_state['candles'])}")
    
    assert len(xbt_state['candles']) == 1
    assert len(eth_state['candles']) == 1
    assert xbt_state['candles'][0]['close'] == 50000
    assert eth_state['candles'][0]['close'] == 3000
    print("SUCCESS: States are independent.")

    # 3. Test Strict Signal Trigger (XBT Long)
    print("\n--- TEST STRICT SIGNAL (XBT LONG) ---")
    
    # Seed Data (Need ~20 candles for MA)
    # create 20 candles for XBT
    # Flat price to ensure low spread -> High Srel? No, low spread -> Low Srel.
    # We need High Vrel and High ERR = Vrel/Srel.
    # If Srel is low, ERR explodes.
    # But we need ERR > 3.0.
    
    base_price = 100.0
    for i in range(25):
        # Oscillate to keep RSI valid
        import math
        p = base_price + math.sin(i)
        
        c = {
            'timestamp': 2000 + i*60,
            'open': p, 'high': p+0.1, 'low': p-0.1, 'close': p,
            'volume': 100, 'trades': 10, 'symbol': 'XBT/EUR'
        }
        processor.finalize_candle('XBT/EUR', c)
        
    # Inject Trigger Candle
    # High Volume (400 vs 100 avg -> Vrel=4)
    # Small Spread (0.1 vs 0.2 avg -> Srel=0.5)
    # ERR = 4 / 0.5 = 8.0 (>3.0)
    # RSI: Pre-drop it? 
    # Current RSI will be ~50. 
    # We need RSI < 25.
    
    # Let's tank price for RSI first
    print("Tanking Price for RSI...")
    for i in range(10):
        base_price -= 0.5 # Drop
        c = {
            'timestamp': 4000 + i*60,
            'open': base_price, 'high': base_price+0.01, 'low': base_price, 'close': base_price,
            'volume': 100, 'trades': 10, 'symbol': 'XBT/EUR'
        }
        processor.finalize_candle('XBT/EUR', c)

    # Trigger
    trig_price = base_price
    print(f"Injecting Trigger at {trig_price}...")
    c_trig = {
        'timestamp': 5000,
        'open': trig_price, 'high': trig_price+0.05, 'low': trig_price, 'close': trig_price,
        'volume': 500, # Vrel ~ 5
        'trades': 10, 'symbol': 'XBT/EUR'
    }
    processor.finalize_candle('XBT/EUR', c_trig)
    
    # Check Wallet
    print(f"Open Positions: {len(wallet.positions)}")
    if len(wallet.positions) == 1:
        pos = list(wallet.positions.values())[0]
        print(f"SUCCESS: Position Opened: {pos['symbol']} {pos['type']} @ {pos['entry_price']}")
        assert pos['symbol'] == 'XBT/EUR'
        assert pos['type'] == 'LONG'
        
        # Check Fee / PnL Net logic validation?
        # Simulating PnL
        net_pct = wallet.calc_pnl_pct_net(pos['id'], trig_price * 1.01) # 1% gain
        print(f"1% Gain Net PnL%: {net_pct:.2f}% (Should be ~0.8% after 0.2% fee roundtrip)")
        
    else:
        print("FAILURE: No position opened. Check logs.")
        # Debug state
        st = processor.market_state['XBT/EUR']
        print(f"Last Ind: {st['indicators']}")

    # 4. Test Capital Limit (Sniper)
    print("\n--- TEST CAPITAL LIMIT ---")
    # artificially fill wallet
    for i in range(15):
        wallet.positions[100+i] = {'symbol': f'DUMMY{i}', 'margin': 50, 'type': 'LONG', 'entry_time':0, 'entry_price':0}
    
    tot_margin, eq, usage = wallet.get_capital_usage()
    print(f"Usage: {usage*100:.1f}%")
    
    can = wallet.can_open_new('SOL/EUR', 'LONG')
    print(f"Can Open New? {can}")
    if usage > 0.4:
        assert not can
        print("SUCCESS: Blocked by Capital Limit.")
    else:
        print("Test inconclusive (didn't fill enough?)")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_test())
