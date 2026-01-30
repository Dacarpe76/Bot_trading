import pandas as pd
import numpy as np
from kraken_bot.processor import StrategyProcessor

def test_regime():
    proc = StrategyProcessor()
    
    # Mock Dataframe
    data = {
        'close': [100]*50,
        'high': [101]*50,
        'low': [99]*50,
        'ema200': [100]*50,
        'Bollinger_Width': [1.0]*50  # Stable width
    }
    df = pd.DataFrame(data)
    
    # Test 1: Ranging (ADX < 25)
    # We mock ADX by injecting into df (processor checks column first)
    df['ADX_14'] = 15.0
    regime = proc.determine_regime("TEST", df)
    print(f"Test 1 (Ranging): Expected 'Ranging_Lateral', Got '{regime}'")
    assert regime == 'Ranging_Lateral'

    # Test 2: Trending Up
    df['ADX_14'] = 30.0
    df['close'] = 105.0 # Above EMA 100
    df['ema200'] = 100.0
    regime = proc.determine_regime("TEST", df)
    print(f"Test 2 (Trend Up): Expected 'Trending_Up', Got '{regime}'")
    assert regime == 'Trending_Up'
    
    # Test 3: Trending Down
    df['close'] = 95.0 # Below EMA
    regime = proc.determine_regime("TEST", df)
    print(f"Test 3 (Trend Down): Expected 'Trending_Down', Got '{regime}'")
    assert regime == 'Trending_Down'

    # Test 4: High Volatility
    # BB Width > Avg * 2
    # Set history width to 1.0, current to 3.0
    df['Bollinger_Width'] = 1.0
    df.iloc[-1, df.columns.get_loc('Bollinger_Width')] = 3.0
    
    regime = proc.determine_regime("TEST", df)
    print(f"Test 4 (High Vol): Expected 'High_Volatility', Got '{regime}'")
    assert regime == 'High_Volatility'

if __name__ == "__main__":
    try:
        test_regime()
        print("ALL TESTS PASSED")
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
