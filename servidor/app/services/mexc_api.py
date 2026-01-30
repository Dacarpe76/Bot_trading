import ccxt.async_support as ccxt
import logging
from app.core.config import settings
import asyncio
import json
import time

logger = logging.getLogger(__name__)

class MexcService:
    def __init__(self):
        self.client = ccxt.mexc({
            'apiKey': settings.MEXC_API_KEY,
            'secret': settings.MEXC_SECRET_KEY,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True
            }
        })
        self.ws_url = "wss://wbs.mexc.com/ws"
    
    async def verify_connection(self):
        try:
            await self.client.load_markets()
            logger.info("MEXC Markets Loaded")
            return True
        except Exception as e:
            logger.error(f"MEXC Connection Failed: {e}")
            return False

    async def get_balance_usdt(self):
        try:
            bal = await self.client.fetch_balance()
            return bal['total'].get('USDT', 0.0), bal['free'].get('USDT', 0.0)
        except Exception as e:
            logger.error(f"Balance Fetch Error: {e}")
            return 0.0, 0.0

    async def get_current_price(self, symbol):
        try:
            ticker = await self.client.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Price Fetch Error {symbol}: {e}")
            return None

    async def place_order(self, symbol, side, qty, price=None, type='limit'):
        try:
            # MEXC V3 Spot
            # Side: 'buy' or 'sell'
            if type == 'market':
                return await self.client.create_order(symbol, type, side, qty)
            else:
                return await self.client.create_order(symbol, type, side, qty, price)
        except Exception as e:
            logger.error(f"Order Error {symbol} {side}: {e}")
            return None
        
    async def close(self):
        await self.client.close()

# Singleton for reuse
mexc_client = MexcService()
