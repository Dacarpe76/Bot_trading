import asyncio
import logging
import json
import os
import time
from kraken_bot import config
from kraken_bot.connector import KrakenConnector
from kraken_bot.processor import StrategyProcessor
from kraken_bot.reporter import TelegramReporter

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_core.log"),
        logging.StreamHandler()
    ]
)

DATA_FILE = "data/bot_state.json"
os.makedirs("data", exist_ok=True)

class StandaloneBot:
    def __init__(self):
        self.loop = None
        self.queue = None
        self.connector = None
        self.strategy = StrategyProcessor()
        self.reporter = TelegramReporter()
        self.running = True

    async def start(self):
        logging.info("Bot Core: Starting...")
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        
        # Initialize Connector
        self.connector = KrakenConnector(
            symbols=config.SYMBOLS,
            channels=["trade"],
            output_queue=self.queue
        )

        # Step 1: Pre-load History
        logging.info("Bot Core: Fetching History...")
        await self.loop.run_in_executor(None, self.strategy.fetch_all_history)
        
        # Step 2: Start Workers
        self.loop.create_task(self.connector.connect())
        self.loop.create_task(self.strategy.process_queue(self.queue))
        self.loop.create_task(self.state_dumper_loop())
        
        self.reporter.send_message("🤖 *Bot Core Online* \nModo Desacoplado iniciado.")
        
        # Keep alive
        while self.running:
            await asyncio.sleep(10)

    async def state_dumper_loop(self):
        """Periodically dumps the full state to a JSON file."""
        logging.info("Bot Core: State Dumper Started.")
        while self.running:
            try:
                start_time = time.time()
                data = self.get_full_state()
                
                # Atomic write to avoid partial reads
                temp_file = f"{DATA_FILE}.tmp"
                with open(temp_file, 'w') as f:
                    json.dump(data, f)
                os.rename(temp_file, DATA_FILE)
                
                # logging.debug(f"State saved in {time.time() - start_time:.4f}s")
            except Exception as e:
                logging.error(f"State Dump Error: {e}")
            
            await asyncio.sleep(1.0) # 1Hz update rate

    def get_full_state(self):
        """Compiles the complete state (Same logic as old WebBotManager)."""
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
                "name": strat_id,
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
            "timestamp": time.time(),
            "global_equity": round(global_equity, 2),
            "strategies": strategies_data,
            "operations": all_ops,
            "history": all_history[:5000],
            "market": self.get_market_monitor(prices)
        }

    def get_market_monitor(self, prices):
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

if __name__ == "__main__":
    bot = StandaloneBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logging.info("Bot Core: Stopping...")
