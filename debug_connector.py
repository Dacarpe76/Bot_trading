import asyncio
import logging
from kraken_bot import config
from kraken_bot.connector import KrakenConnector

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    print(f"Loaded config from: {config.__file__}")
    print(f"SYMBOLS: {config.SYMBOLS}")
    
    queue = asyncio.Queue()
    connector = KrakenConnector(
        symbols=config.SYMBOLS,
        channels=["trade"],
        output_queue=queue
    )
    
    # Run connect for 10 seconds then exit
    try:
        await asyncio.wait_for(connector.connect(), timeout=10)
    except asyncio.TimeoutError:
        print("Test finished.")

if __name__ == "__main__":
    asyncio.run(main())
