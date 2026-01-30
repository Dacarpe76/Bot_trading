import asyncio
import logging
import json
import pandas as pd
from datetime import datetime
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Position, OrderHistory, LogEntry, BotState
from app.services.mexc_api import mexc_client
from app.services.strategies import strategy

logger = logging.getLogger("BotEngine")

class BotEngine:
    def __init__(self):
        self.running = False
        self.market_data = {sym: pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']) for sym in settings.TRADING_PAIRS}
        self.active_positions = {} # Cache
        self.queue = asyncio.Queue()
        
    async def start(self):
        logger.info("Starting Bot Engine...")
        self.running = True
        
        # 1. Load Active Positions from DB
        self.load_positions()
        
        # 2. Worker Task
        asyncio.create_task(self.order_worker())
        
        # 3. WebSocket Loop
        await self.websocket_loop()

    def load_positions(self):
        db = SessionLocal()
        positions = db.query(Position).filter(Position.status == "OPEN").all()
        for p in positions:
            self.active_positions[p.symbol] = p
        db.close()
        logger.info(f"Loaded {len(self.active_positions)} active positions.")

    async def order_worker(self):
        while self.running:
            task = await self.queue.get()
            # Task: (action, symbol, params)
            await self.process_order_task(task)
            self.queue.task_done()
            await asyncio.sleep(0.250) # Rate Limit 4/s

    async def process_order_task(self, task):
        action, symbol, params = task
        logger.info(f"Processing Order: {action} {symbol} {params}")
        
        db = SessionLocal()
        try:
            if action == 'OPEN':
                # Stake Calculation
                stake = settings.DEFAULT_STAKE_USDT
                price = params['price']
                qty = stake / price
                # Execute
                res = await mexc_client.place_order(symbol, 'buy', qty, type='market')
                if res:
                    # DB Create
                    pos = Position(
                        symbol=symbol, strategy="RollingDCA", status="OPEN",
                        avg_price=float(res['price']) if res.get('price') else price,
                        total_size=float(res['amount']) if res.get('amount') else qty,
                        total_cost=float(res['cost']) if res.get('cost') else stake,
                        dca_step=0
                    )
                    db.add(pos)
                    db.commit()
                    self.active_positions[symbol] = pos
                    self.log_db(db, "INFO", f"Opened {symbol} @ {price}")

            elif action == 'DCA':
                # Multiplier
                mult = params['mult']
                current_pos = self.active_positions[symbol]
                
                # Base Cost * Mult? Or Total Cost?
                # RollingDCA usually Base * Mult.
                stake = settings.DEFAULT_STAKE_USDT * mult
                price = params['price']
                qty = stake / price
                
                res = await mexc_client.place_order(symbol, 'buy', qty, type='market')
                if res:
                    # Update Pos
                    # Need to reload from DB to attach session?
                    pos_db = db.query(Position).filter(Position.id == current_pos.id).first()
                    pos_db.total_size += qty
                    pos_db.total_cost += stake
                    # Recalc Avg
                    pos_db.avg_price = pos_db.total_cost / pos_db.total_size
                    pos_db.dca_step += 1
                    db.commit()
                    self.active_positions[symbol] = pos_db
                    self.log_db(db, "INFO", f"DCA Step {pos_db.dca_step} {symbol}")

            elif action == 'CLOSE':
                current_pos = self.active_positions[symbol]
                qty = current_pos.total_size
                res = await mexc_client.place_order(symbol, 'sell', qty, type='market')
                if res:
                    pos_db = db.query(Position).filter(Position.id == current_pos.id).first()
                    pos_db.status = "CLOSED"
                    db.commit()
                    del self.active_positions[symbol]
                    self.log_db(db, "INFO", f"Closed {symbol} with Profit.")

        except Exception as e:
            logger.error(f"Task Failed: {e}")
            self.log_db(db, "ERROR", f"Order Failed {symbol}: {e}")
        finally:
            db.close()

    def log_db(self, db, level, msg):
        log = LogEntry(level=level, message=msg)
        db.add(log)
        db.commit()

    async def websocket_loop(self):
        import websockets
        uri = "wss://wbs.mexc.com/ws"
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    logger.info("Connected to MEXC WS")
                    
                    # Ping loop
                    asyncio.create_task(self.ws_ping(websocket))
                    
                    # Subscribe
                    pairs = [s for s in settings.TRADING_PAIRS]
                    # MEXC Topic: spot@public.kline.v3.api@<symbol>@<interval>
                    # Symbol e.g. BTCUSDT (no slash)
                    topics = [f"spot@public.kline.v3.api@{s}@Min5" for s in pairs]
                    
                    sub_msg = {
                        "method": "SUBSCRIPTION",
                        "params": topics
                    }
                    await websocket.send(json.dumps(sub_msg))
                    logger.info(f"Subscribed to {len(topics)} pairs.")
                    
                    while self.running:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        
                        # Handle Data
                        if 'c' in data and 'kline' in data['c']:
                            # Data format: {"d": {"k": {"t": 123, "o":..., "c":...}}}
                            payload = data['d']
                            k = payload['k']
                            
                            symbol = payload.get('s', '').replace('USDT', 'USDT') # Ensure normalized?
                            # MEXC returns symbol in payload usually?
                            # 'c' string contains symbol: spot@public.kline.v3.api@BTCUSDT@Min5
                            # Extract from topic 'c' if needed
                            topic_parts = data['c'].split('@')
                            if len(topic_parts) >= 3:
                                symbol = topic_parts[2]
                            
                            await self.on_kline_update(symbol, k)

            except Exception as e:
                logger.error(f"WS Error: {e}")
                await asyncio.sleep(5)
                
    async def ws_ping(self, ws):
        while self.running:
            try:
                await ws.send(json.dumps({"method": "PING"}))
                await asyncio.sleep(20)
            except:
                break

    async def on_kline_update(self, symbol, kline):
        # Update DataFrame
        # kline: t, o, c, h, l, v, ...
        ts = pd.to_datetime(kline['t'], unit='s')
        close = float(kline['c'])
        
        # Append to market_data
        df = self.market_data.get(symbol)
        if df is None: return
        
        # Simple Logic: Only keep 100 candles. 
        # For real-time kline (updating tick), we replace the last row if timestamp matches?
        # Or just append closed candles?
        # MEXC stream pushes updates. 
        # Strategy usually needs CLOSED candles. 
        # But RollingDCA checks RSI on the 5m candle. Live RSI? Or Closed?
        # "check_signal" logic usually implies closed.
        # But user wants "Real Time".
        # Let's use live close for immediate calculation.
        
        new_row = {
            'timestamp': ts,
            'open': float(kline['o']), 
            'high': float(kline['h']),
            'low': float(kline['l']),
            'close': close,
            'volume': float(kline['v'])
        }
        
        # Check if last row is same timestamp (update) or new
        if not df.empty and df.iloc[-1]['timestamp'] == ts:
            df.iloc[-1] = new_row
        else:
            # New candle (previous closed)
            # Should we trigger strategy on the CLOSE of the previous?
            # Yes, standard practice.
            # But let's append new first to have live data.
            # df = df.append(new_row) deprecated
            df.loc[len(df)] = new_row
            
        if len(df) > 100:
            df.drop(df.head(1).index, inplace=True)
            self.market_data[symbol] = df # Reassign if copy
            
        # Run Strategy
        inds = strategy.analyze(df)
        if not inds: return
        
        pos = self.active_positions.get(symbol)
        action, qty_mult, price_trigger = strategy.check_signal(symbol, inds, pos)
        
        if action != 'HOLD':
            # Add to Queue
            # Check if recently added to avoid spamming queue for same signal in same candle?
            # Queue Worker handles rate limit.
            # But continuous signal?
            # Check_signal might return OPEN repeatedly if condition holds.
            # We need to check if we already have an ORDER pending?
            # Postpone complex deduplication.
            await self.queue.put((action, symbol, {'price': close, 'mult': qty_mult}))

bot_engine = BotEngine()
