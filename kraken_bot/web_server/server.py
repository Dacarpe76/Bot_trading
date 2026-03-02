import asyncio
import logging
import json
import os
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
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

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
            
            # Calculate wins/losses
            wins = sum(1 for t in w.trades_history if t['final_pnl'] > 0)
            losses = sum(1 for t in w.trades_history if t['final_pnl'] <= 0)
            win_rate = (wins / len(w.trades_history) * 100) if len(w.trades_history) > 0 else 0.0
            
            # Calculate active wins/losses
            active_wins = 0
            active_losses = 0
            for op in w.get_positions_status(prices):
                if op['pnl_pct'] > 0:
                    active_wins += 1
                else:
                    active_losses += 1
            
            strategies_data.append({
                "id": strat_id,
                "name": strat_id,
                "balance": round(w.balance_eur, 2),
                "equity": round(equity, 2),
                "pnl": round(total_pnl, 2),
                "roi": round(w.get_annualized_roi(), 2),
                "daily_roi": round(w.get_daily_roi(), 2),
                "avg_duration": round(w.get_avg_trade_duration(), 1),
                "active_ops": len(w.positions),
                "total_ops": len(w.trades_history),
                "paused": getattr(strat, 'paused', False),
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
                "start_time": getattr(w, 'start_time', 0),
                "active_wins": active_wins,
                "active_losses": active_losses
            })
            
            # Active Positions
            for op in w.get_positions_status(prices):
                # Normalize for Frontend App.tsx types
                frontend_op = {
                    'id': str(op['id']),
                    'strategy_id': strat_id,
                    'symbol': op['symbol'],
                    'side': op['type'], # Map 'type' to 'side'
                    'size': op['size'],
                    'entry_price': op['avg'], # Map 'avg' to 'entry_price'
                    'current_price': op['mark_price'], # Map 'mark_price' to 'current_price'
                    'pnl': op['pnl_val'], # Map 'pnl_val' to 'pnl'
                    'pnl_pct': op['pnl_pct'],
                    'open_time': w.positions[op['id']].get('entry_time', 0),
                    'dca': op['dca'],
                    'avg_price': op['avg'],
                    'invested': op['margin'],
                    'ts_price': op['ts_price'],
                    'ts_status': op['ts_status']
                }
                all_ops.append(frontend_op)
            
            # History
            for h in w.get_history():
                frontend_hist = {
                    'id': str(h.get('id', 'h')),
                    'strategy_id': strat_id,
                    'symbol': h['symbol'],
                    'side': h.get('type', 'LONG'),
                    'size': h.get('size', 0),
                    'entry_price': h.get('avg_price', 0),
                    'exit_price': h.get('close_price', 0),
                    'final_pnl': h.get('final_pnl', 0),
                    'close_time': h.get('close_time', 0),
                    'entry_time': h.get('entry_time', 0)
                }
                all_history.append(frontend_hist)

        all_history.sort(key=lambda x: x.get('close_time', 0), reverse=True)

        return {
            "type": "full_state",
            "global_equity": round(global_equity, 2),
            "strategies": strategies_data,
            "operations": all_ops,
            "history": all_history, # Full history for frontend filtering
            "market": self.get_market_monitor(prices),
            "market_trend": self.strategy.global_trend,
            "logs": self.get_latest_logs(50)
        }

    def get_latest_logs(self, n=50):
        """Reads the last N lines from the bot activity log."""
        log_path = config.LOG_FILE
        if not os.path.exists(log_path): return []
        try:
            with open(log_path, 'r') as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-n:]]
        except:
            return []

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
            # logging.debug(f"WebBotManager: Broadcasting market_tick for {len(data)} symbols")
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

@app.post("/api/auth/login")
async def login(request: Request, response: Response):
    data = await request.json()
    password = data.get("password", "").strip()
    
    # Secure Password from User
    if password == config.ADMIN_PASSWORD:
        from kraken_bot.auth import create_admin_token, COOKIE_NAME, COOKIE_EXPIRY_DAYS
        token = create_admin_token()
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=COOKIE_EXPIRY_DAYS * 24 * 3600,
            httponly=True,
            samesite="lax",
            secure=False # Set to True if using HTTPS
        )
        return {"status": "success", "role": "admin"}
    else:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")

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
        
    return {"status": "success", "action": action, "strategy": strategy_id}

@app.post("/api/control/close_trade/{strategy_id}/{trade_id}")
async def close_trade(strategy_id: str, trade_id: str, request: Request, response: Response):
    # IDs are sent as strings from frontend, but stored as ints in PaperWallet
    try:
        trade_id_int = int(trade_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de operación inválido.")
    role = get_client_role(request, response)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede realizar esta acción.")
    
    if strategy_id not in manager.strategy.strategies:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")
    
    strat = manager.strategy.strategies[strategy_id]
    wallet = strat.wallet
    
    if trade_id_int not in wallet.positions:
        raise HTTPException(status_code=404, detail="Operación no encontrada.")
    
    pos = wallet.positions[trade_id_int]
    symbol = pos['symbol']
    
    # Get current market price
    state = manager.strategy.market_state.get(symbol)
    if not state:
        raise HTTPException(status_code=400, detail=f"No hay datos de mercado para {symbol}")
        
    price = state['current_candle']['close'] if state['current_candle'] else (state['candles'][-1]['close'] if state['candles'] else 0.0)
    
    if price == 0:
         raise HTTPException(status_code=400, detail=f"Precio no disponible para {symbol}")

    success = wallet.close_position(trade_id_int, price)
    
    if success:
        return {"status": "success", "message": f"Operación {trade_id} cerrada a {price}"}
    else:
        raise HTTPException(status_code=500, detail="Error al cerrar la operación.")

@app.post("/api/control/close_positive_trades")
async def close_positive_trades(request: Request, response: Response):
    role = get_client_role(request, response)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede realizar esta acción.")
    
    closed_count = 0
    for strat_id, strat in manager.strategy.strategies.items():
        wallet = strat.wallet
        # Get current prices for this strategy's symbols
        prices = {s: (st['current_candle']['close'] if st['current_candle'] else (st['candles'][-1]['close'] if st['candles'] else 0.0)) 
                  for s, st in manager.strategy.market_state.items()}
        
        # Iterate over active positions
        for t_id in list(wallet.positions.keys()):
            pos = wallet.positions[t_id]
            symbol = pos['symbol']
            price = prices.get(symbol, 0)
            if price == 0: continue
            
            # Calculate net PnL
            # gross_pnl = (price - avg_price) * size (for LONG)
            pnl_gross = wallet.calc_pnl_gross(t_id, price)
            fees_paid = pos.get('itemized_fees', 0)
            fee_rate = config.FEE_SPOT_TAKER
            exit_fee = pos['size'] * price * fee_rate
            net_pnl = pnl_gross - fees_paid - exit_fee
            if net_pnl > 0:
                if wallet.close_position(t_id, price):
                    closed_count += 1
                    
    return {"status": "success", "closed_count": closed_count}

@app.post("/api/control/reload")
async def reload_strategies(request: Request, response: Response):
    role = get_client_role(request, response)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede realizar esta acción.")
    
    new_count = manager.strategy.reload_strategies()
    return {"status": "success", "new_strategies_loaded": new_count}

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

# Serve built frontend
app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("kraken_bot.web_server.server:app", host="0.0.0.0", port=8000, reload=False)
