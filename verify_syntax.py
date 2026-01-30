
import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

# Mock libraries not available in agent env but present in user env
sys.modules['pandas'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['ta'] = MagicMock()
sys.modules['ta.momentum'] = MagicMock() # Mock submodule
sys.modules['ta.volatility'] = MagicMock() # Mock submodule
sys.modules['requests'] = MagicMock()
sys.modules['pyqtgraph'] = MagicMock()

try:
    print("Checking kraken_bot/paper_wallet.py...")
    import kraken_bot.paper_wallet
    print("OK")

    print("Checking kraken_bot/strategies.py...")
    import kraken_bot.strategies
    print("OK")

    print("Checking kraken_bot/processor.py...")
    import kraken_bot.processor
    print("OK")
    
    print("Checking kraken_bot/reporter.py...")
    import kraken_bot.reporter
    print("OK")

    print("Checking kraken_bot/gui.py...")
    # gui imports PyQt6. If fails, we skip or mock.
    try:
        import kraken_bot.gui
        print("OK")
    except ImportError:
        print("SKIPPED (GUI libs missing)")

    print("ALL SYNTAX CHECKS PASSED")

except Exception as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
