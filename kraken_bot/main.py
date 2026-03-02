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

async def main():
    logging.info("--- Starting Kraken VSA Bot (Multi-Position Paper) ---")
    
    # Initialize Queues
    data_queue = asyncio.Queue()
    
    # Initialize Components
    # Note: StrategyProcessor now manages its own multiple strategies and wallets
    strategy = StrategyProcessor()
    
    connector = KrakenConnector(
        symbols=config.SYMBOLS,
        channels=['trade'], # Focusing on Trade for VSA/CVD
        output_queue=data_queue
    )
    
    # Start Tasks
    producer_task = asyncio.create_task(connector.connect())
    consumer_task = asyncio.create_task(strategy.process_queue(data_queue))
    
    try:
        await asyncio.gather(producer_task, consumer_task)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
    except Exception as e:
        logging.error(f"Critical Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
