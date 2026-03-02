
import sys
import asyncio
import logging
import json
import uvicorn
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from kraken_bot import config
from kraken_bot.connector import KrakenConnector
from kraken_bot.processor import StrategyProcessor
from kraken_bot.reporter import TelegramReporter

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global Bot Instance
bot_manager = None

class BotManager:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.queue = asyncio.Queue()
        self.connector = KrakenConnector(
            symbols=config.SYMBOLS,
            channels=["trade"],
            output_queue=self.queue
        )
        self.strategy = StrategyProcessor()
        self.reporter = TelegramReporter()
        
        # Hooks
        self.strategy.on_monitor_update = self.broadcast_monitor
        self.strategy.on_event = self.on_strategy_event 
        # We can hijack 'on_candle_closed' or just poll for dashboard updates
        
        self.websocket_clients = set()
        self.running = True

    async def start(self):
        logging.info("BotManager: Starting components...")
        self.loop.create_task(self.connector.connect())
        self.loop.create_task(self.strategy.process_queue(self.queue))
        self.loop.create_task(self.broadcast_loop())
        
        self.reporter.send_message("🌐 *Web Bot Started* \nDashboard Online.")

    async def broadcast_loop(self):
        """Periodically broadcast full dashboard state (Strategy Summaries + Ops)."""
        while self.running:
            await asyncio.sleep(1.0) # 1Hz Update
            await self.push_dashboard_update()

    async def stop(self):
        self.running = False
        # Add cleanup logic if needed

    # --- Data Gathering ---
    def get_dashboard_data(self):
        """Compiles the Strategy List data."""
        strategies_data = []
        all_ops = []
        all_history = []
        global_equity = 0.0
        
        # Get live prices cache from processor state
        prices = {}
        for s, state in self.strategy.market_state.items():
             if state['current_candle']:
                 prices[s] = state['current_candle']['close']
             elif state['candles']:
                 prices[s] = state['candles'][-1]['close']
             else:
                 prices[s] = 0.0

        for strat_id, strat in self.strategy.strategies.items():
            w = strat.wallet
            
            # ROI / Calcs
            roi = w.get_annualized_roi()
            wins = len([t for t in w.trades_history if t['final_pnl'] >= 0])
            total = len(w.trades_history)
            wr = (wins / total * 100) if total > 0 else 0.0
            total_pnl = sum([t['final_pnl'] for t in w.trades_history])
            
            equity = w.get_portfolio_value(prices)
            global_equity += equity
            
            # Start Time Display
            # Logic: If history exists, take min entry time. Else use wallet.start_time
            # Format as DD/MM/YYYY HH:MM
            import datetime
            s_time = w.start_time
            if w.trades_history:
                 s_time = min([t['entry_time'] for t in w.trades_history])
            # Also check active ops
            for p in w.positions.values():
                 if p['entry_time'] < s_time: s_time = p['entry_time']
                 
            start_str = datetime.datetime.fromtimestamp(s_time).strftime("%d/%m/%Y %H:%M")

            strategies_data.append({
                'id': strat_id,
                'roi': roi,
                'pnl': total_pnl,
                'win_rate': wr,
                'start_date': start_str,
                'active_ops': len(w.positions),
                'total_ops': total,
                'wins': wins,
                'losses': total - wins,
                'balance': w.balance_eur,
                'equity': equity
            })
            
            # Operations
            ops = w.get_positions_status(prices)
            for op in ops:
                op['strategy_id'] = strat_id
                all_ops.append(op)
                
            # History
            hist = w.get_history()
            for h in hist:
                h['strategy_id'] = strat_id
                all_history.append(h)
                
        # Sort History by close time (newest first)
        all_history.sort(key=lambda x: x.get('close_time', 0), reverse=True)
                
        return {
            "type": "dashboard_update",
            "global_equity": global_equity,
            "strategies": strategies_data,
            "operations": all_ops,
            "history": all_history
        }

    # --- Broadcasting ---
    async def broadcast(self, message: dict):
        if not self.websocket_clients: return
        json_msg = json.dumps(message)
        to_remove = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_text(json_msg)
            except:
                to_remove.add(ws)
        self.websocket_clients -= to_remove

    def broadcast_monitor(self, data):
        """Called by Processor on tick."""
        # data is list of {symbol, price, rsi, ...}
        # Filter unwanted fields (Indicators)
        clean_data = []
        for d in data:
            clean_data.append({
                'symbol': d['symbol'],
                'price': d['price']
            })
        
        # Fire and forget (in loop)
        asyncio.create_task(self.broadcast({
            "type": "market_update",
            "data": clean_data
        }))

    async def push_dashboard_update(self):
        data = self.get_dashboard_data()
        await self.broadcast(data)

    def on_strategy_event(self, event_type, strat_id, symbol, price, indicators):
        # Could log or notify
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global bot_manager
    bot_manager = BotManager()
    await bot_manager.start()
    yield
    # Shutdown
    await bot_manager.stop()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="kraken_bot/templates")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    if bot_manager:
        bot_manager.websocket_clients.add(websocket)
    try:
        while True:
            # Keep alive / listen for commands (not implemented yet)
            await websocket.receive_text()
    except:
        if bot_manager:
            bot_manager.websocket_clients.remove(websocket)

if __name__ == "__main__":
    uvicorn.run("kraken_bot.web_server:app", host="0.0.0.0", port=8000, reload=False)
