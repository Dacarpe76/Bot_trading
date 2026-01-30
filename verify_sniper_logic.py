
import time
import logging
import sys
from kraken_bot.strategies import StrategyBandSniper
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot import config

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Setup
wallet = PaperWallet("TestSniper", initial_balance=500.0)
strategy = StrategyBandSniper(wallet, allowed_sides=['LONG', 'SHORT'])

symbol = "XRP/EUR"
price = 0.50

# --- Test 1: Entry Condition ---
print("\n--- Test 1: Entry Conditions (Short) ---")
# Short Setup: Price >= BB_Upper(0.50) + Stoch(95) + Conf(Red or Pin)
indicators = {
    'ADX_14': 25.0, # > 20 OK
    'Bollinger_Upper': 0.50,
    'Bollinger_Lower': 0.40,
    'Stoch_K': 95.0, # > 90 OK
    'Open': 0.51, # Red Candle (Price 0.50 < Open 0.51)
    'PinBar': 'False'
}

strategy.check_entry_logic(symbol, price, indicators)
# Check if opened
if len(wallet.positions) == 1:
    t_id = list(wallet.positions.keys())[0]
    pos = wallet.positions[t_id]
    print(f"SUCCESS: Opened {pos['type']} @ {pos['entry_price']}")
else:
    print("FAILURE: Did not open position.")
    sys.exit(1)

# --- Test 2: Breakeven Activation ---
print("\n--- Test 2: Breakeven Activation ---")
# Move price down to profit 0.25% (Short)
# Entry 0.50. Target +0.25% = 0.50 * (1 - 0.0025) = 0.49875
price_be = 0.4980 
strategy.manage_position(t_id, pos, price_be, indicators)

if pos.get('be_active') and pos['stop_loss'] == 0.50:
    print("SUCCESS: Breakeven Activated. SL set to Entry.")
else:
    print(f"FAILURE: BE not active. BE_Active={pos.get('be_active')}, SL={pos.get('stop_loss')}")

# --- Test 3: TP1 (Partial Close 50%) ---
print("\n--- Test 3: TP1 Mid-Band Hit ---")
# Move price to Mid Band. Mid = (0.50 + 0.40) / 2 = 0.45.
# Short needs Price <= Mid.
price_tp1 = 0.45
initial_size = pos['size']
indicators['Pivot_P'] = 0.45 # Hack if pivot used (code uses BB mean)
# Code calculates mid band from indicators BB Up/Low
indicators['Bollinger_Upper'] = 0.50
indicators['Bollinger_Lower'] = 0.40

strategy.manage_position(t_id, pos, price_tp1, indicators)

if pos.get('tp1_hit'):
    print(f"SUCCESS: TP1 Hit Flag Set.")
    # Check size
    current_size = pos['size']
    ratio = current_size / initial_size
    print(f"Size check: {initial_size} -> {current_size} (Ratio: {ratio:.2f})")
    if 0.49 < ratio < 0.51:
         print("SUCCESS: Size reduced by ~50%")
    else:
         print("FAILURE: Size not correct.")
else:
    print("FAILURE: TP1 did not trigger.")

# --- Test 4: TP2 (Final Close) ---
print("\n--- Test 4: TP2 Lower Band Hit ---")
# Move price to Lower Band (0.40)
price_tp2 = 0.40
strategy.manage_position(t_id, pos, price_tp2, indicators)

if t_id not in wallet.positions:
     print("SUCCESS: Position Closed fully.")
else:
     print("FAILURE: Position still open.")

