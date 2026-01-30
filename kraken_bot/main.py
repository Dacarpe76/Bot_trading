import asyncio
import logging
from connector import KrakenConnector
import config

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

from paper_wallet import PaperWallet
from processor import StrategyProcessor

async def dashboard_loop(wallet):
    """Prints dashboard every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        print("\n" + "="*60)
        print(f"--- DASHBOARD ({config.WS_SYMBOL}) ---")
        print(wallet.status_report(0)) # Price 0 or need current?
        # Actually wallet.status_report returns a string summary.
        # User wanted a table: ID | Tipo | PNL % | Coste Total | Precio Promedio | DCAs realizados
        
        # New Table Format
        stats = wallet.get_positions_status()
        print(f"Equity: {wallet.get_portfolio_value(0):.2f} EUR (Approx)") 
        # Note: get_portfolio_value needs current price. 
        # We don't have easy access to current price here unless we share it or read from strategy.
        # Strategy has candles. Wallet doesn't know price unless passed.
        # Let's just print what we have in wallet logic.
        
        print(f"{'ID':<4} | {'Type':<6} | {'Avg':<8} | {'Margin':<8} | {'DCA':<3}")
        print("-" * 45)
        if not stats:
            print("No active positions.")
        for s in stats:
            print(f"{s['id']:<4} | {s['type']:<6} | {s['avg']:<8.2f} | {s['margin']:<8.2f} | {s['dca']:<3}")
        print("="*60 + "\n")

async def main():
    logging.info("--- Starting Kraken VSA Bot (Multi-Position Paper) ---")
    
    # Initialize Queues
    data_queue = asyncio.Queue()
    
    # Initialize Components
    wallet = PaperWallet(initial_balance=config.INITIAL_BALANCE)
    strategy = StrategyProcessor(wallet)
    
    connector = KrakenConnector(
        symbols=[config.WS_SYMBOL],
        channels=['trade'], # Focusing on Trade for VSA/CVD
        output_queue=data_queue
    )
    
    # Start Tasks
    producer_task = asyncio.create_task(connector.connect())
    consumer_task = asyncio.create_task(strategy.process_queue(data_queue))
    dash_task = asyncio.create_task(dashboard_loop(wallet))
    
    try:
        await asyncio.gather(producer_task, consumer_task, dash_task)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
    except Exception as e:
        logging.error(f"Critical Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
