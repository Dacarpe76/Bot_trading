import asyncio
import logging
import json
import uvicorn
from fastapi import FastAPI, WebSocket, Request, Response, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import Set

from kraken_bot import config
from kraken_bot.connector import KrakenConnector
from kraken_bot.processor import StrategyProcessor
from kraken_bot.reporter import TelegramReporter
from kraken_bot.auth import get_client_role

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WebBotManager:
    def __init__(self):
        self.loop = None
        self.queue = None
        self.connector = None
        self.strategy = StrategyProcessor()
        self.reporter = TelegramReporter()
        
        # Hooks for Processor
        self.strategy.on_monitor_update = self.on_monitor_update
        
        self.websocket_clients: Set[WebSocket] = set()
        self.active_ops_cache = []
        self.dashboard_cache = {}
        self.running = True

    async def start(self):
        logging.info("WebBotManager: Initializing Bot Components...")
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.connector = KrakenConnector(
            symbols=config.SYMBOLS,
            channels=["trade"],
            output_queue=self.queue
        )
        # Step 1: Pre-load History (Sync if needed, better async but processor is sync)
        await self.loop.run_in_executor(None, self.strategy.fetch_all_history)
        
        # Step 2: Start Workers
        self.loop.create_task(self.connector.connect())
        self.loop.create_task(self.strategy.process_queue(self.queue))
        self.loop.create_task(self.broadcast_loop())
        
        self.reporter.send_message("🌐 *Bot Agresivo Web V2 Online* \nDashboard premium habilitado.")

    async def broadcast_loop(self):
        """Periodically broadcast dashboard state to all clients."""
        while self.running:
            await asyncio.sleep(1.0) # 1Hz
            if self.websocket_clients:
                data = self.get_full_state()
                await self.broadcast(data)

    def get_full_state(self):
        """Compiles the complete state for the dashboard."""
        prices = {s: (st['current_candle']['close'] if st['current_candle'] else (st['candles'][-1]['close'] if st['candles'] else 0.0)) 
                  for s, st in self.strategy.market_state.items()}
        
        strategies_data = []
        all_ops = []
        all_history = []
        global_equity = 0.0

        for strat_id, strat in self.strategy.strategies.items():
            w = strat.wallet
            total_pnl = sum([t['final_pnl'] for t in w.trades_history])
            equity = w.get_portfolio_value(prices)
            global_equity += equity
            
            strategies_data.append({
                "id": strat_id,
                "name": strat_id, # Can use STRATEGY_DISPLAY_NAMES later
                "balance": round(w.balance_eur, 2),
                "equity": round(equity, 2),
                "pnl": round(total_pnl, 2),
                "roi": round(w.get_annualized_roi(), 2),
                "active_ops": len(w.positions),
                "total_ops": len(w.trades_history),
                "paused": getattr(strat, 'paused', False)
            })
            
            # Active Positions
            for op in w.get_positions_status(prices):
                op['strategy_id'] = strat_id
                all_ops.append(op)
            
            # History
            for h in w.get_history():
                h['strategy_id'] = strat_id
                all_history.append(h)

        all_history.sort(key=lambda x: x.get('close_time', 0), reverse=True)

        return {
            "type": "full_state",
            "global_equity": round(global_equity, 2),
            "strategies": strategies_data,
            "operations": all_ops,
            "history": all_history[:50], # Last 50 for performance
            "market": self.get_market_monitor(prices)
        }

    def get_market_monitor(self, prices):
        """Returns the current market data."""
        monitor = []
        for symbol, price in prices.items():
            state = self.strategy.market_state.get(symbol, {})
            ind = state.get('indicators', {})
            monitor.append({
                "symbol": symbol,
                "price": price,
                "rsi": round(ind.get('rsi', 50), 2),
                "vrel": round(ind.get('vrel', 0), 2),
                "regime": state.get('current_regime', 'Neutral')
            })
        return monitor

    def on_monitor_update(self, data):
        """Callback from Processor on every tick."""
        # Simple market update to keep UI alive (high frequency)
        if self.websocket_clients:
            asyncio.create_task(self.broadcast({"type": "market_tick", "data": data}))

    async def broadcast(self, message: dict):
        if not self.websocket_clients: return
        msg_json = json.dumps(message)
        dead_clients = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_text(msg_json)
            except:
                dead_clients.add(ws)
        self.websocket_clients -= dead_clients

    async def stop(self):
        self.running = False
        # Add component stop logic here

manager = WebBotManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()
    yield
    await manager.stop()

app = FastAPI(lifespan=lifespan, title="Bot Agresivo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---

@app.get("/api/role")
async def get_role(request: Request, response: Response):
    role = get_client_role(request, response)
    return {"role": role}

@app.get("/api/state")
async def get_state(request: Request, response: Response):
    # Public view restricted in actual implementation if needed
    # role = get_client_role(request, response)
    return manager.get_full_state()

@app.post("/api/control/{strategy_id}/{action}")
async def control_bot(strategy_id: str, action: str, request: Request, response: Response):
    role = get_client_role(request, response)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede realizar esta acción.")
    
    if strategy_id not in manager.strategy.strategies:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")
    
    strat = manager.strategy.strategies[strategy_id]
    if action == "pause":
        strat.paused = True
    elif action == "resume":
        strat.paused = False
    elif action == "stop_all":
        # Panic stop
        pass 
        
    return {"status": "success", "action": action, "strategy": strategy_id}

# WebSocket for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    manager.websocket_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except:
        manager.websocket_clients.remove(websocket)

# Serve built frontend (when ready)
# app.mount("/", StaticFiles(directory="web_server/static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("kraken_bot.web_server.server:app", host="0.0.0.0", port=8000, reload=False)
