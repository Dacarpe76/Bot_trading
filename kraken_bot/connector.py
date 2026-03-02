import asyncio
import websockets
import json
import logging
import logging
from kraken_bot import config

class KrakenConnector:
    def __init__(self, symbols, channels, output_queue):
        self.url = config.KRAKEN_WS_URL
        self.symbols = symbols
        self.channels = channels
        self.queue = output_queue
        self.ws = None

    async def connect(self):
        while True:
            try:
                logging.info(f"Connecting to {self.url}...")
                # Kraken documentation suggests they send heartbeats.
                # To avoid client-side timeouts if network lags or Kraken doesn't pong fast enough:
                # ping_interval=None: Disable client-side pings
                # ping_timeout=None: Disable waiting for pongs
                async with websockets.connect(self.url, ping_interval=30, ping_timeout=120) as websocket:
                    self.ws = websocket
                    logging.info("Connected to Kraken API.")
                    
                    await self.subscribe()
                    
                    await self.listen()
            except Exception as e:
                logging.error(f"Connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def subscribe(self):
        # Kraken Subscription Format: DOGE must be XDG
        sub_symbols = [s.replace('DOGE/EUR', 'XDG/EUR') for s in self.symbols]
        payload = {
            "event": "subscribe",
            "pair": sub_symbols,
            "subscription": {
                "name": "trade"
            }
        }
        await self.ws.send(json.dumps(payload))
        logging.info(f"KrakenConnector: Sent Subscribe for {len(sub_symbols)} pairs: {sub_symbols}")

    async def listen(self):
        async for message in self.ws:
            try:
                # logging.info(f"KrakenConnector: Raw message received") # Too verbose
                data = json.loads(message)
                
                # Filter Heartbeats/SystemStatus/Subscriptions
                if isinstance(data, dict):
                    # Kraken events
                    if data.get("event") == "heartbeat":
                        # logging.info("Heartbeat")
                        continue
                    if data.get("event") == "subscriptionStatus":
                        logging.info(f"Subscription Status: {data}")
                        continue
                    if data.get("event") == "error":
                        logging.error(f"Kraken Error: {data}")
                        continue
                        
                    logging.info(f"Kraken Event: {data}")
                    
                # logging.info(f"Data received: {data}") 
                if isinstance(data, list):
                    # DEBUG: Log purely raw data to see structure
                    # logging.info(f"Raw List: {data}") 
                    
                    
                    # Kraken Trade Msg Format: [channelID, [[price, vol, time, side, type, misc], ...], 'trade', 'Pair']
                    if len(data) >= 4 and data[-2] == 'trade':
                        trades = data[1]
                        pair = data[-1]
                        
                        # Normalize Kraken XDG -> DOGE
                        if pair == 'XDG/EUR': pair = 'DOGE/EUR'
                        
                        # Ensure trades is a list of lists
                        if isinstance(trades, list):
                             self.queue.put_nowait((pair, trades))
                        else:
                             logging.warning(f"Unexpected trades format for {pair}: {type(trades)}")

                    # Handle deprecated or alternative formats if any
                    elif len(data) >= 4 and isinstance(data[1], list):
                        # Try to guess? No, stick to documentation.
                        pass
                    else:
                        # Log unexpected structure only if it looks like data
                        # logging.debug(f"Ignored structure: {data}")
                        pass
                        

                
            except Exception as e:
                logging.error(f"Error processing message: {e}")
