import logging
import time
import os
from kraken_bot import config

class BaseStrategy:
    def __init__(self, strategy_id, wallet):
        self.id = strategy_id
        self.name = strategy_id # Default name
        self.wallet = wallet
        self.dca_enabled = True
        self.paused = False 
        self.dca_enabled = True
        self.paused = False 
        self.allowed_sides = ['LONG', 'SHORT']
        self.on_event = None
        self.start_time = time.time()
        
        self.params = {
            'vrel_min': 3.0,
            'err_min': 2.5,
            'rsi_long_max': 40.0,
            'rsi_short_min': 60.0,
            'adx_min': 0.0,
            'wick_min': 0.0,
            'ts_atr_mult': 3.0,
            'tsl_pct': 0.015
        }
    
    def get_now(self):
        """Returns current time (live or simulated)."""
        if hasattr(self.wallet, 'current_time') and self.wallet.current_time:
            if hasattr(self.wallet.current_time, 'timestamp'):
                return self.wallet.current_time.timestamp()
            return self.wallet.current_time # Already a timestamp
        return time.time()
    
    def on_tick(self, symbol, price, indicators):
        """Called on every trade/tick."""
        self.check_exit_conditions(symbol, price, indicators)
        
        if not self.paused:
            self.check_entry_logic(symbol, price, indicators)

    def check_entry_logic(self, symbol, price, indicators):
        """Standard Entry Logic using Params (S1/S2 style)."""
        # Validate critical data
        if 'vrel' not in indicators or 'err' not in indicators: return

        vrel = float(indicators.get('vrel', 0))
        err = float(indicators.get('err', 0))
        rsi = float(indicators.get('rsi', 50))
        
        wick_val = float(indicators.get('Wick_Body_Ratio', indicators.get('wick_pct', 0)))

        # 1. Base Checks
        if vrel < self.params.get('vrel_min', 0): return
        if err < self.params.get('err_min', 0): return
        if wick_val < self.params.get('wick_min', 0): return
        
        # 0. Global Trend Defense (Panic Mode)
        trend = indicators.get('market_trend', 'NEUTRAL')
        
        # 2. RSI Filters
        # LONG
        if rsi < self.params.get('rsi_long_max', 100):
             if trend == 'DUMP':
                 logging.info(f"[{self.id}] LONG BLOCKED by Global Trend DUMP")
                 return

             if self.on_event: self.on_event("Opportunity", self.id, symbol, price, indicators)
             c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
             if c:
                 self.wallet.open_position(symbol, 'LONG', price)
                 if self.on_event: self.on_event("Open_Auto", self.id, symbol, price, indicators)
                 return

        # SHORT
        if rsi > self.params.get('rsi_short_min', 0):
             # Log Opportunity
             if self.on_event: self.on_event("Opportunity", self.id, symbol, price, indicators)
             c, r = self.wallet.can_open_new(symbol, 'SHORT', {symbol: price})
             if c:
                 self.wallet.open_position(symbol, 'SHORT', price)
                 if self.on_event: self.on_event("Open_Auto", self.id, symbol, price, indicators)


    def confirm_entry(self, symbol, side, price, indicators):
        """Legacy Processor Call - Deprecated in favor of on_tick logic."""
        return False, "Autonomous_Mode"

    def check_dca(self, pos, price, atr, indicators):
        pass

    def check_exit_conditions(self, symbol, price, indicators):
        for t_id, pos in list(self.wallet.positions.items()):
            if pos['symbol'] == symbol:
                self.wallet.update_max_stats(t_id, price) # <--- Update Max PnL
                self.manage_position(t_id, pos, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # Rule 2: Global Trailing Stop (Replaces Limit 2)
        # Trigger: Net PnL >= +0.04 EUR.
        # Trailing Dist: 0.02 EUR.
        
        # Calculate exact Net PnL in EUR
        gross = self.wallet.calc_pnl_gross(t_id, price)
        
        # Estimate Exit Fee
        val_exit = pos['size'] * price
        if pos['type'] == 'LONG': fee_rate = config.FEE_SPOT_TAKER
        else: fee_rate = config.FEE_FUTURES_TAKER
        
        fees_total = pos.get('itemized_fees', 0.0) + (val_exit * fee_rate)
        net_val = gross - fees_total

        trigger_eur = 0.04
        trail_dist_eur = 0.02
        
        # Check Activation
        if net_val >= trigger_eur:
            # Calculate required stop PnL (Current - Distance)
            target_stop_pnl = net_val - trail_dist_eur
            
            # Convert PnL to Price Level
            # Net = (Size * (Exit - Entry)) - Fees -> For Long
            # Net = (Size * (P - Entry)) - (ItemFees + Size*P*Rate)
            # Net = Size*P - Size*Entry - ItemFeatures - Size*P*Rate
            # Net + Size*Entry + ItemFees = Size*P*(1 - Rate)
            # P = (Net + Size*Entry + ItemFees) / (Size * (1 - Rate))
            
            # Helper to calculate Price from Net PnL
            def get_price_from_net(target_net):
                term_fees = pos.get('itemized_fees', 0.0)
                term_entry = pos['size'] * pos['entry_price']
                
                if pos['type'] == 'LONG':
                    numerator = target_net + term_entry + term_fees
                    denominator = pos['size'] * (1 - config.FEE_SPOT_TAKER)
                else:
                    # Net = (Entry - Exit) - Fees
                    # Net = Size*Entry - Size*P - ItemFees - Size*P*Rate
                    # Net - Size*Entry + ItemFees = -Size*P(1 + Rate)
                    # Size*Entry - Net - ItemFees = Size*P(1 + Rate)
                    numerator = term_entry - target_net - term_fees
                    denominator = pos['size'] * (1 + config.FEE_FUTURES_TAKER)
                    
                if denominator == 0: return price # Prevent div/0
                return numerator / denominator

            new_stop_price = get_price_from_net(target_stop_pnl)
            
            # Update Stop
            current_stop = pos.get('global_ts_price', 0.0)
            
            # Init if 0 (first trigger)
            if current_stop == 0.0:
                 pos['global_ts_price'] = new_stop_price
                 logging.info(f"[{self.id}] Global TS Activated {pos['symbol']} @ {price:.4f} (Net: {net_val:.4f}). Stop: {new_stop_price:.4f}")
            else:
                 # Update if better
                 if pos['type'] == 'LONG':
                     if new_stop_price > current_stop:
                         pos['global_ts_price'] = new_stop_price
                 else: # SHORT
                     if new_stop_price < current_stop:
                         pos['global_ts_price'] = new_stop_price
        
        # Check Exit Trigger
        ts_price = pos.get('global_ts_price', 0.0)
        if ts_price > 0:
             fired = False
             if pos['type'] == 'LONG' and price <= ts_price: fired = True
             if pos['type'] == 'SHORT' and price >= ts_price: fired = True
             
             if fired:
                 logging.info(f"[{self.id}] Global TS Hit {pos['symbol']} @ {price:.4f} (Stop: {ts_price:.4f})")
                 if self.wallet.close_position(t_id, price):
                     if self.on_event: self.on_event("Close_Global_TS", self.id, pos['symbol'], price, indicators)
                 return True

        # Rule 1: Limit 1 (Standard Time) -> Scratch at +0.01 Profit
        # Only if Global TS is NOT active (Prioritize Trailing)
        # This rule is removed as per instruction to only close in positive.
        # The global TS already handles positive exits.

        return False

class StrategyAggressive(BaseStrategy): 
    """S3: Aggressive (No DCA) + Momentum Crash Entry"""
    def __init__(self, wallet, allowed_sides=['LONG', 'SHORT']):
        super().__init__("Aggressive", wallet)
        self.name = "Aggressive Sniper"
        self.allowed_sides = allowed_sides
        self.dca_enabled = False
        self.params.update({
            'vrel_min': 3.0,
            'err_min': 2.5,
            'climax_vrel': 10.0,
            'climax_rsi_long': 15.0,
            'climax_rsi_short': 85.0,
            'rsi_long_max': 40.0,
            'rsi_short_min': 60.0,
            'momentum_mfi_limit': 15.0,
            'momentum_adx_min': 25.0,
            'momentum_ts_pct': 0.008,
            'ts_atr_mult': 3.0
        })

    def check_momentum_entry(self, symbol, price, indicators):
        try:
            bb_lower = float(indicators.get('Bollinger_Lower', 0))
            if bb_lower == 0 or price >= bb_lower: return False
            
            mfi = float(indicators.get('MFI_14', 50))
            if mfi >= self.params['momentum_mfi_limit']: return False
            
            adx = float(indicators.get('ADX_14', 0))
            if adx < self.params['momentum_adx_min']: return False
            
        except (ValueError, TypeError):
            return False
        
        return True

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Momentum Short Logic (Priority)
        if 'SHORT' in self.allowed_sides:
            if self.check_momentum_entry(symbol, price, indicators):
                 c, r = self.wallet.can_open_new(symbol, 'SHORT', {symbol: price})
                 if c:
                     if self.wallet.open_position(symbol, 'SHORT', price):
                         # Tag Position immediately
                         target_pos = None
                         max_time = 0
                         for pid, p in self.wallet.positions.items():
                             if p['symbol'] == symbol and p['type'] == 'SHORT' and p['entry_time'] > max_time:
                                 target_pos = p
                                 max_time = p['entry_time']
                         
                         if target_pos:
                             target_pos['strategy_mode'] = 'momentum'
                             target_pos['ts_status'] = 'ACTIVE' # Start Active
                             target_pos['lowest_price'] = price
                         
                         if self.on_event: self.on_event("Open_Mom_Short", self.id, symbol, price, indicators)
                         return

        # 2. Standard S3 Logic: Aggressive (High VRel/ERR) OR Climax
        if 'vrel' not in indicators: return
        
        vrel = float(indicators.get('vrel', 0))
        err = float(indicators.get('err', 0))
        rsi = float(indicators.get('rsi', 50))
        
        # Base
        base_L = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi < self.params['rsi_long_max'])
        base_S = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi > self.params['rsi_short_min'])
        
        # Climax
        climax_L = (vrel > self.params['climax_vrel']) and (rsi < self.params['climax_rsi_long'])
        climax_S = (vrel > self.params['climax_vrel']) and (rsi > self.params['climax_rsi_short'])
        
        side = None
        if (base_L or climax_L) and 'LONG' in self.allowed_sides: side = 'LONG'
        if (base_S or climax_S) and 'SHORT' in self.allowed_sides: side = 'SHORT'
        
        if side:
             c, r = self.wallet.can_open_new(symbol, side, {symbol: price})
             if c:
                 if self.wallet.open_position(symbol, side, price):
                      if self.on_event: self.on_event("Open_Aggr", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # Override for Momentum Mode
        if pos.get('strategy_mode') == 'momentum':
            if pos['type'] == 'SHORT':
                pos['lowest_price'] = min(pos.get('lowest_price', price), price)
                
                # Dynamic TS %
                ts_pct = self.params.get('momentum_ts_pct', 0.008)
                
                ts_price = pos['lowest_price'] * (1 + ts_pct)
                pos['ts_price'] = ts_price 
                
                if price > ts_price:
                     logging.info(f"[{self.id}] Momentum TS Hit {pos['symbol']}")
                     if self.wallet.close_position(t_id, price):
                         if self.on_event: self.on_event("Close_Mom_TS", self.id, pos['symbol'], price, indicators)
            return
                
        # Standard Logic (From Snipper)
        atr = indicators.get('atr', 0.0)
        if atr == 0: return

        if pos['type'] == 'LONG':
            pos['highest_price'] = max(pos.get('highest_price', price), price)
            pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
            
            ts_calculated = pos['highest_price'] - (self.params.get('ts_atr_mult', 3.0) * atr)
            current_ts = pos.get('ts_price', ts_calculated)
            
            # Natural Advance
            if ts_calculated > current_ts:
                ts = ts_calculated
                pos['last_ts_update'] = self.get_now()
            else:
                # Time Advance
                ts = current_ts
                if self.get_now() - pos.get('last_ts_update', pos['entry_time']) > 600:
                     ts += (atr * 0.1)
                     pos['last_ts_update'] = self.get_now()

            # Activation > 0.4%
            is_active = pos.get('ts_status') == "ACTIVE"
            if is_active or pnl_net_pct > 0.4:
                pos['ts_status'] = "ACTIVE"
                limit = pos['entry_price'] * 1.001
                if ts < limit: ts = limit
                pos['ts_price'] = ts
                
                if price < ts:
                    if price > pos['entry_price']: # Secure profit
                         if self.wallet.close_position(t_id, price):
                             if self.on_event: self.on_event("Close_Trail", self.id, pos['symbol'], price, indicators)
                    else: 
                         # Gap down? Hold?
                         pass
        else: # SHORT
            pos['lowest_price'] = min(pos.get('lowest_price', price), price)
            pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
            
            ts_calculated = pos.get('lowest_price') + (self.params.get('ts_atr_mult', 3.0) * atr)
            current_ts = pos.get('ts_price', ts_calculated)
            
            if ts_calculated < current_ts:
                 ts = ts_calculated
                 pos['last_ts_update'] = time.time()
            else:
                 ts = current_ts
                 if time.time() - pos.get('last_ts_update', pos['entry_time']) > 600:
                      ts -= (atr * 0.1)
                      pos['last_ts_update'] = time.time()

            is_active = pos.get('ts_status') == "ACTIVE"
            if is_active or pnl_net_pct > 0.4:
                pos['ts_status'] = "ACTIVE"
                limit = pos['entry_price'] * 0.999
                if ts > limit: ts = limit
                pos['ts_price'] = ts
                
                if price > ts:
                    if price < pos['entry_price']:
                         if self.wallet.close_position(t_id, price):
                             if self.on_event: self.on_event("Close_Trail", self.id, pos['symbol'], price, indicators)

    def confirm_entry(self, symbol, side, price, indicators):
        return False, "Autonomous_Mode"

class StrategyAggressiveCent(BaseStrategy): 
    """S4: Aggressive Cent (No DCA)"""
    def __init__(self, wallet, allowed_sides=['LONG', 'SHORT']):
        super().__init__("AggrCent", wallet)
        self.name = "Aggressive Cent"
        self.allowed_sides = allowed_sides
        self.dca_enabled = False
        self.params.update({
            'vrel_min': 3.0, 
            'err_min': 2.5,
            'climax_vrel': 10.0,
            'climax_rsi_long': 15.0,
            'climax_rsi_short': 85.0,
            'rsi_long_max': 40.0, 
            'rsi_short_min': 60.0,
            'profit_activation_eur': 0.10, 
            'profit_preserve_eur': 0.05,   
            'profit_step_eur': 0.01,
            'vrel_max': 5.0, # (VRel Cap)
            'adx_min': 20.0,
            'adx_max': 45.0 # (The Ceiling Rule)
        })

    def check_entry_logic(self, symbol, price, indicators):
         # S4: Aggressive Cent (Blindada)
        if 'vrel' not in indicators: return
        vrel = float(indicators.get('vrel', 0))
        err = float(indicators.get('err', 0))
        rsi = float(indicators.get('rsi', 50))
        adx = float(indicators.get('ADX_14', 0))
        
        # 0. Safety Filters (The "Vaccine")
        if adx <= self.params['adx_min']: return # Trend too weak
        if adx >= self.params['adx_max']: return # Trend too strong (Tsunami)
        if vrel >= self.params['vrel_max']: return # Volume Panic/Euphoria

        base_L = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi < self.params['rsi_long_max'])
        base_S = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi > self.params['rsi_short_min'])
        
        climax_L = (vrel > self.params['climax_vrel']) and (rsi < self.params['climax_rsi_long'])
        climax_S = (vrel > self.params['climax_vrel']) and (rsi > self.params['climax_rsi_short'])
        
        side = None
        if (base_L or climax_L) and 'LONG' in self.allowed_sides: side = 'LONG'
        if (base_S or climax_S) and 'SHORT' in self.allowed_sides: side = 'SHORT'
        
        if side:
             c, r = self.wallet.can_open_new(symbol, side, {symbol: price})
             if c:
                 if self.wallet.open_position(symbol, side, price):
                      if self.on_event: self.on_event("Open_AggrCent", self.id, symbol, price, indicators)

    def confirm_entry(self, symbol, side, price, indicators):
        return False, "Autonomous_Mode"
    
    def manage_position(self, t_id, pos, price, indicators):
        # PnL Value Logic (EUR)
        gross = self.wallet.calc_pnl_gross(t_id, price)
        
        # Est Fees
        val_exit = pos['size'] * price
        if pos['type'] == 'LONG': fee_rate = config.FEE_SPOT_TAKER
        else: fee_rate = config.FEE_FUTURES_TAKER
        
        fees_total = pos.get('itemized_fees', 0.0) + (val_exit * fee_rate)
        net_val = gross - fees_total
        
        # Activation
        act_eur = self.params.get('profit_activation_eur', 0.04)
        pres_eur = self.params.get('profit_preserve_eur', 0.02)
        step_eur = self.params.get('profit_step_eur', 0.01)

        is_active = pos.get('ts_status') == "ACTIVE"
        
        if not is_active:
            if net_val >= act_eur:
                pos['ts_status'] = "ACTIVE"
                # Init Stop at preserve_eur Profit
                target_pnl = pres_eur
                req_gross = target_pnl + fees_total
                price_diff = req_gross / pos['size']
                
                if pos['type'] == 'LONG':
                    ts_price = pos['avg_price'] + price_diff
                else:
                    ts_price = pos['avg_price'] - price_diff
                    
                pos['ts_price'] = ts_price
                pos['last_stop_move_time'] = time.time()
                pos['high_water_mark'] = net_val 
        else:
            # Check Exit
            if (pos['type']=='LONG' and price < pos['ts_price']) or (pos['type']=='SHORT' and price > pos['ts_price']):
                 logging.info(f"[{self.id}] Cent TS Exit {pos['symbol']} @ {price} (TS: {pos['ts_price']:.4f})")
                 if self.wallet.close_position(t_id, price):
                     if self.on_event: self.on_event("Close_Trail", self.id, pos['symbol'], price, indicators)
                 return

            # Check Updates (Step)
            # Basic Step Logic:
            excess = max(0, net_val - act_eur)
            steps = int(excess / step_eur) if step_eur > 0 else 0
            
            # Target protected profit
            target_stop_pnl = pres_eur + (steps * step_eur)
            
            req_gross = target_stop_pnl + fees_total
            price_diff = req_gross / pos['size']
             
            if pos['type'] == 'LONG':
                new_ts = pos['avg_price'] + price_diff
                if new_ts > pos['ts_price']:
                    pos['ts_price'] = new_ts
                    pos['last_stop_move_time'] = time.time() 
            else:
                new_ts = pos['avg_price'] - price_diff
                if new_ts < pos['ts_price']:
                    pos['ts_price'] = new_ts
                    pos['last_stop_move_time'] = time.time()
            
            # Time Logic ("Regla de Inactividad")
            if self.get_now() - pos.get('last_stop_move_time', self.get_now()) >= 300:
                # Force +0.01 EUR (Inactivity)
                shift = 0.01 / pos['size']
                
                if pos['type'] == 'LONG':
                    # Raise stop
                    pos['ts_price'] += shift
                    # Check if triggered immediately?
                    if pos['ts_price'] > price:
                         self.wallet.close_position(t_id, price)
                         if self.on_event: self.on_event("Close_Inactivity", self.id, pos['symbol'], price, indicators)
        return False, "No Signal"

class StrategyHybridElite(BaseStrategy):
    """
    S8: Hybrid Elite (S3 Entry + S4 Exit + Context).
    Entry: Aggressive Momentum (RSI/VRel) + BTC Trend Adaptation.
    Exit: PnL Preservation (Cent-based Trailing).
    """
    def __init__(self, wallet, allowed_sides=['LONG', 'SHORT']):
        super().__init__("HybridElite", wallet)
        self.name = "Hybrid Elite"
        self.allowed_sides = allowed_sides
        self.dca_enabled = False # No DCA, pure Sniper
        
        self.params.update({
            'vrel_min': 3.0,
            'err_min': 2.5,
            'rsi_long_max': 30.0, # CRITICAL CHANGE: 45 -> 30 (Strict Oversold)
            'rsi_short_min': 60.0, 
            
            # PnL Exit (S4)
            'profit_activation_eur': 0.08,
            'profit_preserve_eur': 0.04,
            'profit_step_eur': 0.01
        })

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Base Checks
        if 'vrel' not in indicators: return
        vrel = float(indicators.get('vrel', 0))
        err = float(indicators.get('err', 0))
        rsi = float(indicators.get('rsi', 50))
        adx = float(indicators.get('ADX_14', 0))
        trend = indicators.get('market_trend', 'NEUTRAL')
        
        # Adaptive Thresholds
        rsi_L_limit = self.params['rsi_long_max']
        rsi_S_limit = self.params['rsi_short_min']
        
        # Protective adjustment: High ADX = Strong Trend = Caution countering
        if adx > 40:
             # If trending down hard, need RSI to be VERY low to buy
             rsi_L_limit = 20.0
        
        if trend == 'DUMP':
            # Block Longs
            rsi_L_limit = -1.0 
            # Encourage Shorts
            rsi_S_limit = 50.0 
        
        # 0. Green Candle Confirmation (Don't catch falling knives)
        # Check if Price > Open
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price <= candle_open:
             # Candle is RED or Flat. Wait for reversal.
             return

        # 0.1. Stoch Momentum Confirmation (Avoid Dead Cat Bounce)
        stoch_k = float(indicators.get('Stoch_K', 50))
        stoch_d = float(indicators.get('Stoch_D', 50))
        if stoch_k < stoch_d: 
             return # Momentum still bearish

        # Logic
        base_L = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi < rsi_L_limit)
        base_S = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi > rsi_S_limit)
        
        side = None
        if base_L and 'LONG' in self.allowed_sides: side = 'LONG'
        if base_S and 'SHORT' in self.allowed_sides: side = 'SHORT'
        
        if side:
             c, r = self.wallet.can_open_new(symbol, side, {symbol: price})
             if c:
                 if self.wallet.open_position(symbol, side, price):
                      if self.on_event: self.on_event("Open_HybridElite", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # Use S4 (AggrCent) Exit Logic (Direct Copy for now, or mixin?)
        # Let's re-implement for clarity to ensure parameters are respected
        
        # PnL Value Logic (EUR)
        
        # Est Fees
        val_exit = pos['size'] * price
        if pos['type'] == 'LONG': fee_rate = config.FEE_SPOT_TAKER
        else: fee_rate = config.FEE_FUTURES_TAKER
        
        fees_total = pos.get('itemized_fees', 0.0) + (val_exit * fee_rate)
        gross = self.wallet.calc_pnl_gross(t_id, price)
        net_val = gross - fees_total
        
        # Activation
        act_eur = self.params.get('profit_activation_eur', 0.08)
        pres_eur = self.params.get('profit_preserve_eur', 0.04)
        step_eur = self.params.get('profit_step_eur', 0.01)

        is_active = pos.get('ts_status') == "ACTIVE"
        
        if not is_active:
            if net_val >= act_eur:
                pos['ts_status'] = "ACTIVE"
                # Init Stop
                req_gross = pres_eur + fees_total
                price_diff = req_gross / pos['size']
                
                if pos['type'] == 'LONG': ts_price = pos['avg_price'] + price_diff
                else: ts_price = pos['avg_price'] - price_diff
                    
                pos['ts_price'] = ts_price
                pos['high_water_mark'] = net_val 
                logging.info(f"[{self.id}] Hybrid Active! Locked {pres_eur} EUR")
        else:
            # Check Exit
            if (pos['type']=='LONG' and price < pos['ts_price']) or (pos['type']=='SHORT' and price > pos['ts_price']):
                 logging.info(f"[{self.id}] Hybrid Exit {pos['symbol']} @ {price} (Net: {net_val:.3f})")
                 if self.wallet.close_position(t_id, price):
                     if self.on_event: self.on_event("Close_Hybrid", self.id, pos['symbol'], price, indicators)
                 return

            # Check Updates (Step)
            excess = max(0, net_val - act_eur)
            steps = int(excess / step_eur) if step_eur > 0 else 0
            target_stop_pnl = pres_eur + (steps * step_eur)
            
            req_gross = target_stop_pnl + fees_total
            price_diff = req_gross / pos['size']
             
            if pos['type'] == 'LONG':
                new_ts = pos['avg_price'] + price_diff
                if new_ts > pos['ts_price']:
                    pos['ts_price'] = new_ts
            else:
                new_ts = pos['avg_price'] - price_diff
                if new_ts < pos['ts_price']:
                    pos['ts_price'] = new_ts

class StrategyRollingDCA(BaseStrategy):
    """
    RollingDCA: Peace of Mind Strategy.
    Timeframe: 5m
    Logic: Buy RSI(5m) < 40. Scale In (DCA) on drops.
    Exit: Avg Price + 1.2%.
    """
    def __init__(self, wallet, allowed_sides=['LONG']):
        super().__init__("RollingDCA", wallet)
        self.name = "Rolling DCA"
        self.allowed_sides = allowed_sides
        self.dca_enabled = True 
        # DCA Config
        self.dca_steps = [
            {'drop': -0.015, 'mult': 1.5}, # Step 1
            {'drop': -0.030, 'mult': 2.0}, # Step 2
            {'drop': -0.050, 'mult': 3.0}  # Step 3 (Total ~7.5x base)
        ]
        
        self.params.update({
            'rsi_5m_entry': 40.0,
            'take_profit_net_pct': 0.75, # FIXED 0.75% NET
            'max_concurrent': 3
        })

    def calc_safe_entry_size(self):
        # Total Multiplier Sum = 1 (Base) + 1.5 + 2.0 + 3.0 = 7.5
        total_mult = 1.0 + sum(s['mult'] for s in self.dca_steps)
        # Max Concurrent Positions = 3
        # Safe Allocation per coin = Total Balance / (MaxConcurrent * TotalMult)
        # We use Total Balance (Initial + Realized) or Free? 
        # Use Total Equity to size.
        equity = self.wallet.balance_eur # Conservative: Use Realized Balance only
        equity = max(equity, 1000.0) # Floor at initial config
        
        safe_size = equity / (self.params['max_concurrent'] * total_mult)
        # Keep > Min Order
        return max(safe_size, 15.0)

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Check Max Concurrent
        active_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id: active_count += 1
        
        if active_count >= self.params['max_concurrent']: return

        # 2. Check 5m RSI (Injected)
        rsi_5m = float(indicators.get('rsi_5m', 50.0))
        if rsi_5m >= self.params['rsi_5m_entry']: return
        
        # 3. Green Candle Check (on 5m? or 1m?)
        # Let's use 1m Green Candle as trigger trigger within the 5m setup
        # Or Price > 5m Close? live price > 5m Open?
        # indicators.get('close_5m') is the *Last Closed* 5m candle close.
        # This is useless for live candle color.
        # Check 1m Green
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price <= candle_open: return

        # Entry
        size_eur = self.calc_safe_entry_size()
        c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
        if c:
             # Override size
             qty = size_eur / price
             # Check constraints again with qty? PaperWallet handles balance check.
             if self.wallet.open_position(symbol, 'LONG', price, quantity=qty):
                 if self.on_event: self.on_event("Open_DCA_Base", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
         # 1. Fixed Net Take Profit (0.75%)
         pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
         
         if pnl_net_pct >= self.params.get('take_profit_net_pct', 0.75):
             logging.info(f"[{self.id}] TP Hit {pos['symbol']} @ {price} (Net: {pnl_net_pct:.2f}%)")
             if self.wallet.close_position(t_id, price):
                 if self.on_event: self.on_event("Close_TP_Net", self.id, pos['symbol'], price, indicators)
             return

         # 2. Check DCA Step
         # Current Drawdown
         avg_price = pos['avg_price']
         pnl_pct = (price - avg_price) / avg_price
         
         current_step = pos.get('dca_step', 0)
         if current_step >= len(self.dca_steps): return # Max Steps Reached
         
         next_cfg = self.dca_steps[current_step]
         target_drop = next_cfg['drop']
         
         if pnl_pct <= target_drop:
             # Trigger DCA
             # Wait for Green Candle? Ideally yes, but DCA is "buying the dip".
             # Let's just buy limit. Or market if touched.
             
             # Calculate Size
             # Base Size was initial. 
             # We need to know base size. 
             # Approx: entry_size = pos['size'] (if step 0).
             # Better: Recalculate safe size or store initial base size in pos?
             # Let's recalculate simply: 
             # If step 0 (1 unit), step 1 adds 1.5 units.
             # Current size = 1 unit. New buy = 1.5 * Current Size ? NO.
             # New buy = 1.5 * (Initial Base).
             # We can deduce initial base roughly: pos['size'] / sum(prev_mults).
             
             # Simplified: Just buy Multiplier * (Current Pos Size / Sum_Mult_So_FAr).
             # Too complex. Let's just buy Multiplier * (Safe Entry Size).
             base_eur = self.calc_safe_entry_size()
             buy_eur = base_eur * next_cfg['mult']
             
             qty = buy_eur / price
             
             if self.wallet.add_to_position(t_id, price, qty):
                 pos['dca_step'] = current_step + 1
                 logging.info(f"[{self.id}] DCA Step {current_step+1} Exectued for {pos['symbol']}")
                 if self.on_event: self.on_event(f"DCA_Step_{current_step+1}", self.id, pos['symbol'], price, indicators)

class StrategyNetScalpDCA(BaseStrategy):
    """
    NetScalp_DCA: Operates on fixed Net Profit (0.05 EUR) with DCA Safety Orders.
    Entry: RSI < 30 + 1m Bullish Confirmation.
    """
    def __init__(self, wallet):
        super().__init__("NetScalp", wallet)
        self.name = "NetScalp DCA"
        self.dca_enabled = True # Uses Safety Orders
        self.params.update({
            'rsi_long_max': 40,
            'profit_trailing_dist_eur': 0.05,
            'max_dca_count': 5,
            'dca_step_pct': 0.015
        })
        
    def check_entry_logic(self, symbol, price, indicators):
        # Only LONG logic specified in request (Dip Buying)
        
        # 1. Base Signal: RSI < 30
        rsi = float(indicators.get('rsi', 50))
        cond_rsi = rsi < self.params['rsi_long_max']
        
        # Alternative: Fib Deep Pullback? 
        # Processor 'fib_level' is 0 (Low) to 1 (High). Deep pullback usually means Fib < 0.2?
        # User said "Fib 0.618 or higher" which was ambiguous. Strict RSI is safer for now.
        
        if not cond_rsi: return
        
        # 2. Confirmation: 1m Candle Close > Prev High
        # Calculated in Processor
        is_conf = str(indicators.get('1m_conf_bullish', False)).lower() == 'true'
        
        if is_conf:
             # Check Trend? User didn't specify trend filter, just "Anti-Trap".
             # RSI < 30 is the trap condition. 1m Conf is the trigger.
             
             if self.on_event: self.on_event("Opportunity", self.id, symbol, price, indicators)
             
             c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
             if c:
                 t_id = self.wallet.open_position(symbol, 'LONG', price)
                 if t_id is not None:
                     # Initial Target Calculation
                     self.recalculate_target(t_id, price)
                     if self.on_event: self.on_event("Open_NetScalp", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # 1. Check Trailing Stop Exit
        # Calculate current Net PnL
        gross = self.wallet.calc_pnl_gross(t_id, price)
        
        # Est Fees
        val_exit = pos['size'] * price
        if pos['type'] == 'LONG': fee_rate = config.FEE_SPOT_TAKER
        else: fee_rate = config.FEE_FUTURES_TAKER
        
        fees_total = pos.get('itemized_fees', 0.0) + (val_exit * fee_rate)
        net_val = gross - fees_total
        
        # Activation
        act_eur = self.params.get('profit_activation_eur', 0.05)
        init_stop_eur = self.params.get('profit_initial_stop_eur', 0.04)
        trail_dist_eur = self.params.get('profit_trailing_dist_eur', 0.03)

        is_active = pos.get('ts_status') == "ACTIVE"
        
        if not is_active:
            if net_val >= act_eur:
                # Activate
                pos['ts_status'] = "ACTIVE"
                
                # Set Initial Stop (Lock 0.04)
                stop_price = self.get_price_for_net_pnl(t_id, init_stop_eur)
                pos['ts_price'] = stop_price
                
                logging.info(f"[{self.id}] NetScalp Activated {pos['symbol']} @ {price:.4f} (Net: {net_val:.4f}). Stop set to {stop_price:.4f} (+{init_stop_eur} EUR)")
                
        else:
            # Update Trailing Stop
            # Desired Stop based on Trailing Distance
            # If Net = 0.10, Trail = 0.03 -> Target Stop PnL = 0.07
            target_stop_pnl = net_val - trail_dist_eur
            
            # Convert PnL to Price
            new_stop_price = self.get_price_for_net_pnl(t_id, target_stop_pnl)
            
            # Logic: Stop can only move UP (for Long)
            current_stop = pos.get('ts_price', 0)
            
            if pos['type'] == 'LONG':
                if new_stop_price > current_stop:
                    pos['ts_price'] = new_stop_price
                
                # Check Exit
                if price <= pos['ts_price']:
                    logging.info(f"[{self.id}] NetScalp TS Exit {pos['symbol']} @ {price:.4f} (TS: {pos['ts_price']:.4f})")
                    if self.wallet.close_position(t_id, price):
                         if self.on_event: self.on_event("Close_NetScalp", self.id, pos['symbol'], price, indicators)
                    return
            else:
                 # SHORT logic (if ever used)
                 # Stop must move DOWN
                 if current_stop == 0 or new_stop_price < current_stop:
                     pos['ts_price'] = new_stop_price
                     
                 if price >= pos['ts_price']:
                      self.wallet.close_position(t_id, price)
                      return

        # 2. Check DCA (Safety Orders)
        # Trigger: Drop 1.5% from Last Entry (or Avg?)
        # User: "Caída: El mercado cae a 108,35€ (1.5% de caída). El agente compra otros 50€."
        # This implies 1.5% drop from Previous Purchase Price.
        
        if pos['dca_count'] >= self.params['max_dca_count']:
            return # Max Safety Orders reached
            
        last_entry = pos.get('last_dca_price', pos['entry_price'])
        drop_pct = self.params.get('dca_step_pct', 0.015)
        
        dca_trigger = last_entry * (1.0 - drop_pct)
        
        if price <= dca_trigger:
             logging.info(f"[{self.id}] DCA Safety Trigger {pos['symbol']} @ {price:.4f} (< {dca_trigger:.4f})")
             # Execute DCA
             if self.wallet.execute_dca(t_id, price):
                 # Recalculate Target based on NEW Avg and Size
                 self.recalculate_target(t_id, price)
                 if self.on_event: self.on_event("DCA_Safety", self.id, pos['symbol'], price, indicators)

    def recalculate_target(self, t_id, current_price):
        """
        Calculates exit price to achieve exactly 0.05 EUR Net Profit.
        Target P = (Total_Invested + Entry_Fees_Paid + Target_Net) / (Size * (1 - Fee_Exit))
        """
        pos = self.wallet.positions.get(t_id)
        if not pos: return
        
        total_size = pos['size']
        total_margin = pos['margin'] 
        fees_paid = pos.get('itemized_fees', 0.0) # Entry + DCA fees so far
        target_net = self.params.get('profit_activation_eur', 0.05)
        
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        
        # Formula:
        # Exit_Val * (1 - Fee) - Cost_Basis = Net
        # Cost_Basis = Margin + Fees_Paid (Wait. 'margin' is just pure coin value at entry? No.)
        # Wallet: margin = size * avg_price in Spot (Leverage=1).
        # Fees are paid externally from balance.
        # So 'Cost Basis' to recover is `margin` + `fees_paid`.
        # We need to end up with `margin` + `Net` + `fees_paid` returned to balance?
        # Balance Delta = (ExitVal - ExitFee) - (Margin + FeesPaid).
        # We want Balance Delta = +Net.
        # (ExitVal * (1-Rate)) - Margin - FeesPaid = Net.
        # ExitVal * (1-Rate) = Net + Margin + FeesPaid.
        
        numerator = target_net + total_margin + fees_paid
        denominator = total_size * (1 - fee_rate)
        
        if denominator == 0: return
        
        target_price = numerator / denominator
        
        target_price = numerator / denominator
        
        # Just for visualization (Yellow line in GUI usually comes from ts_price)
        # We set it to ACTIVATION price initially so user knows where it starts trailing
        pos['ts_price'] = target_price 
        # pos['ts_status'] = "TARGET" # Don't set TARGET status, keep WAIT until active
        
        logging.info(f"[{self.id}] New Actv. Target for #{t_id}: {target_price:.4f} (Avg: {pos['avg_price']:.4f})")

    def get_price_for_net_pnl(self, t_id, target_net_eur):
        """Calculates price required to achieve specific Net PnL (EUR)."""
        pos = self.wallet.positions.get(t_id)
        if not pos: return 0.0
        
        total_size = pos['size']
        total_margin = pos['margin'] 
        fees_paid = pos.get('itemized_fees', 0.0)
        
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        
        numerator = target_net_eur + total_margin + fees_paid
        denominator = total_size * (1 - fee_rate)
        
        if denominator == 0: return 0.0
        return numerator / denominator




class StrategyRollingDCAV2(BaseStrategy):
    """
    RollingDCA v2 (Dynamic & Granular):
    - Filters: ADX>15, VRel>1.5, RSI(5m)<40.
    - Entry: Balance / 50 (~10€).
    - DCA: 1% of entry for every 1% drop from initial entry price.
    - Exit: Trailing Stop (Act +1.0%, Dist 0.3%).
    """
    def __init__(self, wallet, allowed_sides=['LONG']):
        super().__init__("RollingDCA_v2", wallet)
        self.name = "Rolling DCA v2"
        self.allowed_sides = allowed_sides
        self.dca_enabled = True 
        
        self.params.update({
            'rsi_5m_entry': 40.0,
            'adx_min': 15.0,
            'vrel_min': 1.5,
            'take_profit_net_pct': 0.75, 
            'ts_activation_pct': 1.0,
            'ts_distance_pct': 0.3,
            'max_concurrent': 3
        })

    def check_entry_logic(self, symbol, price, indicators):
        # 1. RSI 5m Check
        rsi_5m = float(indicators.get('rsi_5m', 50.0))
        if rsi_5m >= self.params['rsi_5m_entry']: return
        
        # 2. Green Candle (1m)
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price <= candle_open: return

        # 3. Max Concurrent
        active_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id: active_count += 1
        if active_count >= self.params['max_concurrent']: return

        # Entry Size: Balance / 50
        base_eur = self.wallet.balance_eur / 50.0
        if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT

        c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
        if c:
             qty = base_eur / price
             t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
             if t_id:
                 pos = self.wallet.positions[t_id]
                 pos['initial_entry_val'] = base_eur
                 pos['last_dca_level'] = 0
                 if self.on_event: self.on_event("Open_DCA_V2", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
         # Hard Take Profit (0.75% Net)
         pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
         if pnl_net_pct >= self.params.get('take_profit_net_pct', 0.75):
             logging.info(f"[{self.id}] Hard TP Hit {pos['symbol']} @ {price} (Net: {pnl_net_pct:.2f}%)")
             if self.wallet.close_position(t_id, price):
                 if self.on_event: self.on_event("Close_TP_Net", self.id, pos['symbol'], price, indicators)
             return

         avg_price = pos['avg_price']
         entry_price = pos['entry_price']
         
         # 1. Trailing Stop Logic
         # highest_price is already tracked in PaperWallet.update_max_stats
         current_high_pnl = (pos.get('highest_price', price) - avg_price) / avg_price * 100.0
         current_low_pnl = (price - avg_price) / avg_price * 100.0
         
         ts_active = pos.get('ts_active', False)
         ts_stop_level_pct = pos.get('ts_stop_level_pct', -100.0)
         
         if not ts_active:
             if current_high_pnl >= self.params['ts_activation_pct']:
                 ts_active = True
                 pos['ts_active'] = True
         
         if ts_active:
             potential_stop = current_high_pnl - self.params['ts_distance_pct']
             if potential_stop > ts_stop_level_pct:
                 ts_stop_level_pct = potential_stop
                 pos['ts_stop_level_pct'] = ts_stop_level_pct
                 
             # Check Exit
             if current_low_pnl <= ts_stop_level_pct:
                 logging.info(f"[{self.id}] TS Hit {pos['symbol']} @ {price} (Stop: {ts_stop_level_pct:.2f}%)")
                 if self.wallet.close_position(t_id, price):
                     if self.on_event: self.on_event("Close_TS_V2", self.id, pos['symbol'], price, indicators)
                 return

         # 2. Granular DCA Logic
         # 1% of entry_value for every 1% drop from initial entry_price
         drop_from_entry = (entry_price - price) / entry_price
         target_dca_level = int(drop_from_entry * 100)
         last_dca_level = pos.get('last_dca_level', 0)
         
         if target_dca_level > last_dca_level:
             initial_val = pos.get('initial_entry_val', entry_price * pos['size'])
             dca_unit_eur = initial_val * 0.01 # 1% of initial entry
             
             for level in range(last_dca_level + 1, target_dca_level + 1):
                 qty = dca_unit_eur / price
                 if self.wallet.add_to_position(t_id, price, qty):
                     logging.info(f"[{self.id}] DCA Level {level} for {pos['symbol']}")
                     if self.on_event: self.on_event(f"DCA_Level_{level}", self.id, pos['symbol'], price, indicators)
             
             pos['last_dca_level'] = target_dca_level
             
             # Reset Trailing Stop State after DCA to prevent phantom exits
             pos['ts_active'] = False
             pos['ts_stop_level_pct'] = -100.0

class StrategyRollingDCAV3(BaseStrategy):
    """
    RollingDCA v3 ("Smart Scale-In"):
    - Entry: Base 1€ + Steps 1€ (Max 15€).
    - Conditions: ADX>15, VRel>1.5, RSI<40 (Checked for Initial AND DCA).
    - DCA Trigger: Distance >= 1.5% from AvgPrice.
    - Exit: Trailing Stop (Act +1.2% Net, Dist 0.3%).
    """
    def __init__(self, wallet):
        super().__init__("RollingDCA_v3", wallet)
        self.name = "Rolling DCA v3"
        self.allowed_sides = ['LONG']
        
        self.params.update({
            'base_size_eur': 1.0,
            'dca_size_eur': 1.0,
            'max_exposure_eur': 15.0,
            'max_concurrent': 3,
            
            # Technicals
            'rsi_long_max': 40.0,
            'adx_min': 15.0,
            'vrel_min': 1.5,
            
            # Smart DCA
            'dca_min_distance_pct': 0.015, # 1.5%
            
            'profit_target_eur': 0.15, # New parameter for fixed EUR profit
        })

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Technical Filters (Mandatory for ALL entries)
        rsi = float(indicators.get('rsi', 50))
        if rsi >= self.params['rsi_long_max']: return
        
        adx = float(indicators.get('ADX_14', 0))
        if adx <= self.params['adx_min']: return
        
        vrel = float(indicators.get('vrel', 0))
        if vrel <= self.params['vrel_min']: return

        # 2. Check Context (New vs DCA)
        existing_pos = None
        active_symbols_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id:
                # Count unique symbols logic? 
                # Wallet positions are keyed by ID. We iterate all.
                # Simplification: Just count positions. 
                # Ideally we want unique symbol count, but since we merge into one pos per symbol here...
                # effectively count is symbols.
                 active_symbols_count += 1
                 if p['symbol'] == symbol:
                     existing_pos = p
                     
        if existing_pos:
            # --- DCA Logic ---
            # Check Max Exposure
            if existing_pos['margin'] + self.params['dca_size_eur'] > self.params['max_exposure_eur']:
                return # Exposure Limit Reached

            # Check Price Distance
            avg_price = existing_pos['avg_price']
            dist_req = self.params['dca_min_distance_pct']
            target_price = avg_price * (1 - dist_req)
            
            if price > target_price:
                 logging.info(f"[{self.id}] Signal Ignored {symbol}: Price distance < {dist_req*100}%")
                 return

            # Execute DCA
            base_eur = self.wallet.balance_eur * 0.002 # 0.2% of balance
            if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
            qty = base_eur / price
            if self.wallet.add_to_position(existing_pos['id'], price, qty):
                 if self.on_event: self.on_event("DCA_Step_Smart", self.id, symbol, price, indicators)
        
        else:
            # --- New Entry Logic ---
            if active_symbols_count >= self.params['max_concurrent']: return
            
            base_eur = self.wallet.balance_eur * 0.002 # 0.2% of balance
            if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
            qty = base_eur / price
            if self.wallet.open_position(symbol, 'LONG', price, quantity=qty):
                if self.on_event: self.on_event("Open_RollingV3", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # Modified: Only close if net pnl >= target (strictly positive)
        net_val = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        
        # Take Profit Target
        if net_val >= self.params['profit_target_eur']:
             logging.info(f"[{self.id}] Aggressive TP Hit {pos['symbol']} @ {price} (Net: {net_val:.2f} EUR)")
             if self.wallet.close_position(t_id, price):
                 if self.on_event: self.on_event("Close_Aggressive_TP", self.id, pos['symbol'], price, indicators)
             return

class StrategyRollingDCAShort(BaseStrategy):
    """
    Rol_dca_sh_v1: Short version of RollingDCA.
    Entry: RSI > 60 + Red Candle (Price > Open).
    DCA: Martingala on rises (+1.5%, +3%, +5%).
    Exit: 1% Net Profit.
    """
    def __init__(self, wallet):
        super().__init__("Rol_dca_sh_v1", wallet)
        self.name = "Rolling DCA Short"
        self.allowed_sides = ['SHORT']
        self.dca_enabled = True 
        
        # DCA Config (Rise triggers)
        self.dca_steps = [
            {'rise': 0.015, 'mult': 1.5}, 
            {'rise': 0.030, 'mult': 2.0}, 
            {'rise': 0.050, 'mult': 3.0}
        ]
        
        self.params.update({
            'rsi_5m_short': 60.0,
            'take_profit_net_pct': 1.0,
            'max_concurrent': 3
        })

    def calc_safe_entry_size(self):
        total_mult = 1.0 + sum(s['mult'] for s in self.dca_steps)
        equity = self.wallet.balance_eur 
        equity = max(equity, 500.0) 
        safe_size = equity / (self.params['max_concurrent'] * total_mult)
        return max(safe_size, 15.0)

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Check Max Concurrent
        active_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id: active_count += 1
        
        if active_count >= self.params['max_concurrent']: return

        # 2. RSI > 60
        rsi_5m = float(indicators.get('rsi_5m', 50.0))
        if rsi_5m <= self.params['rsi_5m_short']: return
        
        # 3. Red/pump Candle Check (Selling the rip)
        # We want to sell when price is HIGH in the candle
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price >= candle_open: # Above open
             # Entry
             size_eur = self.calc_safe_entry_size()
             c, r = self.wallet.can_open_new(symbol, 'SHORT', {symbol: price})
             if c:
                 qty = size_eur / price
                 if self.wallet.open_position(symbol, 'SHORT', price, quantity=qty):
                     if self.on_event: self.on_event("Open_DCA_Short_Base", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
         # 1. Fixed Net Take Profit (1.0%)
         pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
         if pnl_net_pct >= self.params.get('take_profit_net_pct', 1.0):
             logging.info(f"[{self.id}] TP Hit {pos['symbol']} @ {price} (Net: {pnl_net_pct:.2f}%)")
             if self.wallet.close_position(t_id, price):
                 if self.on_event: self.on_event("Close_TP_Net", self.id, pos['symbol'], price, indicators)
             return

         # 2. Check DCA Step (Short)
         # Drawdown = Price went UP
         avg_price = pos['avg_price']
         # PnL roughly: (Entry - Price) / Entry. 
         # If Price > Entry, PnL is negative.
         # We want to check if Price has Risen by X%.
         rise_pct = (price - avg_price) / avg_price
         
         current_step = pos.get('dca_step', 0)
         if current_step >= len(self.dca_steps): return 
         
         next_cfg = self.dca_steps[current_step]
         target_rise = next_cfg['rise']
         
         if rise_pct >= target_rise:
              # DCA Sell
              base_eur = self.calc_safe_entry_size()
              sell_eur = base_eur * next_cfg['mult']
              qty = sell_eur / price
              
              if self.wallet.add_to_position(t_id, price, qty):
                  pos['dca_step'] = current_step + 1
                  logging.info(f"[{self.id}] DCA Short Step {current_step+1} Executed for {pos['symbol']}")
                  if self.on_event: self.on_event(f"DCA_Step_{current_step+1}", self.id, pos['symbol'], price, indicators)


class StrategyRollingDCAShortV2(BaseStrategy):
    """
    Rol_dca_sh_v2: Short version of V2.
    Entry: RSI > 60.
    DCA: Fixed Value (+4%, +8%, +12%).
    Exit: 1% Net Profit.
    """
    def __init__(self, wallet):
        super().__init__("Rol_dca_sh_v2", wallet)
        self.name = "Rolling DCA Short v2"
        self.allowed_sides = ['SHORT']
        self.dca_enabled = True 
        
        self.dca_steps = [
            {'rise': 0.04, 'val': 15.0}, 
            {'rise': 0.08, 'val': 20.0}, 
            {'rise': 0.12, 'val': 30.0}
        ]
        
        self.params.update({
            'rsi_5m_short': 60.0,
            'base_size_eur': 10.0,
            'take_profit_net_pct': 1.0,
            'max_concurrent': 3
        })

    def check_entry_logic(self, symbol, price, indicators):
        rsi_5m = float(indicators.get('rsi_5m', 50.0))
        if rsi_5m <= self.params['rsi_5m_short']: return
        
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price >= candle_open:
             base_eur = self.wallet.balance_eur * 0.02 # 2.0% of balance
             if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
             c, r = self.wallet.can_open_new(symbol, 'SHORT', {symbol: price})
             if c:
                 qty = base_eur / price
                 if self.wallet.open_position(symbol, 'SHORT', price, quantity=qty):
                     if self.on_event: self.on_event("Open_DCA_Short_V2", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
         pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
         if pnl_net_pct >= self.params.get('take_profit_net_pct', 1.0):
             logging.info(f"[{self.id}] TP Hit {pos['symbol']} @ {price} (Net: {pnl_net_pct:.2f}%)")
             if self.wallet.close_position(t_id, price):
                 if self.on_event: self.on_event("Close_TP_Net", self.id, pos['symbol'], price, indicators)
             return

         avg_price = pos['avg_price']
         rise_pct = (price - avg_price) / avg_price
         
         current_step = pos.get('dca_step', 0)
         if current_step >= len(self.dca_steps): return 
         
         next_cfg = self.dca_steps[current_step]
         target_rise = next_cfg['rise']
         
         if rise_pct >= target_rise:
              # Calculate size based on current balance % (3%, 4%, 6%)
              dca_pcts = [0.03, 0.04, 0.06]
              dca_pct = dca_pcts[current_step] if current_step < len(dca_pcts) else 0.06
              sell_eur = max(self.wallet.balance_eur * dca_pct, config.MIN_ENTRY_AMT)
              
              qty = sell_eur / price
              if self.wallet.add_to_position(t_id, price, qty):
                  pos['dca_step'] = current_step + 1
                  if self.on_event: self.on_event(f"DCA_Short_V2_Step_{current_step+1}", self.id, pos['symbol'], price, indicators)


class StrategyRollingDCAShortV3(BaseStrategy):
    """
    Rol_dca_sh_v3: Short Smart Scale-In.
    Entries: RSI > 60 + ADX > 15 + VRel > 1.5.
    DCA: Smart Distance (Price > Avg + 1.5%).
    Exit: 1% Net Profit.
    """
    def __init__(self, wallet):
        super().__init__("Rol_dca_sh_v3", wallet)
        self.name = "Rolling DCA Short v3"
        self.allowed_sides = ['SHORT']
        
        self.params.update({
            'base_size_eur': 1.0,
            'dca_size_eur': 1.0,
            'max_exposure_eur': 15.0,
            'max_concurrent': 3,
            
            'rsi_short_min': 60.0,
            'adx_min': 15.0,
            'vrel_min': 1.5,
            'dca_min_distance_pct': 0.015, # 1.5%
            'take_profit_net_pct': 1.0,
        })

    def check_entry_logic(self, symbol, price, indicators):
        rsi = float(indicators.get('rsi', 50))
        if rsi <= self.params['rsi_short_min']: return
        
        adx = float(indicators.get('ADX_14', 0))
        if adx <= self.params['adx_min']: return
        
        vrel = float(indicators.get('vrel', 0))
        if vrel <= self.params['vrel_min']: return

        existing_pos = None
        active_symbols_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id:
                 active_symbols_count += 1
                 if p['symbol'] == symbol:
                     existing_pos = p
                     
        if existing_pos:
            # Check Max Exposure
            if existing_pos['margin'] + self.params['dca_size_eur'] > self.params['max_exposure_eur']:
                return 

            # Smart Distance (Short: Price must be HIGHER than Avg)
            avg_price = existing_pos['avg_price']
            dist_req = self.params['dca_min_distance_pct']
            target_price = avg_price * (1 + dist_req)
            
            if price < target_price:
                 logging.info(f"[{self.id}] Signal Ignored {symbol}: Price distance < {dist_req*100}%")
                 return

            base_eur = self.wallet.balance_eur * 0.002 # 0.2% of balance
            if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
            qty = base_eur / price
            if self.wallet.add_to_position(existing_pos['id'], price, qty):
                 if self.on_event: self.on_event("DCA_Short_Step_Smart", self.id, symbol, price, indicators)
        
        else:
            if active_symbols_count >= self.params['max_concurrent']: return
            
            base_eur = self.wallet.balance_eur * 0.002 # 0.2% of balance
            if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
            qty = base_eur / price
            # Sell the Rip logic (Price >= Open) for initial too?
            candle_open = float(indicators.get('Open', -1))
            if candle_open > 0 and price >= candle_open:
                if self.wallet.open_position(symbol, 'SHORT', price, quantity=qty):
                    if self.on_event: self.on_event("Open_RolShortV3", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
         # 1. Fixed Net Take Profit (1.0%)
         pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
         if pnl_net_pct >= self.params.get('take_profit_net_pct', 1.0):
             logging.info(f"[{self.id}] TP Hit {pos['symbol']} @ {price} (Net: {pnl_net_pct:.2f}%)")
             if self.wallet.close_position(t_id, price):
                 if self.on_event: self.on_event("Close_TP_Net", self.id, pos['symbol'], price, indicators)
             return


class StrategyAspiradora(BaseStrategy):
    """
    Aspiradora PRO:
    - RSI <= 12 (Long) / RSI >= 88 (Short).
    - VRel >= 1.5.
    - ADX >= 20.
    - Size: Balance / 50.
    - Exit: Trailing Stop (Act 0.25%, Dist 0.1%).
    """
    def __init__(self, wallet, allowed_sides=['LONG', 'SHORT']):
        super().__init__("Aspiradora", wallet)
        self.name = "Aspiradora PRO"
        self.allowed_sides = allowed_sides
        self.dca_enabled = False
        
        self.params.update({
            'rsi_long_max': 30,
            'rsi_long_min': 20,
            'rsi_long_exit': 70,
            'profit_target_eur': 0.15,
            'max_concurrent': 5
        })

    def check_entry_logic(self, symbol, price, indicators):
        rsi = float(indicators.get('rsi', 50))
        vrel = float(indicators.get('vrel', 0))
        adx = float(indicators.get('ADX_14', 0))
        
        # 1. Base Checks
        if vrel < self.params['vrel_min']: return
        if adx < self.params['adx_min']: return
        
        # 2. Max Concurrent
        active_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id: active_count += 1
        if active_count >= self.params['max_concurrent']: return

        # 3. Entry Logic
        side = None
        if rsi <= self.params['rsi_long_max'] and 'LONG' in self.allowed_sides:
            side = 'LONG'
        elif rsi >= self.params['rsi_short_min'] and 'SHORT' in self.allowed_sides:
            side = 'SHORT'
            
        if side:
            base_eur = self.wallet.balance_eur / 50.0
            if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
            
            c, r = self.wallet.can_open_new(symbol, side, {symbol: price})
            if c:
                qty = base_eur / price
                if self.wallet.open_position(symbol, side, price, quantity=qty):
                    if self.on_event: self.on_event(f"Open_Aspiradora_{side}", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        avg_price = pos['avg_price']
        
        # Trailing Stop Logic
        if pos['type'] == 'LONG':
            current_high_pnl = (pos.get('highest_price', price) - avg_price) / avg_price * 100.0
            current_low_pnl = (price - avg_price) / avg_price * 100.0
        else: # SHORT
            current_high_pnl = (avg_price - pos.get('lowest_price', price)) / avg_price * 100.0
            current_low_pnl = (avg_price - price) / avg_price * 100.0
            
        ts_active = pos.get('ts_active', False)
        ts_stop_level_pct = pos.get('ts_stop_level_pct', -100.0)
        
        if not ts_active:
            if current_high_pnl >= self.params['ts_activation_pct']:
                ts_active = True
                pos['ts_active'] = True
        
        if ts_active:
            potential_stop = current_high_pnl - self.params['ts_distance_pct']
            if potential_stop > ts_stop_level_pct:
                ts_stop_level_pct = potential_stop
                pos['ts_stop_level_pct'] = ts_stop_level_pct
                
            # Check Exit
            if current_low_pnl <= ts_stop_level_pct:
                logging.info(f"[{self.id}] Aspiradora TS Hit {pos['symbol']} @ {price} (Stop: {ts_stop_level_pct:.2f}%)")
                if self.wallet.close_position(t_id, price):
                    if self.on_event: self.on_event("Close_Aspiradora_TS", self.id, pos['symbol'], price, indicators)

class StrategyHormiga(BaseStrategy):
    """
    S17: Hormiga / Grinder - High Frequency Sniper
    - Entry: RSI(14) <= 15 (LONG) or >= 85 (SHORT).
    - Extra Filter: VRel >= 1.5.
    - Size: Balance / 50.
    - Exit: Trailing Stop (Act 0.25%, Dist 0.1%).
    """
    def __init__(self, wallet, allowed_sides=['LONG', 'SHORT']):
        super().__init__("Hormiga", wallet)
        self.name = "Hormiga / Grinder"
        self.allowed_sides = allowed_sides
        self.dca_enabled = False
        
        self.params.update({
            'rsi_long_max': 15.0,
            'rsi_short_min': 85.0,
            'vrel_min': 1.5,
            'ts_activation_pct': 0.25,
            'ts_distance_pct': 0.1,
            'max_concurrent': 5
        })

    def check_entry_logic(self, symbol, price, indicators):
        rsi = float(indicators.get('rsi', 50))
        vrel = float(indicators.get('vrel', 0))
        adx = float(indicators.get('ADX_14', 0))
        
        # 1. Base Checks
        if vrel < self.params['vrel_min']: return
        
        # 2. Max Concurrent
        active_count = 0
        for p in self.wallet.positions.values():
            if p.get('strategy') == self.id: active_count += 1
        if active_count >= self.params['max_concurrent']: return

        # 3. Entry Logic
        side = None
        if rsi <= self.params['rsi_long_max'] and 'LONG' in self.allowed_sides:
            side = 'LONG'
        elif rsi >= self.params['rsi_short_min'] and 'SHORT' in self.allowed_sides:
            side = 'SHORT'
            
        if side:
            base_eur = self.wallet.balance_eur / 50.0
            if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT
            
            c, r = self.wallet.can_open_new(symbol, side, {symbol: price})
            if c:
                qty = base_eur / price
                if self.wallet.open_position(symbol, side, price, quantity=qty):
                    if self.on_event: self.on_event(f"Open_Hormiga_{side}", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        avg_price = pos['avg_price']
        
        # Trailing Stop Logic (identical to Aspiradora for tight exit)
        if pos['type'] == 'LONG':
            current_high_pnl = (pos.get('highest_price', price) - avg_price) / avg_price * 100.0
            current_low_pnl = (price - avg_price) / avg_price * 100.0
        else: # SHORT
            current_high_pnl = (avg_price - pos.get('lowest_price', price)) / avg_price * 100.0
            current_low_pnl = (avg_price - price) / avg_price * 100.0
            
        ts_active = pos.get('ts_active', False)
        ts_stop_level_pct = pos.get('ts_stop_level_pct', -100.0)
        
        if not ts_active:
            if current_high_pnl >= self.params['ts_activation_pct']:
                ts_active = True
                pos['ts_active'] = True
                logging.info(f"[{self.id}] Hormiga TS Activated for {pos['symbol']} at {current_high_pnl:.2f}%")
        
        if ts_active:
            potential_stop = current_high_pnl - self.params['ts_distance_pct']
            if potential_stop > ts_stop_level_pct:
                ts_stop_level_pct = potential_stop
                pos['ts_stop_level_pct'] = ts_stop_level_pct
                
            # Check Exit
            if current_low_pnl <= ts_stop_level_pct:
                logging.info(f"[{self.id}] Hormiga TS Hit {pos['symbol']} @ {price} (Stop: {ts_stop_level_pct:.2f}%)")
                if self.wallet.close_position(t_id, price):
                    if self.on_event: self.on_event("Close_Hormiga_TS", self.id, pos['symbol'], price, indicators)

class StrategyNetScalpRolling(BaseStrategy):
    """
    NetScalp Rolling DCA: 
    - Exit: Target 0.05€ Profit. TS Acts @ 0.05€, Init 0.02€, Dist 0.04€.
    - DCA: 1% initial entry reinvested every 1% drop (Rolling v2 style).
    - Entry: RSI < 30 + 1m Bullish Confirmation.
    """
    def __init__(self, wallet):
        super().__init__("NetScalp_Rolling", wallet)
        self.name = "NetScalp Rolling"
        self.dca_enabled = True
        
        self.params.update({
            'rsi_long_max': 30.0,
            'dca_step_pct': 0.010, # 1.0%
            'reinvest_pct': 0.010, # 1.0%
            'profit_activation_eur': 0.05,
            'profit_initial_stop_eur': 0.02,
            'profit_trailing_dist_eur': 0.04
        })

    def check_entry_logic(self, symbol, price, indicators):
        rsi = float(indicators.get('rsi', 50))
        if rsi >= self.params['rsi_long_max']: return
        
        is_conf = str(indicators.get('1m_conf_bullish', False)).lower() == 'true'
        if not is_conf: return

        if self.on_event: self.on_event("Opportunity", self.id, symbol, price, indicators)
        
        c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
        if c:
            t_id = self.wallet.open_position(symbol, 'LONG', price)
            if t_id is not None:
                # Store initial investment for DCA scaling
                pos = self.wallet.positions[t_id]
                pos['initial_entry_val'] = pos['margin']
                pos['last_dca_level'] = 0
                if self.on_event: self.on_event("Open_NetScalp_Roll", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # 1. Exit Logic (Fixed Profit Trailing)
        gross = self.wallet.calc_pnl_gross(t_id, price)
        val_exit = pos['size'] * price
        fee_rate = config.FEE_SPOT_TAKER # NetScalp is Spot Long
        fees_total = pos.get('itemized_fees', 0.0) + (val_exit * fee_rate)
        net_val = gross - fees_total
        
        act_eur = self.params['profit_activation_eur']
        init_stop_eur = self.params['profit_initial_stop_eur']
        trail_dist_eur = self.params['profit_trailing_dist_eur']

        if pos.get('ts_status') != "ACTIVE":
            if net_val >= act_eur:
                pos['ts_status'] = "ACTIVE"
                # Re-use calculation logic if possible, or direct:
                stop_price = self.get_price_for_net_pnl(t_id, init_stop_eur)
                pos['ts_price'] = stop_price
                logging.info(f"[{self.id}] NS_Roll Activated {pos['symbol']} @ {price:.4f} (Net: {net_val:.4f}). Stop: {stop_price:.4f}")
        else:
            # Update Trailing
            target_stop_pnl = net_val - trail_dist_eur
            new_stop_price = self.get_price_for_net_pnl(t_id, target_stop_pnl)
            
            if new_stop_price > pos.get('ts_price', 0):
                pos['ts_price'] = new_stop_price
            
            # Check Trigger
            if price <= pos.get('ts_price', 0):
                logging.info(f"[{self.id}] NS_Roll TS Exit {pos['symbol']} @ {price:.4f}")
                if self.wallet.close_position(t_id, price):
                    if self.on_event: self.on_event("Close_NetScalp_Roll", self.id, pos['symbol'], price, indicators)
                return

        # 2. DCA Logic (1% Drop / 1% Reinvest)
        entry_price = pos['entry_price']
        drop_from_entry = (entry_price - price) / entry_price
        target_dca_level = int(drop_from_entry * 100) # Every 1%
        last_dca_level = pos.get('last_dca_level', 0)
        
        if target_dca_level > last_dca_level:
            dca_unit_eur = pos.get('initial_entry_val', 50.0) * self.params['reinvest_pct']
            
            for level in range(last_dca_level + 1, target_dca_level + 1):
                qty = dca_unit_eur / price
                if self.wallet.add_to_position(t_id, price, qty):
                    logging.info(f"[{self.id}] DCA Level {level} for {pos['symbol']}")
                    if self.on_event: self.on_event(f"DCA_Level_{level}", self.id, pos['symbol'], price, indicators)
            
            pos['last_dca_level'] = target_dca_level
            # Reset TS to allow recovery
            pos['ts_status'] = "WAIT"
            pos['ts_price'] = 0

    def get_price_for_net_pnl(self, t_id, target_net_eur):
        # Re-using the logic from the file
        pos = self.wallet.positions.get(t_id)
        if not pos: return 0.0
        numerator = target_net_eur + pos['margin'] + pos.get('itemized_fees', 0.0)
        fee_rate = config.FEE_SPOT_TAKER
        denominator = pos['size'] * (1.0 - fee_rate)
        return numerator / denominator


class StrategyRollingDCAEvolution(BaseStrategy):
    """
    RollingDCA Evolution (RDE):
    - Anti-Trap Filters: EMA 200 + ADX < 30 (on 5m/1h), MFI < 15, VRel > 1.8.
    - Intelligent DCA:
        Step 1 (-2.5%): RSI(1m) < 20.
        Step 2 (-5.0%): Bullish MFI Divergence.
    - Multiplier: x1.5 (Step 1).
    - Exit: TP 0.60%, TS Activation 0.40%, TS Distance 0.15%.
    """
    def __init__(self, wallet, allowed_sides=['LONG']):
        super().__init__("RollingDCA_v4", wallet)
        self.name = "Rolling DCA Evolution"
        self.allowed_sides = allowed_sides
        self.dca_enabled = True
        
        # DCA Config
        self.dca_steps = [
            {'drop': -0.025, 'mult': 1.5, 'rsi_1m_max': 20.0}, # Step 1: RSI Filter
            {'drop': -0.050, 'mult': 2.0, 'divergence': True}  # Step 2: Divergence Filter
        ]

        self.params.update({
            'mfi_max': 15.0,
            'vrel_min': 1.8,
            'adx_max': 30.0,
            'ema_trend_filter': True, # Price > EMA200 for Longs if ADX > 30
            'take_profit_net_pct': 0.60,
            'ts_activation_pct': 0.40,
            'ts_distance_pct': 0.15,
            'max_concurrent': 3
        })

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Max Concurrent
        active_count = sum(1 for p in self.wallet.positions.values() if p.get('strategy') == self.id)
        if active_count >= self.params['max_concurrent']: return

        # 2. Indicators Extraction
        ema200 = float(indicators.get('ema200', price))
        adx = float(indicators.get('ADX_14', 50.0))
        mfi = float(indicators.get('MFI_14', 50.0))
        vrel = float(indicators.get('vrel', 0.0))
        
        # 3. Anti-Trap Filter (Trend)
        # No LONG if Price < EMA200 AND ADX > 30 (Strong DownTrend)
        if self.params['ema_trend_filter']:
            if price < ema200 and adx > self.params['adx_max']:
                return

        # 4. Capitulation Filter (MFI)
        if mfi >= self.params['mfi_max']: return

        # 5. Confirmation Filter (VRel)
        if vrel < self.params['vrel_min']: return

        # 6. Green Candle Confirmation (Don't catch falling knives)
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price <= candle_open: return

        # Entry Size: Balance / 50
        base_eur = self.wallet.balance_eur / 50.0
        if base_eur < config.MIN_ENTRY_AMT: base_eur = config.MIN_ENTRY_AMT

        c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
        if c:
             qty = base_eur / price
             t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
             if t_id:
                 pos = self.wallet.positions[t_id]
                 pos['initial_entry_val'] = base_eur
                 pos['dca_step'] = 0
                 # Log indicators for divergence check later
                 pos['mfi_history'] = [mfi]
                 pos['price_history'] = [price]
                 if self.on_event: self.on_event("Open_RDE", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # 1. Hard Take Profit (0.60% Net)
        pnl_net_pct = self.wallet.calc_pnl_pct_net(t_id, price)
        if pnl_net_pct >= self.params.get('take_profit_net_pct', 0.60):
            logging.info(f"[{self.id}] Hard TP Hit {pos['symbol']} @ {price} (Net: {pnl_net_pct:.2f}%)")
            if self.wallet.close_position(t_id, price):
                if self.on_event: self.on_event("Close_TP_Net", self.id, pos['symbol'], price, indicators)
            return

        # 2. Trailing Stop Logic
        avg_price = pos['avg_price']
        current_high_pnl = (pos.get('highest_price', price) - avg_price) / avg_price * 100.0
        current_low_pnl = (price - avg_price) / avg_price * 100.0
        
        ts_active = pos.get('ts_active', False)
        ts_stop_level_pct = pos.get('ts_stop_level_pct', -100.0)
        
        if not ts_active and current_high_pnl >= self.params['ts_activation_pct']:
            ts_active = True
            pos['ts_active'] = True
            logging.info(f"[{self.id}] TS Activated for {pos['symbol']} @ {current_high_pnl:.2f}%")
        
        if ts_active:
            potential_stop = current_high_pnl - self.params['ts_distance_pct']
            if potential_stop > ts_stop_level_pct:
                ts_stop_level_pct = potential_stop
                pos['ts_stop_level_pct'] = ts_stop_level_pct
                
            if current_low_pnl <= ts_stop_level_pct:
                logging.info(f"[{self.id}] TS Hit {pos['symbol']} @ {price} (Stop: {ts_stop_level_pct:.2f}%)")
                if self.wallet.close_position(t_id, price):
                    if self.on_event: self.on_event("Close_TS_RDE", self.id, pos['symbol'], price, indicators)
                return

        # 3. Intelligent DCA Logic
        pnl_pct = (price - avg_price) / avg_price
        current_step_idx = pos.get('dca_step', 0)
        
        if current_step_idx < len(self.dca_steps):
            step_cfg = self.dca_steps[current_step_idx]
            
            # Check price drop
            if pnl_pct <= step_cfg['drop']:
                trigger = False
                
                # Step 1: RSI 1m Filter
                if current_step_idx == 0:
                    rsi_1m = float(indicators.get('rsi', 50.0)) # Processor 'rsi' is 1m in 1m loop
                    if rsi_1m <= step_cfg['rsi_1m_max']:
                        trigger = True
                
                # Step 2: Bullish Divergence MFI
                elif current_step_idx == 1:
                    mfi = float(indicators.get('MFI_14', 50.0))
                    # Simplified Divergence: Current MFI > Previous recorded MFI while Price < Previous recorded Price
                    # We store history in pos for this
                    hist_mfi = pos.get('mfi_history', [])
                    hist_price = pos.get('price_history', [])
                    
                    if hist_mfi and hist_price:
                        if mfi > min(hist_mfi) and price < min(hist_price):
                            trigger = True
                    
                    # Update history (keep small)
                    hist_mfi.append(mfi)
                    hist_price.append(price)
                    pos['mfi_history'] = hist_mfi[-10:]
                    pos['price_history'] = hist_price[-10:]

                if trigger:
                    base_val = pos.get('initial_entry_val', 10.0)
                    buy_eur = base_val * step_cfg['mult']
                    qty = buy_eur / price
                    
                    if self.wallet.add_to_position(t_id, price, qty):
                        pos['dca_step'] = current_step_idx + 1
                        pos['ts_active'] = False # Reset TS
                        logging.info(f"[{self.id}] DCA Step {current_step_idx+1} for {pos['symbol']} @ {price}")
                        if self.on_event: self.on_event(f"DCA_Step_{current_step_idx+1}", self.id, pos['symbol'], price, indicators)


class StrategyRollingDCAInmortal(BaseStrategy):
    """
    RollingDCA Inmortal 50%:
    - Coverage: -50% drop via 25 DCA levels.
    - Entry: RSI(14) < 30 + Green Candle (Close > Open).
    - DCA: 25 levels, each triggered at -2.0% from CURRENT Breakeven (Avg Price).
    - Amount per DCA: 1.60€.
    - Exit: Trailing Stop (Trigger 0.40%, Dist 0.10%).
    - Exchange: Optimized for MEXC (Min Order 1 USDT).
    """
    def __init__(self, wallet, allowed_sides=['LONG']):
        super().__init__("RollingDCA_Inmortal", wallet)
        self.name = "Rolling DCA Inmortal 50%"
        self.allowed_sides = allowed_sides
        self.dca_enabled = True
        
        self.params.update({
            'rsi_max': 30.0,
            'dca_drop_pct': 0.02, # 2.0% from Breakeven
            'dca_amount_eur': 1.60,
            'max_dca_steps': 25,
            'take_profit_activation_pct': 0.40,
            'ts_distance_pct': 0.10,
            'max_concurrent': 10,
            'initial_entry_eur': 10.00
        })

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Max Concurrent (Specific to Inmortal Slots)
        active_count = sum(1 for p in self.wallet.positions.values() if p.get('strategy') == self.id)
        if active_count >= self.params['max_concurrent']: return

        # 2. RSI Filter
        rsi = float(indicators.get('rsi', 50.0))
        if rsi >= self.params['rsi_max']: return

        # 3. Green Candle Confirmation
        candle_open = float(indicators.get('Open', -1))
        if candle_open > 0 and price <= candle_open: return

        # 4. Entry
        c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
        if c:
             base_eur = max(self.wallet.balance_eur * 0.02, config.MIN_ENTRY_AMT)
             qty = base_eur / price
             t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
             if t_id:
                 pos = self.wallet.positions[t_id]
                 pos['dca_step'] = 0
                 if self.on_event: self.on_event("Open_Inmortal", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        avg_price = pos['avg_price']
        pnl_pct = (price - avg_price) / avg_price
        
        # 1. Trailing Stop Logic
        current_high_pnl = (pos.get('highest_price', price) - avg_price) / avg_price * 100.0
        current_low_pnl = pnl_pct * 100.0
        
        ts_active = pos.get('ts_active', False)
        ts_stop_level_pct = pos.get('ts_stop_level_pct', -100.0)
        
        if not ts_active and current_high_pnl >= self.params['take_profit_activation_pct']:
            ts_active = True
            pos['ts_active'] = True
            logging.info(f"[{self.id}] TS Activated for {pos['symbol']} @ {current_high_pnl:.2f}%")
        
        if ts_active:
            potential_stop = current_high_pnl - self.params['ts_distance_pct']
            if potential_stop > ts_stop_level_pct:
                ts_stop_level_pct = potential_stop
                pos['ts_stop_level_pct'] = ts_stop_level_pct
                
            if current_low_pnl <= ts_stop_level_pct:
                logging.info(f"[{self.id}] TS Hit {pos['symbol']} @ {price} (Stop: {ts_stop_level_pct:.2f}%)")
                if self.wallet.close_position(t_id, price):
                    if self.on_event: self.on_event("Close_Inmortal_TS", self.id, pos['symbol'], price, indicators)
                return

        # 2. DCA Grid Logic (Geometric 2% from Breakeven)
        current_step = pos.get('dca_step', 0)
        if current_step < self.params['max_dca_steps']:
            # Pnl_pct is already relative to avg_price (Breakeven)
            if pnl_pct <= -self.params['dca_drop_pct']:
                # Trigger DCA
                buy_eur = max(self.wallet.balance_eur * 0.0032, config.MIN_ENTRY_AMT)
                qty = buy_eur / price
                
                if self.wallet.add_to_position(t_id, price, qty):
                    pos['dca_step'] = current_step + 1
                    pos['ts_active'] = False # Reset TS after DCA
                    logging.info(f"[{self.id}] DCA Level {current_step+1} for {pos['symbol']} @ {price}. New Avg: {pos['avg_price']:.4f}")
                    if self.on_event: self.on_event(f"DCA_Inmortal_Step_{current_step+1}", self.id, pos['symbol'], price, indicators)

class StrategyKrakenEvent(BaseStrategy):
    """
    Kraken Sentinel 2026 Strategy (Kraken Event)
    Three-layer strategy with dynamic capital allocation and daily compound interest recalculation.
    Capa 1 (60%): NetScalp Pro
    Capa 2 (20%): Hybrid/Rolling
    Capa 3 (20%): Aspiradora PRO
    """
    def __init__(self, wallet):
        super().__init__("KrakenEvent", wallet)
        self.name = "Kraken Sentinel 2026"
        self.layers = {
            'Layer1': {'weight': 0.60, 'name': 'NetScalp Pro'},
            'Layer2': {'weight': 0.20, 'name': 'Hybrid/Rolling'},
            'Layer3': {'weight': 0.20, 'name': 'Aspiradora PRO'}
        }
        self.params.update({
            'L1_rsi_low': 35,
            'L1_rsi_high': 65,
            'L1_max_dca': 15,
            'L1_dca_mult': 1.05,
            'L1_tp_trigger_eur': 0.12,
            'L1_tp_dist_eur': 0.04,
            
            'L2_rsi_entry': 30,
            'L2_tp_trigger_eur': 0.50,
            'L2_tp_dist_eur': 0.15,
            
            'L3_rsi_capitulation': 13,
            'L3_tp_trigger_eur': 0.20,
            'L3_tp_dist_eur': 0.05,
            
            'kill_switch_hours': 5,
            'kill_switch_tp_eur': 0.01,
            'liquidity_reserve_pct': 0.05
        })
        self.recalculate_sizes()

    def recalculate_sizes(self):
        """Updates order sizes based on Total Equity (Dashboard value or balance)."""
        total_equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
        operable_equity = total_equity * (1 - self.params['liquidity_reserve_pct'])
        
        l1_cap = operable_equity * self.layers['Layer1']['weight']
        self.params['L1_bo_eur'] = l1_cap * 0.02
        self.params['L1_so_eur'] = l1_cap * 0.02
        
        l2_cap = operable_equity * self.layers['Layer2']['weight']
        self.params['L2_bo_eur'] = l2_cap * 0.05
        
        l3_cap = operable_equity * self.layers['Layer3']['weight']
        self.params['L3_bo_eur'] = l3_cap * 0.10
        
        logging.info(f"[{self.id}] Recalculated sizes: L1_BO={self.params['L1_bo_eur']:.2f}, L2_BO={self.params['L2_bo_eur']:.2f}, L3_BO={self.params['L3_bo_eur']:.2f}")

    def on_tick(self, symbol, price, indicators):
        # Daily Recalculated Strategy logic
        super().on_tick(symbol, price, indicators)


    def check_entry_logic(self, symbol, price, indicators):
        btc_dump = indicators.get('btc_15m_crash', False)
        rsi_5m = float(indicators.get('rsi_5m', 50))
        ema200 = float(indicators.get('ema200', 0))
        
        # --- LAYER 1: NetScalp Pro ---
        if not btc_dump:
            if self.params['L1_rsi_low'] <= rsi_5m <= self.params['L1_rsi_high'] and ema200 > 0 and price > ema200:
                if not self.has_layer_pos(symbol, 'Layer1'):
                    qty = self.params['L1_bo_eur'] / price
                    t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
                    if t_id:
                        self.wallet.positions[t_id]['layer'] = 'Layer1'
                        if self.on_event: self.on_event("Open_L1_NetScalp", self.id, symbol, price, indicators)

        # --- LAYER 2: Hybrid/Rolling ---
        if not btc_dump:
            is_green_5m = False
            c5 = indicators.get('current_candle_5m')
            if c5:
                is_green_5m = price > c5['open']
            
            if rsi_5m < self.params['L2_rsi_entry'] and is_green_5m:
                if not self.has_layer_pos(symbol, 'Layer2'):
                    qty = self.params['L2_bo_eur'] / price
                    t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
                    if t_id:
                        self.wallet.positions[t_id]['layer'] = 'Layer2'
                        if self.on_event: self.on_event("Open_L2_Hybrid", self.id, symbol, price, indicators)

        # --- LAYER 3: Aspiradora PRO ---
        if rsi_5m <= self.params['L3_rsi_capitulation']:
            if not self.has_layer_pos(symbol, 'Layer3'):
                qty = self.params['L3_bo_eur'] / price
                t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
                if t_id:
                    self.wallet.positions[t_id]['layer'] = 'Layer3'
                    if self.on_event: self.on_event("Open_L3_Aspiradora", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        layer = pos.get('layer', 'Layer1')
        
        if layer == 'Layer1':
            trigger = self.params['L1_tp_trigger_eur']
            dist = self.params['L1_tp_dist_eur']
            self.manage_l1_dca(t_id, pos, price, indicators)
        elif layer == 'Layer2':
            trigger = self.params['L2_tp_trigger_eur']
            dist = self.params['L2_tp_dist_eur']
        else: # Layer 3
            trigger = self.params['L3_tp_trigger_eur']
            dist = self.params['L3_tp_dist_eur']

        self.manage_trailing_exit(t_id, pos, price, indicators, trigger, dist)

    def manage_l1_dca(self, t_id, pos, price, indicators):
        if pos.get('dca_count', 0) >= self.params['L1_max_dca']:
            return
            
        last_price = pos.get('last_dca_price', pos['entry_price'])
        if price < last_price * 0.985: # 1.5% drop
            qty = (self.params['L1_so_eur'] * (self.params['L1_dca_mult'] ** (pos['dca_count'] + 1))) / price
            if self.wallet.add_to_position(t_id, price, quantity=qty):
                if self.on_event: self.on_event(f"L1_DCA_{pos['dca_count']}", self.id, pos['symbol'], price, indicators)

    def manage_trailing_exit(self, t_id, pos, price, indicators, trigger_eur, dist_eur):
        net_val = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        net_val -= (pos['size'] * price * fee_rate)

        is_active = pos.get('ts_status') == "ACTIVE"
        if not is_active and net_val >= trigger_eur:
            pos['ts_status'] = "ACTIVE"
            pos['ts_price'] = self.get_price_for_net_pnl(t_id, net_val - dist_eur)
            logging.info(f"[{self.id}] TS Activated for #{t_id} {pos['symbol']} at PnL {net_val:.2f}€")
        
        elif is_active:
            new_ts_price = self.get_price_for_net_pnl(t_id, net_val - dist_eur)
            if pos['type'] == 'LONG':
                if new_ts_price > pos.get('ts_price', 0):
                    pos['ts_price'] = new_ts_price
                if price < pos['ts_price']:
                    if self.wallet.close_position(t_id, price):
                        if self.on_event: self.on_event("Close_TS", self.id, pos['symbol'], price, indicators)
            else: # SHORT
                if new_ts_price < pos.get('ts_price', 999999):
                    pos['ts_price'] = new_ts_price
                if price > pos['ts_price']:
                    if self.wallet.close_position(t_id, price):
                        if self.on_event: self.on_event("Close_TS", self.id, pos['symbol'], price, indicators)

    def has_layer_pos(self, symbol, layer):
        for p in self.wallet.positions.values():
            if p['symbol'] == symbol and p.get('layer') == layer:
                return True
        return False

    def get_price_for_net_pnl(self, t_id, target_net_eur):
        pos = self.wallet.positions.get(t_id)
        if not pos: return 0.0
        total_size = pos['size']
        total_margin = pos['margin'] 
        fees_paid = pos.get('itemized_fees', 0.0)
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        numerator = target_net_eur + total_margin + fees_paid
        denominator = total_size * (1 - fee_rate)
        if denominator == 0: return 0.0
        return numerator / denominator

class StrategySentinelTurbo(BaseStrategy):
    """
    Kraken Sentinel Turbo (Leveraged Evolution)
    - Layer 1: NetScalp Pro Turbo (x2 Leverage)
    - Layer 2: HybridElite Turbo (x3 Leverage)
    - Layer 3: Aspiradora PRO Turbo (x10 Leverage)
    - Daily Compound Interest hook.
    - Isolated Margin logic.
    """
    def __init__(self, wallet):
        super().__init__("SentinelTurbo", wallet)
        self.name = "Kraken Sentinel Turbo"
        self.config_path = "data/sentinel_config.json"
        self.config = {}
        self.load_turbo_config()
        self.recalculate_sizes()

    def load_turbo_config(self):
        try:
            import json, os
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                # Update params from config
                self.params.update({
                    'kill_switch_hours': self.config.get('kill_switch_hours', 5),
                    'kill_switch_tp_eur': self.config.get('kill_switch_tp_eur', 0.01),
                    'liquidity_reserve_pct': self.config.get('liquidity_reserve_pct', 0.05)
                })
                logging.info(f"[{self.id}] Config loaded from {self.config_path}")
        except Exception as e:
            logging.error(f"[{self.id}] Error loading turbo config: {e}")

    def recalculate_sizes(self):
        self.load_turbo_config() # Reload just in case
        total_equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
        reserve = self.params.get('liquidity_reserve_pct', 0.05)
        operable_equity = total_equity * (1 - reserve)
        
        layers = self.config.get('layers', {})
        for lid, lcfg in layers.items():
            layer_cap = operable_equity * lcfg['weight']
            # Store calculated BO/SO in params for use in on_tick
            self.params[f'{lid}_bo_val'] = layer_cap * lcfg['bo_pct']
            if 'so_pct' in lcfg:
                self.params[f'{lid}_so_val'] = layer_cap * lcfg['so_pct']
        
        logging.info(f"[{self.id}] Recalculated sizes based on {total_equity:.2f}€ Equity (-{reserve*100}% reserve)")

    def check_entry_logic(self, symbol, price, indicators):
        # Global Filters
        btc_panic = indicators.get('btc_15m_crash', False)
        rsi_5m = float(indicators.get('rsi_5m', 50))
        ema200 = float(indicators.get('ema200', 0))
        layers = self.config.get('layers', {})

        # --- LAYER 1: NetScalp Pro Turbo (x2) ---
        if not btc_panic and 'Layer1' in layers:
            l1 = layers['Layer1']
            # Filter: EMA(200) 5m Trend (Implicit if Price > EMA200 and EMA200 is increasing? Let's use Price > EMA200)
            if price > ema200 > 0:
                if not self.has_layer_pos(symbol, 'Layer1'):
                    val_eur = self.params.get('Layer1_bo_val', 10.0)
                    qty = (val_eur * l1['leverage']) / price
                    t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty, leverage=l1['leverage'])
                    if t_id:
                        self.wallet.positions[t_id]['layer'] = 'Layer1'
                        self.wallet.positions[t_id]['dca_count'] = 0
                        if self.on_event: self.on_event("Open_L1_Turbo", self.id, symbol, price, indicators)

        # --- LAYER 2: HybridElite Turbo (x3) ---
        if not btc_panic and 'Layer2' in layers:
            l2 = layers['Layer2']
            is_green_5m = False
            c5 = indicators.get('current_candle_5m')
            if c5: is_green_5m = price > c5['open']

            if rsi_5m < 30 and is_green_5m:
                # Volume filter (if available in indicators)
                vol_24h = indicators.get('vol_24h', 9999999999) # Default high if unknown
                if vol_24h >= l2.get('min_vol_24h', 500000000):
                    if not self.has_layer_pos(symbol, 'Layer2'):
                        val_eur = self.params.get('Layer2_bo_val', 10.0)
                        qty = (val_eur * l2['leverage']) / price
                        t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty, leverage=l2['leverage'])
                        if t_id:
                            self.wallet.positions[t_id]['layer'] = 'Layer2'
                            if self.on_event: self.on_event("Open_L2_Turbo", self.id, symbol, price, indicators)

        # --- LAYER 3: Aspiradora PRO Turbo (x10) ---
        if 'Layer3' in layers:
            l3 = layers['Layer3']
            if rsi_5m <= 12:
                if not self.has_layer_pos(symbol, 'Layer3'):
                    val_eur = self.params.get('Layer3_bo_val', 10.0)
                    qty = (val_eur * l3['leverage']) / price
                    t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty, leverage=l3['leverage'])
                    if t_id:
                        self.wallet.positions[t_id]['layer'] = 'Layer3'
                        if self.on_event: self.on_event("Open_L3_Turbo", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        layer_id = pos.get('layer', 'Layer1')
        l_cfg = self.config.get('layers', {}).get(layer_id, {})
        
        # Layer Specific Management
        if layer_id == 'Layer1':
            self.manage_l1_dca(t_id, pos, price, indicators, l_cfg)
            self.manage_trailing_exit(t_id, pos, price, indicators, l_cfg['tp_trigger_eur'], l_cfg['tp_dist_eur'])
        elif layer_id == 'Layer2':
            self.manage_trailing_exit(t_id, pos, price, indicators, l_cfg['tp_trigger_eur'], l_cfg['tp_dist_eur'])
        elif layer_id == 'Layer3':
            # Fixed TP/SL for L3 (x10 leverage makes trailing risky)
            pnl_pct = (price - pos['avg_price']) / pos['avg_price'] * 100.0
            if pnl_pct >= l_cfg['tp_pct_price']:
                logging.info(f"[{self.id}] L3 TP Hit {pos['symbol']} @ {price} ({pnl_pct:.2f}%)")
                self.wallet.close_position(t_id, price)
            elif pnl_pct <= -l_cfg['sl_pct_price']:
                logging.info(f"[{self.id}] L3 SL Hit {pos['symbol']} @ {price} ({pnl_pct:.2f}%)")
                self.wallet.close_position(t_id, price)

    def manage_l1_dca(self, t_id, pos, price, indicators, l_cfg):
        dca_count = pos.get('dca_count', 0)
        if dca_count >= l_cfg['max_dca']: return
        
        last_price = pos.get('last_dca_price', pos['entry_price'])
        if price < last_price * 0.985: # 1.5% drop
            so_val = self.params.get('Layer1_so_val', 10.0)
            mult = l_cfg['dca_mult'] ** (dca_count + 1)
            qty = (so_val * mult * l_cfg['leverage']) / price
            if self.wallet.add_to_position(t_id, price, quantity=qty):
                pos['dca_count'] = dca_count + 1
                pos['last_dca_price'] = price
                if self.on_event: self.on_event(f"L1_Turbo_DCA_{pos['dca_count']}", self.id, pos['symbol'], price, indicators)

    def manage_trailing_exit(self, t_id, pos, price, indicators, trigger_eur, dist_eur):
        net_val = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        fee_rate = config.FEE_SPOT_TAKER # Assuming spot/futures taker fees
        net_val -= (pos['size'] * price * fee_rate)

        if pos.get('ts_status') != "ACTIVE" and net_val >= trigger_eur:
            pos['ts_status'] = "ACTIVE"
            pos['ts_price'] = self.get_price_for_net_pnl(t_id, net_val - dist_eur)
            logging.info(f"[{self.id}] TS Active #{t_id} {pos['symbol']} | Stop: {pos['ts_price']:.4f}")
        elif pos.get('ts_status') == "ACTIVE":
            new_stop = self.get_price_for_net_pnl(t_id, net_val - dist_eur)
            if new_stop > pos.get('ts_price', 0): pos['ts_price'] = new_stop
            if price <= pos['ts_price']:
                if self.wallet.close_position(t_id, price):
                    if self.on_event: self.on_event("Close_Turbo_TS", self.id, pos['symbol'], price, indicators)

    def get_price_for_net_pnl(self, t_id, target_net):
        pos = self.wallet.positions.get(t_id)
        if not pos: return 0.0
        # Correctly use total position value (size * avg_price) instead of margin (which is fraction when leveraged)
        pos_value = pos['size'] * pos['avg_price']
        numerator = target_net + pos_value + pos.get('itemized_fees', 0.0)
        fee_rate = config.FEE_SPOT_TAKER
        denominator = pos['size'] * (1 - fee_rate)
        return numerator / denominator if denominator != 0 else 0.0

    def has_layer_pos(self, symbol, layer):
        return any(p['symbol'] == symbol and p.get('layer') == layer for p in self.wallet.positions.values())


class StrategyAntigravity(BaseStrategy):
    """
    Antigravity Strategy
    - Entry: RSI < 32, VRel > 1.5, Green Candle (1m/5m)
    - Exit: Min 0.35% Net, TP 0.8%, TS Act 0.5%, Dist 0.15%
    - Defense: 25 levels of DCA every -2%, 1.60€ each.
    - Recovery TS: If DCA > 3, Act 0.30%, Dist 0.10%
    """
    def __init__(self, wallet):
        super().__init__("Antigravity", wallet)
        self.name = "Antigravity Sniper"
        self.config_path = "data/antigravity_config.json"
        self.config = {}
        self.load_config()

    def load_config(self):
        try:
            import json, os
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                logging.info(f"[{self.id}] Config loaded from {self.config_path}")
        except Exception as e:
            logging.error(f"[{self.id}] Error loading config: {e}")

    def check_entry_logic(self, symbol, price, indicators):
        # Synchronization with StrategyProcessor: Use rsi_5m and handle vrel naming
        rsi = float(indicators.get('rsi_5m', indicators.get('rsi', 50)))
        vrel = float(indicators.get('vrel', indicators.get('VRel', 0)))
        
        # entry config
        e_cfg = self.config.get('entry', {'rsi_max': 32, 'vrel_min': 1.5, 'bo_eur': 10.0})
        max_slots = self.config.get('max_slots', 10)
        
        if len(self.wallet.positions) >= max_slots:
            return

        if rsi < e_cfg['rsi_max'] and vrel > e_cfg['vrel_min']:
            # Green Candle Confirmation (1m or 5m - using current candle available)
            is_green = False
            curr_candle = indicators.get('current_candle') # 1m
            if not curr_candle: curr_candle = indicators.get('current_candle_5m')
            
            if curr_candle:
                is_green = price > curr_candle['open']
            else:
                # Fallback if no candle info: trust RSI/VRel
                is_green = True
            
            if is_green:
                if not self.has_pos(symbol):
                    equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
                    bo_eur = max(equity * 0.025, config.MIN_ENTRY_AMT)
                    qty = bo_eur / price
                    t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
                    if t_id:
                        self.wallet.positions[t_id]['dca_count'] = 0
                        logging.info(f"[{self.id}] Entry Triggered for {symbol} @ {price} (RSI={rsi:.2f}, VRel={vrel:.2f})")
                        if self.on_event: self.on_event("Open_Antigravity", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        d_cfg = self.config.get('defense', {})
        x_cfg = self.config.get('exit', {})
        
        # 1. DCA / Defense logic
        dca_count = pos.get('dca_count', 0)
        if dca_count < d_cfg.get('dca_levels', 25):
            last_price = pos.get('last_dca_price', pos['entry_price'])
            drop_pct = (price - last_price) / last_price * 100.0
            
            if drop_pct <= -d_cfg.get('dca_step_pct', 2.0):
                equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
                dca_eur = max(equity * 0.004, config.MIN_ENTRY_AMT)
                qty = dca_eur / price
                if self.wallet.add_to_position(t_id, price, quantity=qty):
                    pos['dca_count'] = dca_count + 1
                    pos['last_dca_price'] = price
                    logging.info(f"[{self.id}] DCA Level {pos['dca_count']} for {pos['symbol']} @ {price}")

        # 2. Exit Logic
        # Calculate net PnL %
        net_val = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        fee_rate = config.FEE_SPOT_TAKER
        net_val -= (pos['size'] * price * fee_rate)
        
        # Net % relative to margin (investment)
        net_pct = (net_val / pos['margin']) * 100.0 if pos['margin'] > 0 else 0
        
        # Trailing Stop Activation
        is_recovery = pos.get('dca_count', 0) > 3
        
        if is_recovery:
            act_threshold = d_cfg.get('recovery_ts_activation', 0.30)
            callback = d_cfg.get('recovery_ts_callback', 0.10)
        else:
            act_threshold = x_cfg.get('ts_activation_pct', 0.50)
            callback = x_cfg.get('ts_callback_pct', 0.15)
            

        # Take Profit Hard Limit
        if net_pct >= x_cfg.get('tp_pct', 0.80):
             logging.info(f"[{self.id}] Hard TP Hit for {pos['symbol']} @ {price} ({net_pct:.2f}%)")
             self.wallet.close_position(t_id, price)
             return

        # Trailing Logic
        is_active = pos.get('ts_status') == "ACTIVE"
        if not is_active and net_pct >= act_threshold:
            pos['ts_status'] = "ACTIVE"
            pos['ts_high_net'] = net_pct
            logging.info(f"[{self.id}] TS Activated for #{t_id} {pos['symbol']} @ Net {net_pct:.2f}%")
        
        elif is_active:
            if net_pct > pos.get('ts_high_net', -999):
                pos['ts_high_net'] = net_pct
            
            # Check callback
            if net_pct < (pos['ts_high_net'] - callback):
                # Verify minimum net profit
                min_net = x_cfg.get('min_net_pct', 0.35) if not is_recovery else 0.05
                if net_pct >= min_net:
                    logging.info(f"[{self.id}] TS Callback Triggered for #{t_id} {pos['symbol']} @ Net {net_pct:.2f}%")
                    self.wallet.close_position(t_id, price)

    def has_pos(self, symbol):
        return any(p['symbol'] == symbol for p in self.wallet.positions.values())


class StrategySaintGrial(BaseStrategy):
    """
    Saint-Grial Master Strategy
    Dynamic capital management and regime-based execution.
    """
    def __init__(self, wallet):
        super().__init__("SaintGrial", wallet)
        self.name = "Saint-Grial Master"
        self.config_path = "data/saint_grial_config.json"
        self.config = {}
        self.load_config()

    def load_config(self):
        try:
            import json, os
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                logging.info(f"[{self.id}] Config loaded from {self.config_path}")
            else:
                self.config = {
                    "max_slots": 10, "capital_division": 20, "reserve_pct": 0.50,
                    "regimes": {
                        "HALCON": {"adx_min": 25, "rsi_max": 45, "min_profit_pct": 0.80, "ts_activation": 1.0, "ts_callback": 0.25},
                        "ASPIRADORA": {"adx_max": 20, "rsi_max": 30, "tp_fixed": 0.75},
                        "BUNKER": {"vrel_min": 2.0, "rsi_capitulation": 20, "dca_levels": 25, "dca_step": 2.0, "dca_amount_base": 1.60}
                    }
                }
        except Exception as e:
            logging.error(f"[{self.id}] Error loading config: {e}")

    def determine_regime(self, indicators):
        adx = float(indicators.get('ADX_14', 0))
        vrel = float(indicators.get('vrel', indicators.get('VRel', 0)))
        btc_crash = indicators.get('btc_15m_crash', False)
        
        if btc_crash or vrel > self.config['regimes']['BUNKER'].get('vrel_min', 2.0):
            return "BUNKER"
        
        if adx > self.config['regimes']['HALCON'].get('adx_min', 25):
            w_ratio = float(indicators.get('Wick_Body_Ratio', 1.0))
            if w_ratio < 0.5:
                return "HALCON"
        
        if adx < self.config['regimes']['ASPIRADORA'].get('adx_max', 20):
            return "ASPIRADORA"
            
        return "HALCON"

    def check_entry_logic(self, symbol, price, indicators):
        regime = self.determine_regime(indicators)
        rsi = float(indicators.get('rsi_5m', indicators.get('rsi', 50)))
        
        if len(self.wallet.positions) >= self.config.get('max_slots', 10):
            return

        is_green = False
        curr_c = indicators.get('current_candle')
        if curr_c: is_green = price > curr_c['open']
        if not is_green: return

        total_equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
        entry_eur = total_equity / self.config.get('capital_division', 20)
        
        should_enter = False
        if regime == "HALCON":
            ema20 = float(indicators.get('EMA_20', indicators.get('EMA_50', 0)))
            if (ema20 > 0 and price <= ema20 * 1.005) or rsi < self.config['regimes']['HALCON']['rsi_max']:
                should_enter = True
        
        elif regime == "ASPIRADORA":
            if rsi < self.config['regimes']['ASPIRADORA']['rsi_max']:
                should_enter = True
                
        elif regime == "BUNKER":
            if rsi < self.config['regimes']['BUNKER']['rsi_capitulation']:
                should_enter = True

        if should_enter and not self.has_pos(symbol):
            qty = entry_eur / price
            t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
            if t_id:
                self.wallet.positions[t_id]['regime'] = regime
                self.wallet.positions[t_id]['dca_count'] = 0
                logging.info(f"[{self.id}] Saint-Grial entered {symbol} in mode {regime} @ {price}")
                if self.on_event: self.on_event("Open_SaintGrial", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        regime = pos.get('regime', 'HALCON')
        net_pnl_pct = self.calc_net_pnl_pct(t_id, price, pos)
        
        MIN_BENEFIT = 0.40

        if regime == "BUNKER" or net_pnl_pct < -5.0:
            self.run_bunker_protocol(t_id, pos, price, net_pnl_pct)
            if regime == "BUNKER" and net_pnl_pct >= 0.30:
                self.wallet.close_position(t_id, price)
                return

        if regime == "HALCON":
            cfg = self.config['regimes']['HALCON']
            is_active = pos.get('ts_status') == "ACTIVE"
            if not is_active and net_pnl_pct >= cfg['ts_activation']:
                pos['ts_status'] = "ACTIVE"
                pos['ts_high'] = net_pnl_pct
            
            elif is_active:
                if net_pnl_pct > pos.get('ts_high', -999): pos['ts_high'] = net_pnl_pct
                if net_pnl_pct < (pos['ts_high'] - cfg['ts_callback']):
                    if net_pnl_pct >= cfg['min_profit_pct']:
                         self.wallet.close_position(t_id, price)
                         return

        elif regime == "ASPIRADORA":
            cfg = self.config['regimes']['ASPIRADORA']
            if net_pnl_pct >= cfg['tp_fixed'] and net_pnl_pct >= MIN_BENEFIT:
                self.wallet.close_position(t_id, price)

    def run_bunker_protocol(self, t_id, pos, price, net_pnl_pct):
        cfg = self.config['regimes']['BUNKER']
        dca_count = pos.get('dca_count', 0)
        if dca_count >= cfg['dca_levels']: return

        last_dca = pos.get('last_dca_price', pos['entry_price'])
        drop = (price - last_dca) / last_dca * 100.0
        
        if drop <= -cfg['dca_step']:
            qty = cfg['dca_amount_base'] / price
            if self.wallet.add_to_position(t_id, price, quantity=qty):
                pos['dca_count'] = dca_count + 1
                pos['last_dca_price'] = price
                logging.info(f"[{self.id}] Bunker DCA Level {pos['dca_count']} for {pos['symbol']} @ {price}")

    def calc_net_pnl_pct(self, t_id, price, pos):
        gross = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        fee_rate = config.FEE_SPOT_TAKER
        net_val = gross - (pos['size'] * price * fee_rate)
        return (net_val / pos['margin']) * 100.0 if pos['margin'] > 0 else 0

    def has_pos(self, symbol):
        return any(p['symbol'] == symbol for p in self.wallet.positions.values())


class StrategySaintGrialProX3(BaseStrategy):
    """
    ESTRATEGIA "SAINT-GRIAL PRO X3"
    Protocolo de ejecución unificado.
    - Capital Base: 500 €
    - Monto por Operación: 1/3 del Capital Total.
    - Apalancamiento: x3 ISOLATED.
    - Slots Máximos: 1.
    - Reserva Inmortal: 2/3 para rescate de 25 niveles.
    - Modos: HALCÓN, ASPIRADORA, BÚNKER.
    """
    def __init__(self, wallet):
        super().__init__("SaintGrialProX3", wallet)
        self.name = "Saint-Grial Pro X3"
        self.max_slots = 1
        self.leverage = 3
        self.compound_interest_mode = True
        
        self.params.update({
            'activation_pct': 0.60,
            'callback_pct': 0.20,
            'rsi_safety_limit': 28,
            'min_profit_with_rsi': 0.40,
            'bunker_dca_levels': 25,
            'adx_halcon': 25,
            'adx_aspiradora': 20
        })

    def get_entry_size(self):
        # 1/3 of total equity (reserving 10% for leverage fees)
        equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
        return (equity * 0.9) / 3.0

    def check_entry_logic(self, symbol, price, indicators):
        # 1. Max Slots (Unificado: Solo 1 activo)
        if len(self.wallet.positions) >= self.max_slots: return

        # 2. RSI (5m) Priority
        # Priorizar el activo con el RSI más bajo del universo (5m)
        rsi_5m = float(indicators.get('rsi_5m', 50))
        is_min = indicators.get('is_global_min_rsi', False)
        
        if rsi_5m > 30: return # Filtro base
        if not is_min: return  # Prioridad al más bajo solamente

        # 3. Entry execution
        c, r = self.wallet.can_open_new(symbol, 'LONG', {symbol: price})
        if c:
            size_eur = self.get_entry_size()
            # x3 isolated position size
            qty = (size_eur * self.leverage) / price
            t_id = self.wallet.open_position(symbol, 'LONG', price, quantity=qty)
            if t_id:
                pos = self.wallet.positions[t_id]
                pos['leverage'] = self.leverage
                pos['max_pnl_net'] = -100.0
                logging.info(f"[{self.id}] Saint-Grial PRO X3 Entry {symbol} @ {price} (RSI: {rsi_5m:.2f})")
                if self.on_event: self.on_event("Open_SGProX3", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # 1. Regime Selector
        adx = float(indicators.get('ADX_14', 0))
        drop_15m = float(indicators.get('drop_15m_pct', 0))
        
        mode = "NORMAL"
        if drop_15m >= 3.0: mode = "BUNKER"
        elif adx > self.params['adx_halcon']: mode = "HALCON"
        elif adx < self.params['adx_aspiradora']: mode = "ASPIRADORA"

        # 2. Bunker Protocol (25 Levels DCA)
        if mode == "BUNKER":
            self.run_bunker_dca(t_id, pos, price)
            
        # 3. Trailing Stop Exit (Anti-Loss)
        net_pnl_pct = self.calc_net_pnl(t_id, price, pos)
        
        # Current High Water Mark Update
        if net_pnl_pct > pos.get('max_pnl_net', -100):
            pos['max_pnl_net'] = net_pnl_pct

        act = self.params['activation_pct']
        cb = self.params['callback_pct']
        
        if mode == "HALCON": cb = 0.15 # Aggressive
        if mode == "ASPIRADORA": act = 0.40; cb = 0.10 # Fast

        if pos.get('ts_active') or pos['max_pnl_net'] >= act:
            pos['ts_active'] = True
            
            # Check for Callback Exit
            if net_pnl_pct <= (pos['max_pnl_net'] - cb):
                # 4. Filter Safety: RSI < 28 (wait for bounce)
                rsi = float(indicators.get('rsi', 50))
                if rsi < self.params['rsi_safety_limit'] and net_pnl_pct < self.params['min_profit_with_rsi']:
                    return # Blocked
                
                # Check for net profit > 0 (Prohibido cerrar en negativo)
                if net_pnl_pct > 0:
                    logging.info(f"[{self.id}] Trailing {mode} Exit {pos['symbol']} @ {price} (PnL: {net_pnl_pct:.2f}%)")
                    if self.wallet.close_position(t_id, price):
                        if self.on_event: self.on_event(f"Close_SGProX3_{mode}", self.id, pos['symbol'], price, indicators)

    def run_bunker_dca(self, t_id, pos, price):
        dca_count = pos.get('dca_count', 0)
        if dca_count >= self.params['bunker_dca_levels']: return
        
        last_price = pos.get('last_dca_price', pos['entry_price'])
        drop = (last_price - price) / last_price * 100.0
        
        if drop >= 2.0: # Mínimo 2% entre niveles
            equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
            # Use 2/3 of capital for 25 levels (reserving 10% for leverage fees)
            dca_size = (equity * 0.9 * 2/3) / self.params['bunker_dca_levels']
            qty = (dca_size * self.leverage) / price
            
            if self.wallet.add_to_position(t_id, price, quantity=qty):
                pos['dca_count'] = dca_count + 1
                pos['last_dca_price'] = price
                logging.info(f"[{self.id}] Bunker DCA Level {pos['dca_count']} for {pos['symbol']} @ {price}")

    def calc_net_pnl(self, t_id, price, pos):
        gross = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        fee_exit = (pos['size'] * price * config.FEE_SPOT_TAKER)
        net_val = gross - fee_exit
        return (net_val / pos['margin']) * 100.0 if pos['margin'] > 0 else 0


class StrategyVectorFlujoV1(BaseStrategy):
    """
    ESTRATEGIA "VectorFlujo_V1"
    Decisión Macro (EMA 200 15m) + Fuerza (ADX > 20)
    Gestiíon Sniper x3 con Defensa Búnker (DCA) y Cierre Estructural.
    """
    def __init__(self, wallet):
        super().__init__("VectorFlujo_V1", wallet)
        self.name = "VectorFlujo V1"
        self.max_slots = 1
        self.leverage = 3
        
        self.params.update({
            'activation_pct': 0.60,
            'callback_pct': 0.15,
            'adx_min': 20.0,
            'dca_levels': 15,
            'rescue_levels': 25,
            'invalidation_candles_threshold': 2
        })
        
        # Invalidation counters: { t_id: count }
        self.invalidation_state = {}
        self.last_candle_5m_ts = {} 

        # Log Path
        self.perf_log = "logs/VectorFlujo_performance.log"
        if not os.path.exists("logs"):
            os.makedirs("logs")

    def get_entry_size(self):
        equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
        return (equity * 0.9) / 3.0

    def check_entry_logic(self, symbol, price, indicators):
        if len(self.wallet.positions) >= self.max_slots: return

        # Macro Filters (15m)
        ema200_15m = float(indicators.get('ema200_15m', 0))
        adx_15m = float(indicators.get('adx_15m', 0))
        
        if ema200_15m == 0: return # No data yet

        # 1. Macro Direction & Strength
        side = None
        if price > ema200_15m and adx_15m > self.params['adx_min']:
            side = 'LONG'
        elif price < ema200_15m and adx_15m > self.params['adx_min']:
            side = 'SHORT'
        
        if not side: return

        # 2. Execution
        c, r = self.wallet.can_open_new(symbol, side, {symbol: price})
        if c:
            size_eur = self.get_entry_size()
            qty = (size_eur * self.leverage) / price
            t_id = self.wallet.open_position(symbol, side, price, quantity=qty)
            if t_id:
                pos = self.wallet.positions[t_id]
                pos['leverage'] = self.leverage
                pos['max_pnl_net'] = -100.0
                pos['ema200_entry'] = ema200_15m
                self.invalidation_state[t_id] = 0
                self.last_candle_5m_ts[t_id] = indicators.get('timestamp_5m')
                
                logging.info(f"[{self.id}] VectorFlujo Entry {side} {symbol} @ {price} (ADX: {adx_15m:.1f}, EMA200_15m: {ema200_15m:.2f})")
                if self.on_event: self.on_event("Open_VectorFlujo", self.id, symbol, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        # 1. Update Exit Benchmarks
        net_pnl_pct = self.calc_net_pnl_pct(t_id, price, pos)
        if net_pnl_pct > pos.get('max_pnl_net', -100):
            pos['max_pnl_net'] = net_pnl_pct

        # 1.1 Breakeven Exit for Rescue Mode
        if pos.get('rescue_mode') and net_pnl_pct >= 0.01:
            self.close_with_log(t_id, price, "Rescue_Breakeven_Exit", indicators)
            return

        # 2. Trailing Stop
        act = self.params['activation_pct']
        cb = self.params['callback_pct']
        
        if pos.get('ts_active') or pos['max_pnl_net'] >= act:
            pos['ts_active'] = True
            if net_pnl_pct <= (pos['max_pnl_net'] - cb):
                if net_pnl_pct > 0: # Safety
                    self.close_with_log(t_id, price, f"Trailing_Stop_{net_pnl_pct:.2f}%", indicators)
                    return

        # 3. Invalidation Check (Structural Stop)
        # Check every time a 5m candle closes
        current_5m_ts = indicators.get('timestamp_5m')
        if current_5m_ts != self.last_candle_5m_ts.get(t_id):
            self.last_candle_5m_ts[t_id] = current_5m_ts
            
            ema200_15m = float(indicators.get('ema200_15m', 0))
            close_5m = float(indicators.get('close_5m', 0))
            
            invalid = False
            if pos['side'] == 'LONG' and close_5m < ema200_15m:
                invalid = True
            elif pos['side'] == 'SHORT' and close_5m > ema200_15m:
                invalid = True
                
            if invalid:
                self.invalidation_state[t_id] = self.invalidation_state.get(t_id, 0) + 1
                if self.invalidation_state[t_id] >= self.params['invalidation_candles_threshold']:
                    # CONDITION: Only exit if net_pnl > 0.5%
                    if net_pnl_pct > 0.5:
                        self.close_with_log(t_id, price, "Structural_Invalidity", indicators)
                        return
                    # PROTECTION: If in loss, enter Rescue Mode
                    elif net_pnl_pct < 0:
                        if not pos.get('rescue_mode'):
                            pos['rescue_mode'] = True
                            logging.info(f"[{self.id}] !!! POSITION IN LOSS CROSSING EMA !!! Activating Rescue Protocol (25 Levels) for {pos['symbol']} #{t_id}")
            else:
                self.invalidation_state[t_id] = 0 # Reset if back in trend

        # 4. Bunker DCA
        self.check_dca(t_id, pos, price, indicators)

    def check_dca(self, t_id, pos, price, indicators):
        dca_count = pos.get('dca_count', 0)
        is_rescue = pos.get('rescue_mode', False)
        max_levels = self.params['rescue_levels'] if is_rescue else self.params['dca_levels']

        if dca_count >= max_levels: return
        
        # Tendencia macro debe seguir a favor (SKIP IF RESCUE MODE)
        if not is_rescue:
            ema200_15m = float(indicators.get('ema200_15m', 0))
            if pos['side'] == 'LONG' and price < ema200_15m: return
            if pos['side'] == 'SHORT' and price > ema200_15m: return

        last_price = pos.get('last_dca_price', pos['entry_price'])
        
        if pos['side'] == 'LONG':
            drop = (last_price - price) / last_price * 100.0
        else:
            drop = (price - last_price) / last_price * 100.0
            
        if drop >= 1.5: # 1.5% distance for DCA levels
            equity = self.wallet.balance_eur + sum(p['margin'] for p in self.wallet.positions.values())
            # Distribution: Same dca_size but allows more levels if rescue (with 10% reserve)
            div_val = self.params['rescue_levels'] if is_rescue else self.params['dca_levels']
            dca_size = (equity * 0.9 * 2/3) / div_val
            qty = (dca_size * self.leverage) / price
            
            if self.wallet.add_to_position(t_id, price, quantity=qty):
                pos['dca_count'] = dca_count + 1
                pos['last_dca_price'] = price
                mode_str = "RESCUE" if is_rescue else "STANDARD"
                logging.info(f"[{self.id}] VectorFlujo {mode_str} DCA Level {pos['dca_count']} for {pos['symbol']} @ {price}")

    def close_with_log(self, t_id, price, reason, indicators):
        pos = self.wallet.positions.get(t_id)
        if not pos: return
        
        symbol = pos['symbol']
        pnl_pct = self.calc_net_pnl_pct(t_id, price, pos)
        
        # Capture Hormiga/Sentinel Status via Processor
        comparativa = {}
        if hasattr(self, 'processor'):
            comparativa = self.processor.get_strategies_summary()
        
        log_entry = {
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'symbol': symbol,
            'side': pos['side'],
            'entry': pos['entry_price'],
            'exit': price,
            'pnl_pct': f"{pnl_pct:.2f}%",
            'reason': reason,
            'dca_count': pos.get('dca_count', 0),
            'ema200_15m': indicators.get('ema200_15m'),
            'adx_15m': indicators.get('adx_15m'),
            'comparativa': comparativa
        }
        
        # Write to log
        with open(self.perf_log, "a") as f:
            f.write(str(log_entry) + "\n")
            
        logging.info(f"[{self.id}] Closing {symbol} @ {price} | Reason: {reason} | PnL: {pnl_pct:.2f}%")
        
        if self.wallet.close_position(t_id, price):
            if self.on_event: self.on_event(f"Close_VectorFlujo_{reason}", self.id, symbol, price, indicators)

    def calc_net_pnl_pct(self, t_id, price, pos):
        gross = self.wallet.calc_pnl_gross(t_id, price) - pos.get('itemized_fees', 0)
        fee_exit = (pos['size'] * price * config.FEE_SPOT_TAKER)
        net_val = gross - fee_exit
        return (net_val / pos['margin']) * 100.0 if pos['margin'] > 0 else 0
