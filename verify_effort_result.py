import pandas as pd
import logging
from unittest.mock import MagicMock
from kraken_bot.processor import StrategyProcessor
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)

def run_verification():
    print("--- Starting Verification of Effort vs Result Strategy ---")
    
    # 1. Mock Wallet
    mock_wallet = MagicMock()
    mock_wallet.active_position = False
    mock_wallet.avg_buy_price = 0.0
    mock_wallet.dca_count = 0
    mock_wallet.buy_market.return_value = True # Simulate successful buy

    # 2. Instantiate Processor
    processor = StrategyProcessor(mock_wallet)
    # Avoid fetching history
    processor.fetch_history = MagicMock() 

    # 3. Generate Synthetic Data (Scenario: Downtrend -> Absorption)
    # We need enough candles for RSI(14) and MA(20)
    # Let's create 50 candles
    
    candles = []
    price = 50000.0
    
    for i in range(50):
        # Create a downtrend to lower RSI
        price -= 100 
        
        c = {
            'timestamp': i,
            'open': price + 50,
            'high': price + 60,
            'low': price - 10,
            'close': price, # Close at low
            'volume': 100.0, # Steady volume
            'trades': 10
        }
        candles.append(c)

    # 4. Modify Last Candle to be the "Absorption" Candle
    # Conditions:
    # - Vrel > 3.0  (Need vol > 300, since avg is 100)
    # - ERR > 2.5   (Need Srel low. If spread is usually 70, let's make it 30. Srel=0.42. ERR=3/0.42=7)
    # - PosClose > 0.5 (Close in upper half)
    # - RSI < 35 (Should be low from downtrend)
    
    last_candle = candles[-1]
    last_candle['volume'] = 500.0 # Vrel ~ 5.0
    last_candle['high'] = price + 30
    last_candle['low'] = price
    last_candle['close'] = price + 25 # PosClose = 25/30 = 0.83
    
    # Update DataFrame
    df = pd.DataFrame(candles)
    
    # 5. Run Analysis
    print("Running analyze_market with synthetic data...")
    processor.analyze_market(df)
    
    # 6. Check Results
    # We expect buy_market to be called
    if mock_wallet.buy_market.called:
        print("SUCCESS: Buy signal triggered!")
        call_args = mock_wallet.buy_market.call_args
        print(f"Buy called with args: {call_args}")
    else:
        print("FAILURE: Buy signal NOT triggered.")
        # Debug info
        last_row = df.iloc[-1]
        print("Last Candle Data:")
        print(last_row)
        
        # We can inspect the internal dataframe of the processor if we assigned it, 
        # but analyze_market takes a df and modifies it inplace usually or we can check the df we passed if it modified it (pandas often does)
        # However, checking the logs (stdout) is best.

if __name__ == "__main__":
    run_verification()
