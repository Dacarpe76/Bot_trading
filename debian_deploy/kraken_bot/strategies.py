import logging
import time
from kraken_bot import config

class BaseStrategy:
    def __init__(self, strategy_id, wallet):
        self.id = strategy_id
        self.wallet = wallet
        self.dca_enabled = True
        self.paused = False 
        self.on_event = None
        
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
        
        # 2. RSI Filters
        # LONG
        if rsi < self.params.get('rsi_long_max', 100):

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
                self.manage_position(t_id, pos, price, indicators)

    def manage_position(self, t_id, pos, price, indicators):
        pass


class StrategyAggressive(BaseStrategy): 
    """S3: Aggressive (No DCA) + Momentum Crash Entry"""
    def __init__(self, wallet):
        super().__init__("Aggressive", wallet)
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
        if base_L or climax_L: side = 'LONG'
        if base_S or climax_S: side = 'SHORT'
        
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
                pos['last_ts_update'] = time.time()
            else:
                # Time Advance
                ts = current_ts
                if time.time() - pos.get('last_ts_update', pos['entry_time']) > 600:
                     ts += (atr * 0.1)
                     pos['last_ts_update'] = time.time()

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
    def __init__(self, wallet):
        super().__init__("AggrCent", wallet)
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
            'profit_step_eur': 0.01 
        })

    def check_entry_logic(self, symbol, price, indicators):
         # S4 Same as S3
        if 'vrel' not in indicators: return
        vrel = float(indicators.get('vrel', 0))
        err = float(indicators.get('err', 0))
        rsi = float(indicators.get('rsi', 50))
        
        base_L = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi < self.params['rsi_long_max'])
        base_S = (vrel > self.params['vrel_min']) and (err > self.params['err_min']) and (rsi > self.params['rsi_short_min'])
        
        climax_L = (vrel > self.params['climax_vrel']) and (rsi < self.params['climax_rsi_long'])
        climax_S = (vrel > self.params['climax_vrel']) and (rsi > self.params['climax_rsi_short'])
        
        side = None
        if base_L or climax_L: side = 'LONG'
        if base_S or climax_S: side = 'SHORT'
        
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
            if time.time() - pos.get('last_stop_move_time', time.time()) >= 300:
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

class StrategyNetScalpDCA(BaseStrategy):
    """
    NetScalp_DCA: Operates on fixed Net Profit (0.05 EUR) with DCA Safety Orders.
    Entry: RSI < 30 + 1m Bullish Confirmation.
    """
    def __init__(self, wallet):
        super().__init__("NetScalp", wallet)
        self.dca_enabled = True # Uses Safety Orders
        
        self.params.update({
            'rsi_long_max': 30.0,
            'dca_step_pct': 0.020, # 2.0%
            'max_dca_count': 3,
            'profit_activation_eur': 0.05,
            'profit_initial_stop_eur': 0.04,
            'profit_trailing_dist_eur': 0.01
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
