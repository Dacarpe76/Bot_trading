import asyncio
import logging
import pandas as pd
import numpy as np
import datetime
import requests
import ta
import time
import math
from kraken_bot import config
# from kraken_bot import sunday_data_fetch   # Legacy if any

from kraken_bot.paper_wallet import PaperWallet
from kraken_bot import strategies
from kraken_bot import scheduler_strategies
from kraken_bot.reporter import TelegramReporter

class StrategyProcessor:
    def __init__(self):
        logging.info("StrategyProcessor: Initializing...")
        # Initialize 4 Strategies with their own Wallets
        # Strategies Initialization (Descriptive Names)
        self.strategies = {}
        
        # --- Scheduled Strategies (Macro & Sim) ---
        self.macro_strategy = scheduler_strategies.KrakenMacroStrategy()
        self.five_cubes_sim = scheduler_strategies.FiveCubesSimStrategy()
        self.news_strategy = scheduler_strategies.KrakenNewsStrategy()
        self.last_scheduler_date = None # Track last run DATE
        
        self.reporter = TelegramReporter()
        self.last_summary_date = None
        self.last_tech_summary_date = None

        
        # --- Aggressive Variants ---
        # 1. Aggressive (Mixed)
        w1 = PaperWallet("Aggressive", initial_balance=500.0, capital_limit_pct=config.CAPITAL_LIMIT_AGGRESSIVE, display_name="Aggressive Sniper")
        self.strategies['Aggressive'] = strategies.StrategyAggressive(w1, allowed_sides=['LONG', 'SHORT'])
        self.strategies['Aggressive'].on_event = self.handle_strategy_event

        # 2. Aggressive Cent
        w2 = PaperWallet("AggrCent", initial_balance=500.0, capital_limit_pct=config.CAPITAL_LIMIT_PCT, display_name="Aggressive Cent")
        self.strategies['AggrCent'] = strategies.StrategyAggressiveCent(w2)
        self.strategies['AggrCent'].on_event = self.handle_strategy_event

        

        
        # 5. NetScalp (Fixed Net + Safety)
        w5 = PaperWallet("NetScalp", initial_balance=500.0, capital_limit_pct=config.CAPITAL_LIMIT_PCT, display_name="NetScalp DCA")
        self.strategies['NetScalp'] = strategies.StrategyNetScalpDCA(w5)
        self.strategies['NetScalp'].on_event = self.handle_strategy_event

        # 6. RollingDCA V3
        w6 = PaperWallet("RollingDCA_v3", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA v3")
        self.strategies['RollingDCA_v3'] = strategies.StrategyRollingDCAV3(w6)
        self.strategies['RollingDCA_v3'].on_event = self.handle_strategy_event

        
        # 8. HybridElite (Best of Both Worlds) - New 500 EUR Wallet
        w8 = PaperWallet("HybridElite", initial_balance=500.0, capital_limit_pct=None, display_name="Hybrid Elite")
        self.strategies['HybridElite'] = strategies.StrategyHybridElite(w8)
        self.strategies['HybridElite'].on_event = self.handle_strategy_event
        
        w9 = PaperWallet("RollingDCA", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA")
        self.strategies['RollingDCA'] = strategies.StrategyRollingDCA(w9)
        self.strategies['RollingDCA'].on_event = self.handle_strategy_event
        


        # 11. RollingDCA v2 (Robust Recovery) - 500 EUR
        w11 = PaperWallet("RollingDCA_v2", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA v2")
        self.strategies['RollingDCA_v2'] = strategies.StrategyRollingDCAV2(w11)
        self.strategies['RollingDCA_v2'].on_event = self.handle_strategy_event


        # 13. RollingDCA Short v1 - 500 EUR 
        w13 = PaperWallet("Rol_dca_sh_v1", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA Short")
        self.strategies['Rol_dca_sh_v1'] = strategies.StrategyRollingDCAShort(w13)
        self.strategies['Rol_dca_sh_v1'].on_event = self.handle_strategy_event

        # 14. RollingDCA Short v2
        w14 = PaperWallet("Rol_dca_sh_v2", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA Short v2")
        self.strategies['Rol_dca_sh_v2'] = strategies.StrategyRollingDCAShortV2(w14)
        self.strategies['Rol_dca_sh_v2'].on_event = self.handle_strategy_event

        # 15. RollingDCA Short v3
        w15 = PaperWallet("Rol_dca_sh_v3", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA Short v3")
        self.strategies['Rol_dca_sh_v3'] = strategies.StrategyRollingDCAShortV3(w15)
        self.strategies['Rol_dca_sh_v3'].on_event = self.handle_strategy_event


        
        # 16. Aspiradora (Sniper Extreme) - 500 EUR 
        w16 = PaperWallet("Aspiradora", initial_balance=500.0, capital_limit_pct=None)
        self.strategies['Aspiradora'] = strategies.StrategyAspiradora(w16)
        self.strategies['Aspiradora'].on_event = self.handle_strategy_event

        # 17. Hormiga / Grinder (High Frequency) - 500 EUR
        w17 = PaperWallet("Hormiga", initial_balance=500.0, capital_limit_pct=None)
        self.strategies['Hormiga'] = strategies.StrategyHormiga(w17)
        self.strategies['Hormiga'].on_event = self.handle_strategy_event

        # 18. NetScalp Rolling (Fixed Profit + Granular DCA) - 500 EUR
        w18 = PaperWallet("NetScalp_Rolling", initial_balance=500.0, capital_limit_pct=config.CAPITAL_LIMIT_PCT)
        self.strategies['NetScalp_Rolling'] = strategies.StrategyNetScalpRolling(w18)
        self.strategies['NetScalp_Rolling'].on_event = self.handle_strategy_event

        # 19. RollingDCA Evolution (Anti-Trap) - 500 EUR 
        w19 = PaperWallet("RollingDCA_Evolution", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA Evolution")
        self.strategies['RollingDCA_Evolution'] = strategies.StrategyRollingDCAEvolution(w19)
        self.strategies['RollingDCA_Evolution'].on_event = self.handle_strategy_event

        w20 = PaperWallet("RollingDCA_Inmortal", initial_balance=500.0, capital_limit_pct=None, display_name="Rolling DCA Inmortal")
        self.strategies['RollingDCA_Inmortal'] = strategies.StrategyRollingDCAInmortal(w20)
        self.strategies['RollingDCA_Inmortal'].on_event = self.handle_strategy_event

        # --- Re-enabled Legacy Bots for History/Operations Visibility ---
        w21_old = PaperWallet("KrakenEvent", initial_balance=500.0, capital_limit_pct=None, display_name="Kraken Sentinel 2026")
        self.strategies['KrakenEvent'] = strategies.StrategyKrakenEvent(w21_old)
        self.strategies['KrakenEvent'].on_event = self.handle_strategy_event

        w22_old = PaperWallet("SentinelTurbo", initial_balance=500.0, capital_limit_pct=None, display_name="Kraken Sentinel Turbo")
        self.strategies['SentinelTurbo'] = strategies.StrategySentinelTurbo(w22_old)
        self.strategies['SentinelTurbo'].on_event = self.handle_strategy_event

        # 23. Antigravity (Sniper & 25-level DCA Defense) - 500 EUR
        w23 = PaperWallet("Antigravity", initial_balance=500.0, capital_limit_pct=None, display_name="Antigravity Sniper")
        self.strategies['Antigravity'] = strategies.StrategyAntigravity(w23)
        self.strategies['Antigravity'].on_event = self.handle_strategy_event
        
        # 24. Saint-Grial (Master Adaptive Mode) - 500 EUR
        w24 = PaperWallet("SaintGrial", initial_balance=500.0, capital_limit_pct=None, display_name="Saint-Grial Master")
        self.strategies['SaintGrial'] = strategies.StrategySaintGrial(w24)
        self.strategies['SaintGrial'].on_event = self.handle_strategy_event

        # 25. Saint-Grial PRO X3 (Unified Execution Protocol) - 500 EUR
        w25 = PaperWallet("SaintGrialProX3", initial_balance=500.0, capital_limit_pct=None, display_name="Saint-Grial PRO X3")
        self.strategies['SaintGrialProX3'] = strategies.StrategySaintGrialProX3(w25)
        self.strategies['SaintGrialProX3'].on_event = self.handle_strategy_event
        
        # 26. VectorFlujo_V1 (Macro sniper & 15m EMA200 Defense) - 500 EUR
        w26 = PaperWallet("VectorFlujo_V1", initial_balance=500.0, capital_limit_pct=None, display_name="Vector Flujo V1")
        self.strategies['VectorFlujo_V1'] = strategies.StrategyVectorFlujoV1(w26)
        self.strategies['VectorFlujo_V1'].on_event = self.handle_strategy_event
        
        # Inyectar referencia al procesador para que VectorFlujo pueda pedir status de otros
        self.strategies['VectorFlujo_V1'].processor = self

        # --- Short-Only Scalping Variations to reach 25 ---
        
        # 22. Aggressive Short
        w22 = PaperWallet("Aggressive_Short", initial_balance=500.0, capital_limit_pct=config.CAPITAL_LIMIT_AGGRESSIVE)
        self.strategies['Aggressive_Short'] = strategies.StrategyAggressive(w22, allowed_sides=['SHORT'])
        self.strategies['Aggressive_Short'].on_event = self.handle_strategy_event

        # 23. AggrCent Short
        w23_s = PaperWallet("AggrCent_Short", initial_balance=500.0, capital_limit_pct=config.CAPITAL_LIMIT_PCT)
        self.strategies['AggrCent_Short'] = strategies.StrategyAggressiveCent(w23_s, allowed_sides=['SHORT'])
        self.strategies['AggrCent_Short'].on_event = self.handle_strategy_event

        # 24. Aspiradora Short
        w24_s = PaperWallet("Aspiradora_Short", initial_balance=500.0, capital_limit_pct=None)
        self.strategies['Aspiradora_Short'] = strategies.StrategyAspiradora(w24_s, allowed_sides=['SHORT'])
        self.strategies['Aspiradora_Short'].on_event = self.handle_strategy_event

        # 25. Hormiga Short
        w25_s = PaperWallet("Hormiga_Short", initial_balance=500.0, capital_limit_pct=None)
        self.strategies['Hormiga_Short'] = strategies.StrategyHormiga(w25_s, allowed_sides=['SHORT'])
        self.strategies['Hormiga_Short'].on_event = self.handle_strategy_event
        
        # Multi-Coin State: { 'XBT/EUR': { 'candles': [], 'current_candle': None, 'cvd': 0.0, 'cols': ... } }
        self.market_state = {}
        self.btc_history = [] # To track price for crash detection
        for sym in config.SYMBOLS:
            self.market_state[sym] = {
                'candles': [],
                'candles_5m': [], # New 5m storage
                'candles_15m': [], # New 15m storage
                'current_candle': None,
                'current_candle_5m': None, # New
                'current_candle_15m': None, # New
                'cvd': 0.0,
                'indicators': {} # Store last calc indicators
            }
        
        # UI Callbacks
        self.on_candle_closed = None # format: (symbol, candle_dict)
        self.on_data_update = None   # format: (market_data_list)
        self.on_monitor_update = None # New: List of {sym, price, rsi}

        # Pre-load History
        # self.fetch_all_history() # Moved to explicit call in WorkerThread to avoid blocking init
        
        self.last_monitor_update = 0 # Throttle Control
        self.global_trend = "NEUTRAL"
        logging.info("StrategyProcessor: Initialization Complete (History fetch pending).")

    def reload_strategies(self):
        """Scans for new wallet_state_*.json files and registers them if not already active."""
        import glob
        import os
        
        logging.info("StrategyProcessor: Scanning for new strategies...")
        state_files = glob.glob("wallet_state_*.json")
        new_count = 0
        
        for file_path in state_files:
            # Extract strategy ID from filename: wallet_state_{ID}.json
            strat_id = file_path.replace("wallet_state_", "").replace(".json", "")
            
            if strat_id in self.strategies or strat_id == "" or strat_id == "legacy":
                continue
                
            try:
                logging.info(f"StrategyProcessor: Detected new wallet file: {file_path}. Registering {strat_id}...")
                
                # Create PaperWallet - it will auto-load the state from the file
                w = PaperWallet(strat_id, initial_balance=500.0, capital_limit_pct=None)
                
                # Determine which strategy class to use based on id or default to a safe one
                # If it's a known legacy bot name, use the corresponding class
                if strat_id == "KrakenEvent":
                    self.strategies[strat_id] = strategies.StrategyKrakenEvent(w)
                elif strat_id == "SentinelTurbo":
                    self.strategies[strat_id] = strategies.StrategySentinelTurbo(w)
                elif strat_id == "SaintGrial":
                    self.strategies[strat_id] = strategies.StrategySaintGrial(w)
                elif "RollingDCA" in strat_id:
                    self.strategies[strat_id] = strategies.StrategyRollingDCAV2(w)
                else:
                    # Generic strategy to at least visualize positions/history
                    # StrategyAspiradora is relatively safe as it has strict entry conditions
                    self.strategies[strat_id] = strategies.StrategyAspiradora(w)
                
                self.strategies[strat_id].on_event = self.handle_strategy_event
                new_count += 1
                logging.info(f"StrategyProcessor: Successfully registered new strategy: {strat_id}")
                
            except Exception as e:
                logging.error(f"StrategyProcessor: Failed to register {strat_id}: {e}")
                
        return new_count

    def fetch_all_history(self):
        """Fetches history for all configured symbols."""
        for sym in config.SYMBOLS:
             self.fetch_history_for_symbol(sym)

    def fetch_history_for_symbol(self, symbol):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logging.info(f"Fetching history for {symbol} (Attempt {attempt+1})...")
                # Kraken Pair Name formatting (sometimes needs mapping, try raw)
                # symbol like XBT/EUR -> XBTEUR? Kraken API usually flexible or requires altname.
                # Let's try sending as is, if fails connection usually handles it.
                # REST generic: pair=XBTEUR 
                query_symbol = symbol.replace('/', '')
                url = f"{config.KRAKEN_REST_URL}/OHLC?pair={query_symbol}&interval={config.TIMEFRAME}"
                resp = requests.get(url, timeout=5) # Reduced timeout to avoid hang perception
                data = resp.json()
                
                if data.get('error'):
                    logging.error(f"Error fetching history for {symbol}: {data['error']}")
                    # If error is rate limit or temp, maybe retry? For now return.
                    # If it's a real API error, don't retry.
                    return

                res = data['result']
                # Key is variable
                pair_key = list(res.keys())[0] if res else None
                
                if pair_key:
                    ohlc = res[pair_key]
                    state = self.market_state[symbol]
                    
                    for candle in ohlc[-300:]: 
                        timestamp = float(candle[0])
                        c = {
                            'timestamp': datetime.datetime.fromtimestamp(timestamp),
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': float(candle[6]),
                            'trades': int(candle[7]),
                            'symbol': symbol
                        }
                        state['candles'].append(c)
                        
                        # Warm up 5m indicators
                        self.update_5m_candle(symbol, c)
                    
                    logging.info(f"Loaded {len(state['candles'])} candles for {symbol}.")
                    return # Success
                    
            except Exception as e:
                logging.info(f"Failed history fetch {symbol} (Attempt {attempt+1}): {e}")
                time.sleep(2 * (attempt + 1)) # Backoff
        
        logging.error(f"Given up fetching history for {symbol} after {max_retries} attempts.")

    async def process_queue(self, input_queue):
        """Main loop consuming data from WebSocket."""
        logging.info("Strategy Processor Started (Multi-Coin).")
        
        # Initial Scheduler Check (Run on startup if needed, or wait for next 00:00)
        # User said "evaluada cada 24 horas". Let's run checks in loop.
        self.scheduler_interval = 60 # Check every minute
        self.last_scheduler_check = time.time() # Delay first check
        
        while True:
            # --- Scheduler Check ---
            now_ts = time.time()
            if now_ts - self.last_scheduler_check > self.scheduler_interval:
                self.check_scheduled_tasks()
                self.last_scheduler_check = now_ts

            data = await input_queue.get()
            # Connector sends (symbol, trades_list)
            # logging.info(f"DEBUG: Msg received: {data}") # Too verbose?
            try:
                if isinstance(data, tuple) and len(data) == 2:
                    symbol, trades_list = data
                    
                    if symbol in self.market_state:
                         # logging.info(f"DEBUG: Processing {len(trades_list)} trades for {symbol}")
                         for trade in trades_list:
                             # ... process trade ...
                             self.process_trade(symbol, trade)
                
                # Legacy support or error handling
                elif isinstance(data, list):
                     logging.warning(f"Processor received raw list, expected tuple: {data}")
            except Exception as e:
                logging.error(f"Error processing data: {e}")
                     
            except Exception as e:
                logging.error(f"Error processing data: {e}")
            
            input_queue.task_done()

    def process_trade(self, symbol, trade):
        try:
            if not isinstance(trade, (list, tuple)): return
            price = float(trade[0])
            volume = float(trade[1])
            timestamp = float(trade[2])
            side = trade[3] # 'b' or 's'
            
            state = self.market_state[symbol]
            dt = datetime.datetime.fromtimestamp(timestamp)
            minute = dt.replace(second=0, microsecond=0)
            
            # CVD
            if side == 'b': state['cvd'] += volume
            else: state['cvd'] -= volume

            # Candle Management
            if state['current_candle'] is None or state['current_candle']['timestamp'] != minute:
                if state['current_candle'] is not None:
                    self.finalize_candle(symbol, state['current_candle'])
                
                state['current_candle'] = {
                    'timestamp': minute,
                    'symbol': symbol,
                    'open': price, 'high': price, 'low': price, 'close': price,
                    'volume': 0.0, 'trades': 0
                }
            
            c = state['current_candle']
            c['high'] = max(c['high'], price)
            c['low'] = min(c['low'], price)
            c['close'] = price
            c['volume'] += volume
            c['trades'] += 1
            
            # Update Larger Timeframes
            self.update_5m_candle(symbol, c)
            self.update_15m_candle(symbol, c)
            
            # Real-time Checks (Multi-Strategy)
            # 1. Update Global Trend (BTC Watcher)
            if symbol == 'XBT/EUR':
                # Persistent history for 15m crash detection
                self.btc_history.append({'time': timestamp, 'price': price})
                # Clean old history (keep > 15m)
                self.btc_history = [h for h in self.btc_history if timestamp - h['time'] <= 960] # 16m buffer
                
                # Detect 15m crash (> 2%)
                if self.btc_history:
                    oldest_btc = self.btc_history[0]
                    if (price - oldest_btc['price']) / oldest_btc['price'] <= -0.02:
                        if self.global_trend != "BTC_CRASH":
                             logging.warning(f"StrategyProcessor: BTC CRASH DETECTED! (>2% drop in 15m). Suspending Layer 1 & 2 opens.")
                             self.global_trend = "BTC_CRASH"
                    elif self.global_trend == "BTC_CRASH" and (price - oldest_btc['price']) / oldest_btc['price'] > -0.015:
                             # Slight recovery to exit crash mode
                             self.global_trend = "NEUTRAL"

                c_open = c.get('open', price)
                if c_open > 0:
                    pct_change = (price - c_open) / c_open
                    if pct_change < -0.0025: # -0.25% in 1 minute
                        if self.global_trend != "BTC_CRASH": self.global_trend = "DUMP"
                    elif pct_change > 0.001: # Recovery or Bullish move
                        if self.global_trend not in ["BTC_CRASH", "DUMP"]:
                            self.global_trend = "BULLISH"
                        else:
                            self.global_trend = "NEUTRAL"
                    else:
                        if self.global_trend not in ["DUMP", "BTC_CRASH", "BULLISH"]:
                            if pct_change > -0.0010:
                                 self.global_trend = "NEUTRAL"

            # 2. Inject Trend into Indicators
            current_indicators = state['indicators'].copy() # Copy to avoid polluting persistent state
            current_indicators['market_trend'] = self.global_trend
            current_indicators['btc_15m_crash'] = (self.global_trend == "BTC_CRASH")
            
            # Inject 5m Data and Global Minimum RSI
            all_rsis = {}
            for s, st in self.market_state.items():
                r = st.get('indicators_5m', {}).get('rsi', 100) # Default to 100 if no data
                all_rsis[s] = r
            
            min_rsi_val = min(all_rsis.values()) if all_rsis else 100
            
            if 'indicators_5m' in state:
                ind_5 = state['indicators_5m']
                current_indicators['rsi_5m'] = ind_5.get('rsi', 50.0)
                current_indicators['close_5m'] = ind_5.get('close', 0.0)
                current_indicators['timestamp_5m'] = ind_5.get('timestamp')
            
            if 'indicators_15m' in state:
                ind_15 = state['indicators_15m']
                current_indicators['ema200_15m'] = ind_15.get('ema200', 0.0)
                current_indicators['adx_15m'] = ind_15.get('adx', 0.0)
                current_indicators['close_15m'] = ind_15.get('close', 0.0)
            
            # Identify if this symbol is the global minimum RSI
            current_indicators['is_global_min_rsi'] = (current_indicators.get('rsi_5m', 100) <= min_rsi_val)
            current_indicators['global_min_rsi'] = min_rsi_val
            
            for strat in self.strategies.values():
                strat.on_tick(symbol, price, current_indicators)
            
            # Legacy calls removed (check_dynamic_exit)
            
            # Emit Real-time Monitor Signal (optional throttle)
            # We will gather all symbols prices and emit? Or just emit this one?
            # GUI wants a list of all coins.
            # Limit Monitor Updates to 1s to prevent GUI freeze
            now = time.time()
            if self.on_monitor_update and (now - getattr(self, 'last_monitor_update', 0) > 1.0):
                monitor_data = []
                for s, st in self.market_state.items():
                    # Last close or current
                    p = st['current_candle']['close'] if st['current_candle'] else 0.0
                    if p == 0.0 and st['candles']: p = st['candles'][-1]['close']
                    
                    # Extract Indicators
                    ind = st['indicators']
                    
                    width = ind.get('Bollinger_Width', 0.0)
                    
                    # Use FULL CASH of properties if available
                    # Use FULL CASH of properties if available
                    if 'last_analysis' in st:
                         data = st['last_analysis'].copy()
                         # Override with live price & indicators
                         data['Price'] = str(p)
                         data['price'] = p
                         data['symbol'] = s
                         # FORCE Live Indicators
                         data['rsi'] = ind.get('rsi', data.get('RSI_14', 0.0))
                         data['vrel'] = ind.get('vrel', 0.0)
                         data['err'] = ind.get('err', 0.0)
                    else:
                        # Fallback
                        data = {
                            'symbol': s, 
                            'price': p, 
                            'rsi': ind.get('rsi', 0.0),
                            'vrel': ind.get('vrel', 0.0),
                            'err': ind.get('err', 0.0),
                            # Use current live volume (1m) or accumulated? 
                            # Users prefer seeing the candle filling up.
                            # `current_candle` is the live 1m candle.
                            'volume': st['current_candle']['volume'] if st['current_candle'] else 0.0
                        }
                    monitor_data.append(data)
                
                # logging.info(f"Processor: Emit Monitor {len(monitor_data)}")
                self.on_monitor_update(monitor_data)
                self.last_monitor_update = now
        except Exception as e:
            logging.error(f"Trade Parse Error {symbol}: {e}")

    def get_strategies_summary(self):
        """Returns a snapshot of performance for specific strategies."""
        summary = {}
        for s_id in ['Hormiga', 'KrakenEvent', 'SentinelTurbo']:
            if s_id in self.strategies:
                s = self.strategies[s_id]
                w = s.wallet
                pnl = w.balance_eur - 500.0 # Assuming 500 initial
                # Add unrealized using live prices
                for tid, pos in w.positions.items():
                    symbol = pos['symbol']
                    price = 0.0
                    if symbol in self.market_state:
                         st = self.market_state[symbol]
                         if st['current_candle']: price = st['current_candle']['close']
                         elif st['candles']: price = st['candles'][-1]['close']
                    if price > 0:
                        pnl += w.calc_pnl_gross(tid, price)
                
                summary[s_id] = f"{pnl:+.2f}€"
        return summary

    def handle_strategy_event(self, event_type, strat_id, symbol, price, indicators):
        """Called by strategies when a trade event occurs."""
        logging.info(f"Strategy Event: {event_type} {strat_id} {symbol} @ {price}")
        
        # Log to Rich CSV
        try:

             # Handle Opportunity Logging explicitly
             if event_type == "Opportunity":
                 state = self.market_state.get(symbol)
                 if state:
                     # Create a dummy candle from price if needed, or use current
                     candle = state['current_candle'] or (state['candles'][-1] if state['candles'] else {'close': price})
                     self.log_opportunity(symbol, candle, state, f"Strategy_{strat_id}", "Detected")
                 return

             # Calculate State Metrics fresh or fetch last?
             # Trade happens live. 5m candles might be forming.
             # Ideally we take the last updated state['candles'] + current partial?
             # For simplicity and consistence with 'Purchase Moment', let's use the current available history.
             state = self.market_state[symbol]
             
             # Calculate Data
             raw_ind = self.calculate_technical_indicators(symbol, state)
             if not raw_ind: return
             
             # Format for CSV
             row_dict = raw_ind
             if not row_dict: return
             
             # Overwrite/Add Event Specifics
             row_dict['Strategy_ID'] = strat_id
             row_dict['Event'] = event_type
             row_dict['Price'] = f"{price:.4f}" # Override Close with execution price?
             # Keep Candle Date or Use Now? Now is better for Event.
             row_dict['Timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
             
             self._write_rich_csv(row_dict)
             
        except Exception as e:
            logging.error(f"Error logging rich event {symbol}: {e}")

    def calculate_technical_indicators(self, symbol, state):
        """Calculates rich indicators returning typed values for logic."""
        df = pd.DataFrame(state['candles'])
        if len(df) < 50: return None

        # Ensure numeric
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')

        # --- Volatility ---
        df['ATR_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
        
        # Bollinger
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['Bollinger_Upper'] = bb.bollinger_hband()
        df['Bollinger_Lower'] = bb.bollinger_lband()
        df['Bollinger_Width'] = bb.bollinger_wband()

        # --- Volume Advanced ---
        # MFI 14
        df['MFI_14'] = ta.volume.MFIIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()
        # OBV
        df['OBV'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
        # Volume Mean 20
        df['Volume_Mean_20'] = df['volume'].rolling(20).mean()

        # --- Oscillation ---
        # Stochastic (14, 3, 3) 
        stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal()
        
        # Stochastic RSI (14) - New Intelligent Indicator
        stoch_rsi = ta.momentum.StochRSIIndicator(df['close'], window=14)
        df['Stoch_RSI_K'] = stoch_rsi.stochrsi_k()
        df['Stoch_RSI_D'] = stoch_rsi.stochrsi_d() # Optional, keeping K is main
        
        # ADX 14
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['ADX_14'] = adx_ind.adx()

        # --- Trend Moving Averages ---
        # EMA 50 (Short/Medium Trend)
        df['EMA_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        # EMA 200 (Major Trend)
        df['EMA_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
        
        # Distance to EMA 200 Pct
        df['Dist_EMA200_Pct'] = (df['close'] - df['EMA_200']) / df['EMA_200']
        
        # --- Derived Decision Logic (Simulated) ---
        # Decision_Log: "Trend_Bullish" if Price > EMA50, "Trend_Bearish" if Price < EMA50
        # Current_Trend_1h: "Bullish" if Price > EMA200, "Bearish" if Price < EMA200 (Simplified alignment)
        
        def get_decision(row):
            if pd.isna(row['EMA_50']): return "Monitoring"
            if row['close'] > row['EMA_50']: return "Trend_Bullish"
            return "Trend_Bearish"

        def get_trend_1h(row):
            if pd.isna(row['EMA_200']): return "Neutral"
            if row['close'] > row['EMA_200']: return "Bullish"
            return "Bearish"

        df['Decision_Log'] = df.apply(get_decision, axis=1)
        df['Current_Trend_1h'] = df.apply(get_trend_1h, axis=1)

        # --- Structure (Price Action) ---
        # Candle Body Size: abs(Open - Close)
        df['Candle_Body_Size'] = (df['open'] - df['close']).abs()
        # Upper Wick: High - max(Open, Close)
        df['Upper_Wick_Size'] = df['high'] - df[['open', 'close']].max(axis=1)
        # Lower Wick: min(Open, Close) - Low
        df['Lower_Wick_Size'] = df[['open', 'close']].min(axis=1) - df['low']
        # Wick Body Ratio
        df['Wick_Body_Ratio'] = (df['Upper_Wick_Size'] + df['Lower_Wick_Size']) / df['Candle_Body_Size'].replace(0, 0.00001)

        # --- Levels (Pivot Points - Auto Rolling) ---
        rolling_high_24h = df['high'].rolling(1440, min_periods=1).max()
        rolling_low_24h = df['low'].rolling(1440, min_periods=1).min()
        pp = (rolling_high_24h + rolling_low_24h + df['close']) / 3
        df['Pivot_P'] = pp
        df['Pivot_R1'] = (2 * pp) - rolling_low_24h
        df['Pivot_S1'] = (2 * pp) - rolling_high_24h
        df['Pivot_R2'] = pp + (rolling_high_24h - rolling_low_24h)
        df['Pivot_S2'] = pp - (rolling_high_24h - rolling_low_24h)

        # --- Reference Metrics ---
        df['EMA_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
        df['Dist_EMA200_Pct'] = (df['close'] - df['EMA_200']) / df['EMA_200']

        # --- Strategy State ---
        # Current Trend 1h
        trend = "Neutral"
        if len(df) > 60:
            delta = df['close'].iloc[-1] - df['close'].iloc[-61]
            trend = "Bullish" if delta > 0 else "Bearish"
        
        # Fib Zone
        fib_level = 0.0
        if len(df) > 10:
            window = 200
            recent = df.tail(window)
            local_high = recent['high'].max()
            local_low = recent['low'].min()
            rng = local_high - local_low
            if rng > 0:
                fib_level = (df['close'].iloc[-1] - local_low) / rng # 0 to 1 position
            
        # --- Last Row Extraction ---
        last = df.iloc[-1]
        
        # Format Data
        row_dict = {
            'Timestamp': str(last['timestamp']), # May be overwritten by event time
            'Symbol': symbol,
            'Price': f"{last['close']:.4f}", # May be overwritten
            'Open': f"{last['open']:.4f}",
            'High': f"{last['high']:.4f}",
            'Low': f"{last['low']:.4f}",
            'Close': f"{last['close']:.4f}",
            'Volume': f"{last['volume']:.2f}",
            
            # Computed
            'ATR_14': f"{last.get('ATR_14', np.nan):.4f}",
            'Bollinger_Upper': f"{last.get('Bollinger_Upper', np.nan):.4f}",
            'Bollinger_Lower': f"{last.get('Bollinger_Lower', np.nan):.4f}",
            'Bollinger_Width': f"{last.get('Bollinger_Width', np.nan):.4f}",
            
            'MFI_14': f"{last.get('MFI_14', np.nan):.2f}",
            'OBV': f"{last.get('OBV', np.nan):.2f}",
            'Volume_Mean_20': f"{last.get('Volume_Mean_20', np.nan):.2f}",
            
            'Stoch_K': f"{last.get('Stoch_K', np.nan):.2f}",
            'Stoch_D': f"{last.get('Stoch_D', np.nan):.2f}",
            'Stoch_RSI_K': f"{last.get('Stoch_RSI_K', np.nan):.2f}",
            'ADX_14': f"{last.get('ADX_14', np.nan):.2f}",
            
            'Candle_Body_Size': f"{last.get('Candle_Body_Size', 0):.5f}",
            'Upper_Wick_Size': f"{last.get('Upper_Wick_Size', 0):.5f}",
            'Lower_Wick_Size': f"{last.get('Lower_Wick_Size', 0):.5f}",
            'Wick_Body_Ratio': f"{last.get('Wick_Body_Ratio', 0):.2f}",
            
            'Pivot_P': f"{last.get('Pivot_P', np.nan):.4f}",
            'Pivot_R1': f"{last.get('Pivot_R1', np.nan):.4f}",
            'Pivot_S1': f"{last.get('Pivot_S1', np.nan):.4f}",
            
            'Dist_EMA200_Pct': f"{last.get('Dist_EMA200_Pct', np.nan):.4f}",
            
            'Current_Trend_1h': trend,
            'Fibonacci_Level': f"{fib_level:.3f}", 
            
            # Context / Strategy Signals (From State/Input)
            # 'VRel': passed separately if event
            # 'ERR': passed separately if event
            'PinBar': f"{state.get('last_pinbar', False)}", 
            'Decision_Log': state.get('last_decision', "Init"),
            'Active_Pos_Count': "0", # Placeholder
            'Strategy_ID': "",
            'Event': "Market_Update"
        }
        
        # Add basic indicators from state if available
        ind = state['indicators']
        row_dict['VRel'] = f"{ind.get('vrel', 0.0):.2f}"
        row_dict['ERR'] = f"{ind.get('err', 0.0):.2f}"
        row_dict['Market_Regime'] = state.get('current_regime', 'Unknown')
            
        return row_dict

    def _write_rich_csv(self, row_dict):
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        filename = f"TRH_Research_{date_str}.csv"
        
        # Define Columns (Now includes Event/Strategy_ID)
        headers = [
            'Timestamp','Symbol','Event','Strategy_ID','Price',
            'Open','High','Low','Close','Volume',
            'ATR_14','Bollinger_Upper','Bollinger_Lower','Bollinger_Width',
            'MFI_14','OBV','Volume_Mean_20',
            'Stoch_K','Stoch_D','Stoch_RSI_K','ADX_14',
            'Candle_Body_Size','Upper_Wick_Size','Lower_Wick_Size','Wick_Body_Ratio',
            'Pivot_P','Pivot_R1','Pivot_S1',
            'Dist_EMA200_Pct','Current_Trend_1h','Fibonacci_Level',
            'VRel','ERR','PinBar','Decision_Log','Market_Regime'
        ]
        
        import os
        try:
            file_exists = os.path.isfile(filename)
            is_empty = file_exists and os.path.getsize(filename) == 0
            
            with open(filename, 'a') as f:
                if not file_exists or is_empty:
                    f.write(",".join(headers) + "\n")
                
                vals = [str(row_dict.get(h, "")) for h in headers]
                # Ensure Strategy_ID is empty string for Market Updates in this specific CSV if not applicable, 
                # but 'row_dict' has it blank by default.
                f.write(",".join(vals) + "\n")
        except: pass

    def finalize_candle(self, symbol, candle):
        state = self.market_state[symbol]
        state['candles'].append(candle)
        if len(state['candles']) > 300: state['candles'].pop(0)
        
        if len(state['candles']) > 1:
            prev = state['candles'][-2] # Last completed before this one was just appended? 
            # Wait, verify list state.
            # L456: state['candles'].append(candle)
            # So state['candles'][-1] is the one just finalized (Current closed).
            # state['candles'][-2] is the previous one.
            current = state['candles'][-1]
            prev = state['candles'][-2]
            
            # 1m Bullish Confirmation: Close > Prev High
            is_bullish_conf = current['close'] > prev['high']
            state['indicators']['1m_conf_bullish'] = is_bullish_conf
            
            # Also Short Confirmation (Close < Prev Low)
            is_bearish_conf = current['close'] < prev['low']
            state['indicators']['1m_conf_bearish'] = is_bearish_conf
            
        else:
            state['indicators']['1m_conf_bullish'] = False
            state['indicators']['1m_conf_bearish'] = False
            
        # Log 1m Data (CSV)
        ind = state['indicators']
        vrel = ind.get('vrel', 0.0)
        err = ind.get('err', 0.0)
        # pos_count = len([p for p in self.wallet.positions.values() if p['symbol'] == symbol])
        pos_count = 0 # Placeholder: detailed position info is now in strategy logs
        self.save_market_data(symbol, candle, vrel, err, pos_count)
        
        # Aggregate to 5m -> Analyze
        self.update_5m_candle(symbol, candle)
        
        if self.on_candle_closed:
             self.on_candle_closed(symbol, candle)

    def update_5m_candle(self, symbol, candle_1m):
        state = self.market_state[symbol]
        c5 = state['current_candle_5m']
        
        # Init if None
        if c5 is None:
             base_time = candle_1m['timestamp'].replace(minute=(candle_1m['timestamp'].minute // 5) * 5)
             c5 = {
                 'timestamp': base_time,
                 'symbol': symbol,
                 'open': candle_1m['open'], 
                 'high': candle_1m['high'], 
                 'low': candle_1m['low'], 
                 'close': candle_1m['close'],
                 'volume': candle_1m['volume'], 
                 'trades': candle_1m['trades']
             }
             state['current_candle_5m'] = c5
        else:
             # Check for 5m gap? If candle_1m is far ahead, we might have skipped.
             # Assuming continuous stream for now or reset.
             if (candle_1m['timestamp'] - c5['timestamp']).total_seconds() >= 300:
                  # Force close previous? Or just reset?
                  # Simple Aggregation
                  state['current_candle_5m'] = None
                  self.update_5m_candle(symbol, candle_1m) # Recurse as new
                  return

             c5['high'] = max(c5['high'], candle_1m['high'])
             c5['low'] = min(c5['low'], candle_1m['low'])
             c5['close'] = candle_1m['close']
             c5['volume'] += candle_1m['volume']
             c5['trades'] += candle_1m['trades']
        
        # Check Close Condition: (minute + 1) % 5 == 0?
        # 12:00 -> (0+1)%5=1. No.
        # 12:04 -> (4+1)%5=0. YES.
        
        ts = candle_1m['timestamp']
        if (ts.minute + 1) % 5 == 0:
             state['candles_5m'].append(c5)
             if len(state['candles_5m']) > 100: state['candles_5m'].pop(0)
             
             state['current_candle_5m'] = None
             
             # Analyze 5m
             df_5m = pd.DataFrame(state['candles_5m'])
             logging.info(f"ANALYSIS 5m {symbol}: Closed {c5['timestamp'].strftime('%H:%M')} | Close: {c5['close']}")
             
             # Calculate 5m Indicators (Lightweight)
             try:
                 # Ensure numeric
                 df_5m['close'] = pd.to_numeric(df_5m['close'])
                 
                 if len(df_5m) > 14:
                     rsi_5m = ta.momentum.RSIIndicator(close=df_5m['close'], window=14).rsi().iloc[-1]
                     
                     # Store in separate key to avoid overwriting 1m indicators
                     if 'indicators_5m' not in state: state['indicators_5m'] = {}
                     state['indicators_5m']['rsi'] = rsi_5m
                     state['indicators_5m']['close'] = c5['close']
                     state['indicators_5m']['timestamp'] = c5['timestamp']
                     
                     logging.info(f"5m Analysis {symbol}: RSI={rsi_5m:.2f}")
             except Exception as e:
                 logging.error(f"5m Calc Error {symbol}: {e}")
             
             # RESTORED: Standard System Analysis
             self.analyze_market(symbol, df_5m)
        
        if self.on_candle_closed:
             self.on_candle_closed(symbol, candle_1m)

    def update_15m_candle(self, symbol, candle_1m):
        state = self.market_state[symbol]
        c15 = state['current_candle_15m']
        
        # Init if None
        if c15 is None:
             base_time = candle_1m['timestamp'].replace(minute=(candle_1m['timestamp'].minute // 15) * 15)
             c15 = {
                 'timestamp': base_time,
                 'symbol': symbol,
                 'open': candle_1m['open'], 
                 'high': candle_1m['high'], 
                 'low': candle_1m['low'], 
                 'close': candle_1m['close'],
                 'volume': candle_1m['volume'], 
                 'trades': candle_1m['trades']
             }
             state['current_candle_15m'] = c15
        else:
             if (candle_1m['timestamp'] - c15['timestamp']).total_seconds() >= 900:
                  state['current_candle_15m'] = None
                  self.update_15m_candle(symbol, candle_1m)
                  return

             c15['high'] = max(c15['high'], candle_1m['high'])
             c15['low'] = min(c15['low'], candle_1m['low'])
             c15['close'] = candle_1m['close']
             c15['volume'] += candle_1m['volume']
             c15['trades'] += candle_1m['trades']
        
        ts = candle_1m['timestamp']
        if (ts.minute + 1) % 15 == 0:
             state['candles_15m'].append(c15)
             if len(state['candles_15m']) > 100: state['candles_15m'].pop(0)
             
             state['current_candle_15m'] = None
             
             # Analyze 15m
             df_15m = pd.DataFrame(state['candles_15m'])
             logging.info(f"ANALYSIS 15m {symbol}: Closed {c15['timestamp'].strftime('%H:%M')} | Close: {c15['close']}")
             
             # Calculate 15m Indicators
             try:
                 df_15m['close'] = pd.to_numeric(df_15m['close'])
                 df_15m['high'] = pd.to_numeric(df_15m['high'])
                 df_15m['low'] = pd.to_numeric(df_15m['low'])
                 
                 if len(df_15m) > 14:
                     # EMA 200
                     ema200_15m = ta.trend.EMAIndicator(close=df_15m['close'], window=200 if len(df_15m) >= 200 else len(df_15m)).ema_indicator().iloc[-1]
                     # ADX 14
                     adx_15m = ta.trend.ADXIndicator(high=df_15m['high'], low=df_15m['low'], close=df_15m['close'], window=14).adx().iloc[-1]
                     
                     if 'indicators_15m' not in state: state['indicators_15m'] = {}
                     state['indicators_15m']['ema200'] = ema200_15m
                     state['indicators_15m']['adx'] = adx_15m
                     state['indicators_15m']['close'] = c15['close']
                     
                     logging.info(f"15m Analysis {symbol}: EMA200={ema200_15m:.2f}, ADX={adx_15m:.2f}")
             except Exception as e:
                 logging.error(f"15m Calc Error {symbol}: {e}")

    def analyze_market(self, symbol, df):
        if len(df) < 20: return
        
        # --- Indicators ---
        # 1. RSI (Using ta library)
        try:
            rsi_indicator = ta.momentum.RSIIndicator(close=df['close'], window=14)
            df['rsi'] = rsi_indicator.rsi()
        except Exception as e:
            logging.info(f"RSI Calc Error {symbol}: {e}") # Changed from logging.warning to logging.info
            df['rsi'] = 50.0

        # 2. Volume Moving Average
        df['vol_ma'] = df['volume'].rolling(20).mean()
        
        # 3. Spread & VRel & ERR (Manual Logic)
        df['spread'] = df['high'] - df['low']
        df['spread_ma'] = df['spread'].rolling(20).mean()
        
        last = df.iloc[-1]
        state = self.market_state[symbol]
        
        # Store for Monitor
        state['indicators']['rsi'] = last['rsi']
        
        # Safety for NaNs
        df['rsi'] = df['rsi'].fillna(50.0)
        df['vol_ma'] = df['vol_ma'].fillna(0.0)
        df['spread_ma'] = df['spread_ma'].fillna(0.0)

        # 4. EMA 200
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Get latest values for logic
        last_row = df.iloc[-1]
        
        rsi = last_row['rsi']
        vol = last_row['volume']
        vol_ma = last_row['vol_ma']
        
        # VRel
        vrel = vol / vol_ma if vol_ma > 0 else 0.0
        
        # ERR (Effort Result Ratio)
        # Effort = Volume, Result = Spread
        # Strict VSA: ERR = VRel / SRel (Relative Spread)
        spread = last_row['spread']
        spread_ma = last_row['spread_ma']
        srel = spread / spread_ma if spread_ma > 0 else 1.0
        err = vrel / srel if srel > 0 else 0.0
        
        # Update State Indicators
        state['indicators']['rsi'] = rsi
        state['indicators']['vrel'] = vrel
        state['indicators']['err'] = err
        
        # Store for strategies
        state['indicators']['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
        state['indicators']['ema200'] = last_row['ema200']
        
        # Simple PinBar Detection
        # (Body / Range < 0.3) AND (Wick > 2x Body)
        # Determine Bearish/Bullish
        open_p = last_row['open']
        close_p = last_row['close']
        high_p = last_row['high']
        low_p = last_row['low']
        
        body = abs(close_p - open_p)
        rng = high_p - low_p
        
        is_pinbar = False
        if rng > 0 and (body / rng) < 0.3:
             # Check Wicks
             upper_wick = high_p - max(open_p, close_p)
             lower_wick = min(open_p, close_p) - low_p
             
             if lower_wick > (2 * body) and lower_wick > upper_wick:
                  is_pinbar = True # Bullish Pinbar (Hammer)
             elif upper_wick > (2 * body) and upper_wick > lower_wick:
                  is_pinbar = True # Bearish Pinbar (Shooting Star)
        
        state['indicators']['PinBar'] = is_pinbar
        
        # Trend 1h (Approximation using 5m EMA)
        # If Price > EMA200 -> UP, else DOWN
        trend = "UP" if close_p > last_row['ema200'] else "DOWN"
        state['indicators']['Current_Trend_1h'] = trend
        
        # Define Trend Flags for Signal
        trend_bullish = close_p > last_row['ema200']
        trend_bearish = close_p < last_row['ema200']

        logging.info(f"ANALYSIS {symbol}: RSI={rsi:.1f}, Vol={vol:.0f}, VRel={vrel:.2f}, ERR={err:.2f}")

        # --- REGIME CLASSIFICATION ---
        regime = self.determine_regime(symbol, df)
        state['current_regime'] = regime
        state['indicators']['Market_Regime'] = regime

        # --- FULL ANALYSIS STORAGE (For GUI Market Monitor) ---
        # Calculate full rich indicators and store them for the GUI to pick up
        full_analysis = self.calculate_technical_indicators(symbol, state)
        if full_analysis:
             state['last_analysis'] = full_analysis
             # Update critical real-time indicators in state['indicators'] from this full analysis too
             # to ensure consistency
             state['indicators'].update({
                 'rsi': float(full_analysis.get('RSI_14', 50.0)) if 'RSI_14' in full_analysis else rsi,
                 'vrel': float(full_analysis.get('VRel', 0.0)),
                 'err': float(full_analysis.get('ERR', 0.0)),
                 'PinBar': full_analysis.get('PinBar') == 'True'
             })

        # 1. Signal Detection Init
        is_signal_long = False
        is_signal_short = False

        # Strict Thresholds
        vrel_ok = vrel > config.VREL_THRESHOLD
        err_ok = err > config.ERR_THRESHOLD
        rsi_long = last['rsi'] < config.RSI_OVERSOLD
        rsi_short = last['rsi'] > config.RSI_OVERBOUGHT
        
        # Pin Bar / Low Test / High Test
        body = abs(last['open'] - last['close'])
        wick_up = last['high'] - max(last['open'], last['close'])
        wick_down = min(last['open'], last['close']) - last['low']
        total_len = last['high'] - last['low']
        
        is_pinbar_bull = False
        is_pinbar_bear = False
        
        if total_len > 0:
            # Bull Pin: Long Lower Wick (>60%)
            if (wick_down / total_len) > 0.60: is_pinbar_bull = True
            # Bear Pin: Long Upper Wick (>60%)
            if (wick_up / total_len) > 0.60: is_pinbar_bear = True

        # Signal Combination
        decision_log = []
        if vrel_ok and err_ok:
             if rsi_long and is_pinbar_bull and trend_bullish:
                # Calculate Rich Indicators for Strategy Logic
                rich_ind = self.calculate_technical_indicators(symbol, state)
                if rich_ind:
                    # Merge into state['indicators'] so monitor and logs use it
                    # Note: state['indicators'] had basic RSI/VRel from `analyze_market`.
                    # Valid VRel calculation: Volume / Mean
                    vol_mean = rich_ind.pop('vrel', 1.0) # 'vrel' key from calc func was actually mean
                    if vol_mean > 0:
                        vrel_calc = vol / vol_mean
                        rich_ind['vrel'] = vrel_calc
                    
                    state['indicators'].update(rich_ind)
                
                is_signal_long = True
                decision_log.append("SIGNAL LONG: VRel+ERR+RSI+PinBar+Trend")
             elif rsi_short and is_pinbar_bear and trend_bearish:
                # Calculate Rich Indicators for Strategy Logic
                rich_ind = self.calculate_technical_indicators(symbol, state)
                if rich_ind:
                    # Merge into state['indicators'] so monitor and logs use it
                    # Note: state['indicators'] had basic RSI/VRel from `analyze_market`.
                    # Valid VRel calculation: Volume / Mean
                    vol_mean = rich_ind.pop('vrel', 1.0) # 'vrel' key from calc func was actually mean
                    if vol_mean > 0:
                        vrel_calc = vol / vol_mean
                        rich_ind['vrel'] = vrel_calc
                    
                    state['indicators'].update(rich_ind)

                is_signal_short = True
                decision_log.append("SIGNAL SHORT: VRel+ERR+RSI+PinBar+Trend")

        # 3. State Machine: Pending Confirmation
        # Check if we were pending
        pending_cmd = state.get('pending_signal') # 'LONG' or 'SHORT'
        pending_trigger = state.get('pending_trigger_price') # High or Low of signal candle
        
        if pending_cmd:
             # Check Expiration
             expires_in = state.get('pending_expires_in', 0)
             if expires_in <= 0:
                  logging.info(f"EXPIRED {pending_cmd} {symbol}: Confirmation Timeout")
                  state['pending_signal'] = None
                  state['last_decision'] = "Expired_Conf"
                  pending_cmd = None # Stop processing
             else:
                  state['pending_expires_in'] = expires_in - 1
        
        if pending_cmd:
             current_price = close_p
             # Check Confirmation (Breakout)
             if pending_cmd == 'LONG':
                 if current_price > pending_trigger:
                     logging.info(f"CONFIRMED LONG {symbol} @ {current_price} > {pending_trigger}")
                     self.handle_entry(symbol, 'LONG', current_price)
                     state['pending_signal'] = None # Reset
                 else:
                     logging.info(f"WAIT CONFIRM LONG {symbol}: {current_price} <= {pending_trigger}")
                     
                     # Cancel Condition: Break Low of Signal Candle
                     signal_low = state.get('signal_candle_low')
                     if signal_low and current_price < signal_low:
                         logging.info(f"CANCEL LONG {symbol}: Price broke Signal Low")
                         state['pending_signal'] = None
                         state['last_decision'] = "Cancelled_BreakLow"

             elif pending_cmd == 'SHORT':
                 if current_price < pending_trigger:
                     logging.info(f"CONFIRMED SHORT {symbol} @ {current_price} < {pending_trigger}")
                     self.handle_entry(symbol, 'SHORT', current_price)
                     state['pending_signal'] = None
                 else:
                     logging.info(f"WAIT CONFIRM SHORT {symbol}: {current_price} >= {pending_trigger}")
                     
                     # Cancel Condition
                     signal_high = state.get('signal_candle_high')
                     if signal_high and current_price > signal_high:
                         logging.info(f"CANCEL SHORT {symbol}: Price broke Signal High")
                         state['pending_signal'] = None
                         state['last_decision'] = "Cancelled_BreakHigh"

        # 3. New Signal -> Set Pending
        # Only if no position open (or can hedge/dca - handled in handle_entry)
        
        # CLIMAX EXCEPTION: Check for VRel > 10 + RSI < 15 (Force LONG)
        is_climax = False
        if vrel > 10.0 and rsi_long and last['rsi'] < 15:
            is_climax = True
            decision_log.append("CLIMAX LONG: VRel>10 + RSI<15")
            logging.info(f"CLIMAX SIGNAL {symbol}: Force Long")
            # Immediate Entry or Confirm? Valid Signal usually implies immediate or pending check.
            # Let's treat it as a Strong Signal that bypasses Trend check.
            is_signal_long = True
        
        if is_signal_long and not pending_cmd:
            logging.info(f"PENDING LONG {symbol}: Signal Candle Closed. Wait > {last['high']}. (Climax={is_climax})")
            state['pending_signal'] = 'LONG'
            state['pending_trigger_price'] = last['high']
            state['signal_candle_low'] = last['low']
            state['pending_expires_in'] = 2 # 2 Candles window
            decision_outcome = "Pending_Confirmation"
            
            if is_climax: 
                state['last_decision'] = "Climax_Entry"
                decision_outcome = "Climax_Entry_Triggered"
            
            # Log Opportunity
            self.log_opportunity(symbol, last, state, "SIGNAL_LONG", decision_outcome)
            
        elif is_signal_short and not pending_cmd:
            logging.info(f"PENDING SHORT {symbol}: Signal Candle Closed. Wait < {last['low']}")
            state['pending_signal'] = 'SHORT'
            state['pending_trigger_price'] = last['low']
            state['signal_candle_high'] = last['high']
            state['pending_expires_in'] = 2
            
            # Log Opportunity
            self.log_opportunity(symbol, last, state, "SIGNAL_SHORT", "Pending_Confirmation")
            
        elif (vrel_ok or err_ok or is_pinbar_bull or is_pinbar_bear):
             # Log Ignored Opps
             reason = "Ignored"
             if not trend_bullish and not trend_bearish: reason = "Trend_Neutral"
             elif not is_pinbar_bull and not is_pinbar_bear: reason = "No_PinBar"
             elif not rsi_long and not rsi_short: reason = "RSI_Filter"
             
             self.log_opportunity(symbol, last, state, "POTENTIAL_SIGNAL", reason)


        # Store context for logs (Into State directly, avoiding DataFrame warning)
        # last['PinBar'] = is_pinbar_bull or is_pinbar_bear (Removed to fix Warning)
        # last['Decision_Log'] = "; ".join(decision_log) if decision_log else "Monitoring" (Removed to fix Warning)
        
        state['last_decision'] = "; ".join(decision_log) if decision_log else "Monitoring"
        # If explicitly waiting or ignored, use that
        if pending_cmd:
            state['last_decision'] = f"Waiting_Conf_{pending_cmd} ({state.get('pending_expires_in', 0)})"
        elif "SIGNAL" in state.get('last_decision', ''):
             pass
        else:
             # Basic state
             if trend_bullish: state['last_decision'] = "Trend_Bullish"
             elif trend_bearish: state['last_decision'] = "Trend_Bearish"
             
        state['last_pinbar'] = is_pinbar_bull or is_pinbar_bear
        state['last_pinbar'] = is_pinbar_bull or is_pinbar_bear
        
    def handle_entry(self, symbol, side, price):
        """
        Handles confirmed breakout signal. 
        Broadcasts to all strategies.
        """
        state = self.market_state[symbol]
        indicators = state['indicators']
        
        log_entry = {
            'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'Symbol': symbol,
            'Side': side,
            'Price': f"{price:.4f}",
            'RSI': f"{indicators.get('rsi',0):.1f}", 
            'VRel': f"{indicators.get('vrel',0):.2f}",
            'ERR': f"{indicators.get('err',0):.2f}",
            'PinBar': str(indicators.get('PinBar', False))
        }
        
        for strat_id, strat in self.strategies.items():
            # Pass full context if needed, for now just price and indicators
            # strategies now return (success, reason)
            success, reason = strat.confirm_entry(symbol, side, price, indicators)
            
            log_entry[f"{strat_id}_Status"] = "ACCEPTED" if success else "REJECTED"
            log_entry[f"{strat_id}_Reason"] = reason

        self.log_signal_to_csv(log_entry)

        self.log_signal_to_csv(log_entry)

    def determine_regime(self, symbol, df):
        """
        Classifies Market Regime:
        - Trending_Up: ADX > 25 & Close > EMA200
        - Trending_Down: ADX > 25 & Close < EMA200
        - High_Volatility: BB Width > (Avg BB Width * 2) 
        - Ranging_Lateral: ADX < 25 (Default)
        """
        if len(df) < 20: return "Unknown"
        last = df.iloc[-1]
        
        adx = last.get('ADX_14', 0) if 'ADX_14' in last else 0
        # Check if ADX was calc in df (it is in calc_tech_ind but here 'df' is 5m candles raw? 
        # No, analyze_market calculates some indicators but maybe not full 'ADX_14' column globally if not using calc_tech_ind.
        # analyze_market does basic ta. Need to ensure ADX is calculated there or re-use.
        # Let's calc ADX here quickly if missing.
        if 'ADX_14' not in df.columns:
             try:
                 df['ADX_14'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
                 adx = df['ADX_14'].iloc[-1]
             except: pass
             
        # BB Width Check
        bb_width = 0
        if 'Bollinger_Width' in df.columns:
            bb_width = df['Bollinger_Width'].iloc[-1]
        else:
            # Calc
            bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
            df['Bollinger_Width'] = bb.bollinger_wband()
            bb_width = df['Bollinger_Width'].iloc[-1]
            
        # Avg BB Width (Last 50?)
        avg_bb_width = df['Bollinger_Width'].rolling(50).mean().iloc[-1]
        
        if avg_bb_width > 0 and bb_width > (avg_bb_width * 2):
            return "High_Volatility"
            
        ema200 = df['ema200'].iloc[-1]
        close = last['close']
        
        if adx > 25:
            if close > ema200: return "Trending_Up"
            else: return "Trending_Down"
            
        return "Ranging_Lateral"

    def log_opportunity(self, symbol, candle, state, signal_type, outcome):
        """Logs every potential signal to TRH_Opportunities_Log.csv"""
        import os
        filename = "TRH_Opportunities_Log.csv"
        
        headers = [
            'Timestamp', 'Symbol', 'Price', 'Signal_Type', 'Decision_Outcome', 
            'Regime', 'RSI', 'VRel', 'ERR', 'PinBar', 'ADX', 'Fib_Level', 'Strategy_IDs'
        ]
        
        # Prepare Data
        indicators = state.get('indicators', {})
        
        row = {
            'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'Symbol': symbol,
            'Price': f"{candle['close']:.4f}",
            'Signal_Type': signal_type,
            'Decision_Outcome': outcome,
            'Regime': state.get('current_regime', 'Unknown'),
            'RSI': f"{indicators.get('rsi', 0):.1f}",
            'VRel': f"{indicators.get('vrel', 0):.2f}",
            'ERR': f"{indicators.get('err', 0):.2f}",
            'PinBar': str(indicators.get('PinBar', False)),
            'ADX': f"{indicators.get('atr', 0):.4f}", # Placeholder: ATR is stored, need ADX? 
            # We calculated ADX in determine_regime but not stored in indicators dict explicitly yet?
            # It's in 'state' via TRH Research Log logic, but analyze_market might differ.
            # Let's just use what we have or 0.
            'Fib_Level': "0.00", # TODO: Store Fib
            'Strategy_IDs': "ALL" 
        }
        
        # Write
        try:
            file_exists = os.path.isfile(filename)
            with open(filename, 'a') as f:
                if not file_exists:
                    f.write(",".join(headers) + "\n")
                
                vals = [str(row.get(h, "")) for h in headers]
                f.write(",".join(vals) + "\n")
        except Exception as e:
            logging.error(f"Failed to log opportunity: {e}")

    def log_signal_to_csv(self, row_data):
        import os
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        filename = f"Trading_Signals_{date_str}.csv"
        
        headers = ['Timestamp', 'Symbol', 'Side', 'Price', 'RSI', 'VRel', 'ERR', 'PinBar',
                   'S1_Status', 'S1_Reason', 'S2_Status', 'S2_Reason', 'S3_Status', 'S3_Reason', 'S4_Status', 'S4_Reason']
                   
        try:
            file_exists = os.path.isfile(filename)
            is_empty = file_exists and os.path.getsize(filename) == 0
            
            with open(filename, 'a') as f:
                if not file_exists or is_empty:
                    f.write(",".join(headers) + "\n")
                
                # Ensure ordered values
                vals = [str(row_data.get(h, "")) for h in headers]
                f.write(",".join(vals) + "\n")
        except Exception as e:
            logging.error(f"Signal Log Error: {e}")

    def check_dca_condition(self, symbol, current_price, last):
         pass

    def log_ts_debug(self, t_id, symbol, side, price, extremum, atr, pnl_pct, status, ts_price):
        """Logs Trailing Stop details to CSV for verification."""
        file_exists = False
        try:
             with open("ts_debug.csv", "r") as f: file_exists = True
        except: pass
        
        with open("ts_debug.csv", "a") as f:
             if not file_exists:
                 f.write("Timestamp,TradeID,Symbol,Type,Price,Extremum,ATR,PnL_Pct,Status,TS_Price\n")
             
             t_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
             line = f"{t_str},{t_id},{symbol},{side},{price:.4f},{extremum:.4f},{atr:.4f},{pnl_pct:.2f},{status},{ts_price:.4f}\n"
             f.write(line)




    def save_market_data(self, symbol, candle, vrel_passed, err_passed, pos_count):
        import os
        # TRH Sniper Research Log
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        filename = f"TRH_Research_{date_str}.csv"
        
        try:

            # 1. Prepare Data
            state = self.market_state[symbol]
            df = pd.DataFrame(state['candles'])
            if len(df) < 50: return 

            # Ensure numeric
            cols = ['open', 'high', 'low', 'close', 'volume']
            df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')

            # 2. Calculate Indicators (using 'ta' library)
            
            # --- Volatility ---
            # ATR 14
            df['ATR_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
            
            # Bollinger Bands (20, 2)
            bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
            df['Bollinger_Upper'] = bb.bollinger_hband()
            df['Bollinger_Lower'] = bb.bollinger_lband()
            df['Bollinger_Width'] = bb.bollinger_wband()

            # --- Volume Advanced ---
            # MFI 14
            df['MFI_14'] = ta.volume.MFIIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()
            # OBV
            df['OBV'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
            # Volume Mean 20
            df['Volume_Mean_20'] = df['volume'].rolling(20).mean()

            # --- Oscillation ---
            # Stochastic (14, 3, 3) 
            stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
            df['Stoch_K'] = stoch.stoch()
            df['Stoch_D'] = stoch.stoch_signal()
            
            # Stochastic RSI (14) - New Intelligent Indicator
            stoch_rsi = ta.momentum.StochRSIIndicator(df['close'], window=14)
            df['Stoch_RSI_K'] = stoch_rsi.stochrsi_k()
            df['Stoch_RSI_D'] = stoch_rsi.stochrsi_d() # Optional, keeping K is main
            
            # ADX 14
            adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
            df['ADX_14'] = adx_ind.adx()

            # --- Structure (Price Action) ---
            # Candle Body Size: abs(Open - Close)
            df['Candle_Body_Size'] = (df['open'] - df['close']).abs()
            # Upper Wick: High - max(Open, Close)
            df['Upper_Wick_Size'] = df['high'] - df[['open', 'close']].max(axis=1)
            # Lower Wick: min(Open, Close) - Low
            df['Lower_Wick_Size'] = df[['open', 'close']].min(axis=1) - df['low']
            # Wick Body Ratio
            df['Wick_Body_Ratio'] = (df['Upper_Wick_Size'] + df['Lower_Wick_Size']) / df['Candle_Body_Size'].replace(0, 0.00001)

            # --- Levels (Pivot Points - Auto Rolling) ---
            # Rolling window to emulate Daily High/Low/Close for intraday Pivot Calculation.
            # Using last 1440 minutes (24h) if available, else expanding.
            rolling_high_24h = df['high'].rolling(1440, min_periods=1).max()
            rolling_low_24h = df['low'].rolling(1440, min_periods=1).min()
            rolling_close_24h = df['close'] # Use current close as "Prev Close" proxy? Or Close of 24h ago? 
            # Classic Pivot: (H + L + C) / 3. We use rolling approximation.
            pp = (rolling_high_24h + rolling_low_24h + df['close']) / 3
            df['Pivot_P'] = pp
            df['Pivot_R1'] = (2 * pp) - rolling_low_24h
            df['Pivot_S1'] = (2 * pp) - rolling_high_24h
            # R2 = P + (H - L)
            df['Pivot_R2'] = pp + (rolling_high_24h - rolling_low_24h)
            # S2 = P - (H - L)
            df['Pivot_S2'] = pp - (rolling_high_24h - rolling_low_24h)

            # --- Reference Metrics ---
            # EMA 200
            df['EMA_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
            # Distance EMA 200 %
            df['Dist_EMA200_Pct'] = (df['close'] - df['EMA_200']) / df['EMA_200']

            # --- Strategy State ---
            # Current Trend 1h
            trend = "Neutral"
            if len(df) > 60:
                delta = df['close'].iloc[-1] - df['close'].iloc[-61]
                trend = "Bullish" if delta > 0 else "Bearish"
            
            # Fib Zone
            fib_level = 0.0
            if len(df) > 10:
                window = 200
                recent = df.tail(window)
                local_high = recent['high'].max()
                local_low = recent['low'].min()
                rng = local_high - local_low
                if rng > 0:
                    fib_level = (df['close'].iloc[-1] - local_low) / rng # 0 to 1 position
                
            # --- Last Row Extraction ---
            last = df.iloc[-1]
            
            # Format Data
            row_dict = {
                'Timestamp': str(last['timestamp']),
                'Symbol': symbol,
                'Open': f"{last['open']:.4f}",
                'High': f"{last['high']:.4f}",
                'Low': f"{last['low']:.4f}",
                'Close': f"{last['close']:.4f}",
                'Volume': f"{last['volume']:.2f}",
                
                # Computed
                'ATR_14': f"{last.get('ATR_14', np.nan):.4f}",
                'Bollinger_Upper': f"{last.get('Bollinger_Upper', np.nan):.4f}",
                'Bollinger_Lower': f"{last.get('Bollinger_Lower', np.nan):.4f}",
                'Bollinger_Width': f"{last.get('Bollinger_Width', np.nan):.4f}",
                
                'MFI_14': f"{last.get('MFI_14', np.nan):.2f}",
                'OBV': f"{last.get('OBV', np.nan):.2f}",
                'Volume_Mean_20': f"{last.get('Volume_Mean_20', np.nan):.2f}",
                
                'Stoch_K': f"{last.get('Stoch_K', np.nan):.2f}",
                'Stoch_D': f"{last.get('Stoch_D', np.nan):.2f}",
                'Stoch_RSI_K': f"{last.get('Stoch_RSI_K', np.nan):.2f}",
                'ADX_14': f"{last.get('ADX_14', np.nan):.2f}",
                
                'Candle_Body_Size': f"{last.get('Candle_Body_Size', 0):.5f}",
                'Upper_Wick_Size': f"{last.get('Upper_Wick_Size', 0):.5f}",
                'Lower_Wick_Size': f"{last.get('Lower_Wick_Size', 0):.5f}",
                'Wick_Body_Ratio': f"{last.get('Wick_Body_Ratio', 0):.2f}",
                
                'Pivot_P': f"{last.get('Pivot_P', np.nan):.4f}",
                'Pivot_R1': f"{last.get('Pivot_R1', np.nan):.4f}",
                'Pivot_S1': f"{last.get('Pivot_S1', np.nan):.4f}",
                
                'Dist_EMA200_Pct': f"{last.get('Dist_EMA200_Pct', np.nan):.4f}",
                
                'Current_Trend_1h': trend,
                'Fibonacci_Level': f"{fib_level:.3f}", # Renamed zone to level
                # 'DCA_Available_Funds': f"{self.wallet.balance_eur:.2f}", # Removed
                
                # Context / Strategy Signals (From 5m State)
                'VRel': f"{vrel_passed:.2f}", # Computed on 1m? No, passed in.
                'ERR': f"{err_passed:.2f}",
                'PinBar': f"{state.get('last_pinbar', False)}", # Read from State
                'Decision_Log': state.get('last_decision', "Init"), # Read from State
                'Active_Pos_Count': str(pos_count),
                # 'Total_Balance': f"{self.wallet.balance_eur:.2f}" # Removed
            }
            
            headers = list(row_dict.keys())
            values = list(row_dict.values())
            
            # 3. Write CSV
            file_exists = os.path.isfile(filename)
            is_empty = file_exists and os.path.getsize(filename) == 0
            
            with open(filename, 'a') as f:
                if not file_exists or is_empty:
                    f.write(",".join(headers) + "\n")
                f.write(",".join(values) + "\n")
                
        except Exception as e:
            logging.error(f"Error saving extended market data for {symbol}: {e}")
            pass

    def check_scheduled_tasks(self):
        """Checks if scheduled strategies should run (Daily @ 00:00)."""
        now = datetime.datetime.now()
        today = now.date()
        
        # 1. Daily Strategy Run (00:00)
        if self.last_scheduler_date is None or (now.hour == 0 and self.last_scheduler_date != today):
                logging.info("Executing Daily Scheduled Tasks (00:00)...")
                try:
                    self.macro_strategy.run()
                except Exception as e:
                    logging.error(f"Error in Macro Strategy: {e}")
                
                try:
                    self.five_cubes_sim.run()
                except Exception as e:
                    logging.error(f"Error in Five Cubes Sim: {e}")
                
                try:
                    self.news_strategy.run()
                except Exception as e:
                    logging.error(f"Error in News Strategy: {e}")
                
                # 4. Kraken Event Daily Recalculation (Compound Interest)
                # 4. Antigravity Daily Log (Optional)
                if 'Antigravity' in self.strategies:
                    logging.info("StrategyProcessor: Antigravity Strategy is active.")

                self.last_scheduler_date = today
                logging.info("Daily Strategy Run Completed.")

        # 2. Daily Telegram Summary (08:00)
        # We check if it's 8:00 and we haven't sent it today.
        if now.hour == 8 and self.last_summary_date != today:
            logging.info("Sending Daily Telegram Summary (08:00)...")
            try:
                summary_text = self.reporter.generate_daily_summary(self.strategies)
                self.reporter.send_message(summary_text)
                self.last_summary_date = today
                logging.info("Daily Summary Sent.")
            except Exception as e:
                logging.error(f"Failed to send Daily Summary: {e}")

        # 3. Daily Technical Summary (12:00)
        if now.hour == 12 and self.last_tech_summary_date != today:
            logging.info("Sending Daily Technical Summary (12:00)...")
            try:
                summary_text = self.reporter.generate_technical_summary(self.strategies)
                self.reporter.send_message(summary_text)
                self.last_tech_summary_date = today
                logging.info("Daily Technical Summary Sent.")
            except Exception as e:
                logging.error(f"Failed to send Technical Summary: {e}")

    def get_aggregated_strategies_status(self):
        """Combines Macro/Sim strategies + Paper Wallets."""
        # 1. Macro / Scheduled
        statuses = []
        statuses.append(self.macro_strategy.get_status())
        statuses.append(self.five_cubes_sim.get_status())
        statuses.append(self.news_strategy.get_status())
        
        return statuses
