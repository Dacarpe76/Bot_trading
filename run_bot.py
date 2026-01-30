import sys
import os

# Add the current directory to sys.path to make sure we can import the package
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# --- Force PyInstaller to see these modules ---
import kraken_bot.connector
import kraken_bot.processor
import kraken_bot.paper_wallet
import kraken_bot.config
# ----------------------------------------------

from kraken_bot import gui

if __name__ == "__main__":
    gui.main()
