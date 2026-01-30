import logging
import time
import json
import os
import requests
from kraken_bot import config

STATE_FILE = "wallet_state.json"

class PaperWallet:
    def __init__(self, strategy_id="S1", initial_balance=config.INITIAL_BALANCE, capital_limit_pct=config.CAPITAL_LIMIT_PCT):
        self.strategy_id = strategy_id
        self.state_file = f"wallet_state_{strategy_id}.json"
        
        self.balance_eur = initial_balance 
        self.start_time = time.time() # Track start for APY
        
        # Capital Limit Override (For Aggressive Strategies)
        self.capital_limit_pct = capital_limit_pct

        # Position Structure:
        # {
        #   id: {
        #      symbol: 'XBT/EUR', type: 'LONG'/'SHORT', size: float, margin: float, 
        #      avg_price: float, entry_price: float, entry_time: float, 
        #      dca_count: int, last_dca_price: float,
        #      highest_price: float, lowest_price: float 
        #   }
        # }
        self.positions = {} 
        self.trades_history = []
        self.next_trade_id = 1
        
        self.load_state()

    def save_state(self):
        try:
            state = {
                'balance': self.balance_eur,
                'positions': self.positions,
                'history': self.trades_history,
                'next_id': self.next_trade_id,
                'start_time': self.start_time
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save wallet {self.strategy_id} state: {e}")

    def load_state(self):
        if not os.path.exists(self.state_file):
             return
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                self.balance_eur = state.get('balance', self.balance_eur)
                self.start_time = state.get('start_time', time.time()) # Load start time
                # Ensure keys are integers if JSON converts to string keys?
                # JSON keys are always strings. We use int IDs.
                raw_pos = state.get('positions', {})
                self.positions = {}
                for k, v in raw_pos.items():
                    self.positions[int(k)] = v
                
                self.trades_history = state.get('history', [])
                self.next_trade_id = state.get('next_id', 1)
            logging.info(f"Loaded Wallet {self.strategy_id} State: {len(self.positions)} active positions.")
        except Exception as e:
            logging.error(f"Failed to load wallet {self.strategy_id} state: {e}")

    def get_portfolio_value(self, current_prices):
        """
        Returns Total Equity (Cash + All Positions PnL + Locked Margin).
        current_prices: Dict {symbol: price}
        """
        equity = self.balance_eur
        for t_id, pos in self.positions.items():
            symbol = pos['symbol']
            price = current_prices.get(symbol)
            if price:
                pnl = self.calc_pnl_gross(t_id, price)
                equity += (pos['margin'] + pnl)
            else:
                 # If price unknown, assume 0 PnL (Just margin + cash)
                 equity += pos['margin']
        return equity

    def get_capital_usage(self, current_prices=None):
        """Returns (used_margin, total_equity, usage_pct)."""
        total_margin = sum(pos['margin'] for pos in self.positions.values())
        
        if current_prices:
            equity = self.get_portfolio_value(current_prices)
        else:
            # Fallback
            equity = self.balance_eur + total_margin
            
        if equity <= 0: return total_margin, 0.0, 1.0
        
        return total_margin, equity, (total_margin / equity)

    def can_open_new(self, symbol, side, current_prices=None):
        # 1. Global Capital Limit (40%)
        margin, equity, usage = self.get_capital_usage(current_prices)
        
        if self.capital_limit_pct is not None and usage >= self.capital_limit_pct:
             logging.warning(f"Block Open {symbol} ({self.strategy_id}): Cap Usage {usage*100:.1f}% >= {self.capital_limit_pct*100:.0f}%")
             return False, "Capital Limit Reached"
             
        # 2. Hedge Limit: Max 1 Long + 1 Short per Symbol
        # Count existing positions for this symbol/side
        count = 0
        for pos in self.positions.values():
            if pos['symbol'] == symbol and pos['type'] == side:
                count += 1
                
        if count >= 1:
            logging.warning(f"Block Open {symbol} ({self.strategy_id}): Already have {side}")
            return False, f"Already have {side}"
            
        return True, "OK"

    def calculate_entry_size(self, price):
        """
        Sniper Sizing: min(Capital * 10%, 60 EUR)
        Returns (size, margin_cost, leverage)
        """
        # Determine Base Investment
        # We use a theoretical 'Total Capital' for 10% calc, usually initial or current equity.
        # Determine Base Investment: 10% of Total Current Equity
        current_equity = self.balance_eur + sum(p['margin'] for p in self.positions.values())
        
        alloc_10pct = current_equity * config.MAX_ENTRY_PCT
        
        # Base Sizing: Min(10% Equity, 60 EUR)
        entry_cost = min(alloc_10pct, config.MAX_ENTRY_AMT)
        
        # Enforce Minimum (10 EUR)
        if entry_cost < config.MIN_ENTRY_AMT:
             entry_cost = config.MIN_ENTRY_AMT

        # Check Cash Availability
        # If we don't have enough for the Minimum, we DO NOT open.
        if self.balance_eur < entry_cost:
            # logging.warning(f"Insufficient cash for entry. Need {entry_cost}, Have {self.balance_eur}")
            return 0.0, 0.0, 1.0

        # Leverage
        # Long = 1x (Spot), Short = 1x (Futures for Simplicity, user said 1x or 2x, let's use 1x to keep margin simple)
        # Actually user said "Short = Futures... Margen 1x or 2x". Let's use 1x for robustness unless requested.
        leverage = 1.0 
        
        position_value = entry_cost * leverage
        size = position_value / price
        
        return size, entry_cost, leverage

    def open_position(self, symbol, side, price):
        can_open, reason = self.can_open_new(symbol, side)
        if not can_open:
            return None

        size, margin_cost, leverage = self.calculate_entry_size(price)
        if size == 0:
            logging.warning(f"Insufficient funds to open {symbol}")
            return None
        if self.balance_eur < margin_cost:
             logging.warning(f"Open Fail: Insufficient Balance {self.balance_eur:.2f} < {margin_cost:.2f}")
             return False
             
        self.balance_eur -= margin_cost
        
        # Fee Calculation (Entry is Taker)
        fee_rate = config.FEE_SPOT_TAKER if side == 'LONG' else config.FEE_FUTURES_TAKER
        entry_val = size * price
        fee_eur = entry_val * fee_rate
        self.balance_eur -= fee_eur # Pay fee explicitly
        
        pos = {
            'symbol': symbol,
            'type': side,
            'size': size,
            'margin': margin_cost,
            'leverage': leverage,
            'avg_price': price,
            'entry_price': price,
            'itemized_fees': fee_eur, # Track total fees paid
            'entry_time': time.time(),
            'dca_count': 0,
            'last_dca_price': price,
            'highest_price': price, # For Trailing Stop Long
            'lowest_price': price,  # For Trailing Stop Short
            'last_ts_update': time.time() # For Time-Based Advance
        }
        
        t_id = self.next_trade_id
        self.next_trade_id += 1
        self.positions[t_id] = pos
        
        logging.info(f">>> OPEN #{t_id} {symbol} {side} @ {price:.5f} | Size {size:.5f} | Margin {margin_cost:.2f}")
        self.save_state()
        return t_id

    def execute_dca(self, trade_id, price):
        if trade_id not in self.positions: return False
        pos = self.positions[trade_id]
        
        if pos['dca_count'] >= 3:
            logging.warning(f"Max DCA reached for #{trade_id}")
            return False
            
        # DCA Size: Same as Entry (Martingale? User didn't specify. Usually same size or 1.5x)
        # "Solo promediar... Reserva DCA 60%". Implies we use funds.
        # Let's use same size as initial for consistency or re-calc?
        # Standard DCA: usually same value added.
        
        chunk_cost = pos['margin'] / (pos['dca_count'] + 1) # Avg cost of previous chunks?
        # Actually, let's just add the fixed Entry Amount (max 60) again.
        
        # Recalculate generic "Entry Unit"
        current_equity = self.balance_eur + sum(p['margin'] for p in self.positions.values())
        alloc_10pct = current_equity * config.MAX_ENTRY_PCT
        chunk_cost = min(alloc_10pct, config.MAX_ENTRY_AMT)
        
        if self.balance_eur < chunk_cost:
             logging.warning(f"No funds for DCA #{trade_id}")
             return False

        chunk_size = (chunk_cost * pos['leverage']) / price
        
        # Update Average
        old_val = pos['size'] * pos['avg_price']
        new_val = chunk_size * price
        new_total_size = pos['size'] + chunk_size
        new_avg = (old_val + new_val) / new_total_size
        
        pos['size'] = new_total_size
        pos['margin'] += chunk_cost
        pos['avg_price'] = new_avg
        pos['dca_count'] += 1
        pos['last_dca_price'] = price
        
        self.balance_eur -= chunk_cost
        
        # DCA Fee (Maker)
        # Spot DCA = Maker (0%), Futures DCA = Maker (0%)
        # But we must implement logic to use config
        fee_rate = config.FEE_SPOT_MAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_MAKER
        dca_val = chunk_size * price
        fee_eur = dca_val * fee_rate
        self.balance_eur -= fee_eur
        pos['itemized_fees'] = pos.get('itemized_fees', 0.0) + fee_eur
        
        logging.info(f">>> DCA #{pos['dca_count']} {pos['symbol']} (#{trade_id}): New Avg {new_avg:.2f}")
        self.save_state()
        return True

    def close_position(self, trade_id, price):
        if trade_id not in self.positions: return False
        pos = self.positions[trade_id]
        
        # Calculate Gross PnL
        gross_pnl = self.calc_pnl_gross(trade_id, price)
        
        # Calculate Fees (Opening + Closing)
        # Long (Spot): Taker on Entry, Taker on Exit
        # Short (Futures): Taker on Entry, Taker on Exit
        
        # Calculate Exit Fee (Taker)
        if pos['type'] == 'LONG':
             fee_exit_rate = config.FEE_SPOT_TAKER
        else:
             fee_exit_rate = config.FEE_FUTURES_TAKER
             
        exit_val = pos['size'] * price
        fee_exit = exit_val * fee_exit_rate
        self.balance_eur -= fee_exit
        
        # Total Fees = Already Paid (Entry + DCA) + Exit
        # Note: 'itemized_fees' contains all fees PAID so far during open/dca.
        fees_paid_so_far = pos.get('itemized_fees', 0.0)
        total_fees = fees_paid_so_far + fee_exit
        
        # PnL Calculation:
        # Gross PnL is purely price diff.
        # Net PnL = Gross - Total Fees.
        # But wait, we already subtracted fees from balance during open/dca/close.
        # So Balance is correct. We just need to report the PnL stat.
        
        net_pnl = gross_pnl - total_fees
        
        # Return Margin + Gross PnL (Fees were paid separately)
        # Balance = Start - (Margin + FeesPaid)
        # Close: Balance - ExitFee + Margin + GrossPnL
        # Result: Start - FeesPaid - ExitFee + GrossPnL = Start - TotalFees + GrossPnL = Start + NetPnL.
        
        self.balance_eur += pos['margin']
        self.balance_eur += gross_pnl
        
        # Log
        logging.info(f">>> CLOSE #{trade_id} {pos['symbol']}: Gross {gross_pnl:.2f} | Fees {total_fees:.4f} | Net {net_pnl:.2f}")
        
        # Archive
        record = pos.copy()
        record['id'] = trade_id # Ensure ID is preserved
        record['close_price'] = price
        record['close_time'] = time.time()
        record['final_pnl'] = net_pnl
        record['final_fees'] = total_fees
        self.trades_history.append(record)
        
        del self.positions[trade_id]
        self.save_state()
        
        # Notify Telegram
        self.send_telegram_notification(pos, price, net_pnl, total_fees)
        
        return True

    def send_telegram_notification(self, pos, close_price, net_pnl, fees):
        try:
            token = config.TELEGRAM_TOKEN
            chat_id = config.TELEGRAM_CHAT_ID
            
            if not token or not chat_id: return
            
            # Emoji based on result
            icon = "✅" if net_pnl >= 0 else "❌"
            
            msg = (
                f"{icon} <b>TRADE CLOSED: {pos['symbol']}</b>\n"
                f"Type: {pos['type']}\n"
                f"Entry: {pos['avg_price']:.4f}\n"
                f"Exit: {close_price:.4f}\n"
                f"------------------\n"
                f"<b>Net PnL: {net_pnl:+.2f} EUR</b>\n"
                f"Fees: {fees:.2f} EUR\n"
                f"Balance: {self.balance_eur:.2f} EUR"
            )
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
            
            # Send async or simple timeout? 
            # Blocking here might slow down the loop. 
            # But close is rare. 1s timeout is fine.
            requests.post(url, data=data, timeout=3)
            
        except Exception as e:
            logging.error(f"Telegram Alert Failed: {e}")

    def close_all_positions(self, current_prices):
        """Emergency: Close all active positions."""
        ids = list(self.positions.keys())
        logging.warning("!!! PANIC CLOSE ALL TRIGGERED !!!")
        for t_id in ids:
             pos = self.positions[t_id]
             price = current_prices.get(pos['symbol'], 0)
             if price > 0:
                 self.close_position(t_id, price)
             else:
                 logging.warning(f"Could not close #{t_id} {pos['symbol']}: No price data")
        self.save_state()

    def calc_pnl_gross(self, trade_id, current_price):
        if trade_id not in self.positions: return 0.0
        if current_price <= 0: return 0.0
        pos = self.positions[trade_id]
        if pos['type'] == 'LONG':
            return (current_price - pos['avg_price']) * pos['size']
        else:
            return (pos['avg_price'] - current_price) * pos['size']
            
    def calc_pnl_pct_net(self, trade_id, current_price):
        """Returns Net PnL % relative to Margin."""
        # We estimate fees based on CURRENT price exit
        if trade_id not in self.positions: return 0.0
        pos = self.positions[trade_id]
        
        gross_pnl = self.calc_pnl_gross(trade_id, current_price)
        
        entry_val = pos['size'] * pos['avg_price']
        exit_val = pos['size'] * current_price
        
        if pos['type'] == 'LONG':
            fee_est = entry_val * config.FEE_SPOT_TAKER + exit_val * config.FEE_SPOT_TAKER
            # Better: use itemized if available
            fees = pos.get('itemized_fees', entry_val * config.FEE_SPOT_TAKER) + (exit_val * config.FEE_SPOT_TAKER)
        else:
            fees = pos.get('itemized_fees', entry_val * config.FEE_FUTURES_TAKER) + (exit_val * config.FEE_FUTURES_TAKER)
            
        net_pnl = gross_pnl - fees
        return (net_pnl / pos['margin']) * 100.0

    def get_last_entry_info(self, symbol, side):
        last_price = 0.0
        last_time = 0.0
        found = False
        for pos in self.positions.values():
            if pos['symbol'] == symbol and pos['type'] == side:
                 # In hedge mode with max 1, this finds THE position
                 if pos['entry_time'] > last_time:
                     last_time = pos['entry_time']
                     last_price = pos['entry_price']
                     found = True
        return (last_price, last_time) if found else None

    def get_positions_status(self, current_prices={}):
        """Returns list of status strings for dashboard."""
        stats = []
        for t_id, pos in self.positions.items():
            sym = pos['symbol']
            price = current_prices.get(sym)
            
            pnl_pct = 0.0
            pnl_val = 0.0
            
            if price:
                 # Net PnL %
                 pnl_pct = self.calc_pnl_pct_net(t_id, price)
                 # Net PnL Value (EUR) - Approximate
                 gross = self.calc_pnl_gross(t_id, price)
                 # Fees
                 # Fees
                 val_exit = pos['size'] * price
                 if pos['type'] == 'LONG': fee_exit = val_exit * config.FEE_SPOT_TAKER
                 else: fee_exit = val_exit * config.FEE_FUTURES_TAKER
                 
                 fees = pos.get('itemized_fees', 0.0) + fee_exit
                 
                 pnl_val = gross - fees

            stats.append({
                'id': t_id,
                'symbol': sym,
                'type': pos['type'],
                'dca': pos['dca_count'],
                'avg': pos['avg_price'],
                'margin': pos['margin'],
                'pnl_pct': pnl_pct,
                'pnl_val': pnl_val,
                'fees_eur': fees, # Added for GUI
                'ts_status': pos.get('ts_status', 'WAIT'), # Added for GUI sync
                'ts_price': pos.get('ts_price', 0.0), # Added for GUI sync
                'mark_price': price or 0.0
            })
        return stats

    def get_history(self):
        return self.trades_history[::-1]

    def get_balance_summary(self, current_prices):
        """Returns Equity, Real Capital (Base), and Available Balance."""
        total_margin = sum(p['margin'] for p in self.positions.values())
        
        total_unrealized_net = 0.0
        for t_id, pos in self.positions.items():
            price = current_prices.get(pos['symbol'], pos['avg_price'])
            if price <= 0: price = pos['avg_price']
            
            # Gross PnL
            if pos['type'] == 'LONG':
                gross = (price - pos['avg_price']) * pos['size']
                entry_fee = (pos['size'] * pos['avg_price']) * config.FEE_SPOT_TAKER
                exit_fee = (pos['size'] * price) * config.FEE_SPOT_TAKER
            else:
                gross = (pos['avg_price'] - price) * pos['size']
                entry_fee = (pos['size'] * pos['avg_price']) * config.FEE_FUTURES_TAKER
                exit_fee = (pos['size'] * price) * config.FEE_FUTURES_TAKER
            
            # Equity = Real Capital + Gross - Entry Fee - Exit Fee
            # (Entry Fee is "sunk" cost, Exit Fee is "future" cost, both reduce equity)
            total_unrealized_net += (gross - entry_fee - exit_fee)
            
        real_capital = self.balance_eur + total_margin
        equity = real_capital + total_unrealized_net
        
        # APY Calculation
        apy = self.get_annualized_roi()
        
        return {
            "balance": self.balance_eur,
            "margin_used": total_margin,
            "real_capital": real_capital,
            "equity": equity,
            "apy": apy
        }

    def get_annualized_roi(self):
        """Calculates Annualized Profit % (APY) based on Realized PnL."""
        total_pnl = sum([t.get('final_pnl', 0.0) for t in self.trades_history])
        
        # If no PnL, 0%
        if total_pnl == 0: return 0.0
        
        # Duration in Days
        duration_sec = time.time() - self.start_time
        duration_days = duration_sec / 86400.0
        
        if duration_days < 0.001: return 0.0 # Too short
        
        # 1. Base Capital
        # If user says 1000 but config says 500, we should perhaps use the greater of config vs current equity?
        # Or better: Use equity at start? We don't have it tracked.
        # Let's use config.INITIAL_BALANCE but log if it looks weird? 
        # No, just use config.INITIAL_BALANCE as the "Reference Input".
        base_capital = config.INITIAL_BALANCE
        
        # 2. Time Base Fix
        # User REQ: Start calculation strictly from the first operation time
        start_times = []
        
        # History
        if self.trades_history:
             # Assuming sorted? better to just look at all or min
             # History append order: usually oldest first? No, append adds to end.
             # Let's take min to be safe
             for t in self.trades_history:
                 if 'entry_time' in t: start_times.append(t['entry_time'])
                 
        # Active Positions
        for p in self.positions.values():
             if 'entry_time' in p: start_times.append(p['entry_time'])
             
        if start_times:
            effective_start = min(start_times)
        else:
            # If no trades ever, use bot start logic (or just return 0)
            return 0.0

        duration_sec = time.time() - effective_start
        duration_days = duration_sec / 86400.0
        
        # ROI %
        roi_pct = (total_pnl / base_capital) * 100.0
        
        # Annualize: ROI * (365 / days)
        # Avoid huge numbers for very short duration. Min 0.1 days?
        # User saw 333% because of short duration denominator.
        
        if duration_days < 0.001: return 0.0
        
        apy = roi_pct * (365.0 / max(duration_days, 0.1)) 
        return apy
