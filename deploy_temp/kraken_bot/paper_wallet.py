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
        
        self.initial_capital = initial_balance # Store immutable start capital
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
                'initial_capital': self.initial_capital, # Save this
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
                self.initial_capital = state.get('initial_capital', self.initial_capital) # Load or keep default
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
            
    # ... [Skipping unchanged methods] ...

    def get_annualized_roi(self):
        """Calculates Annualized Profit % (APY) based on Realized PnL using Compound Interest."""
        total_pnl = sum([t.get('final_pnl', 0.0) for t in self.trades_history])
        
        # If no PnL, 0% (unless negative?)
        if total_pnl == 0: return 0.0
        if self.initial_capital <= 0: return 0.0
        
        # Duration based on Wallet Inception (Start Time)
        # This is more stable than "First Trade Time"
        effective_start = self.start_time
        
        # If we have history older than start_time (e.g. state file issues), adjust
        if self.trades_history:
             first_trade = min([t['entry_time'] for t in self.trades_history])
             if first_trade < effective_start:
                 effective_start = first_trade

        duration_sec = time.time() - effective_start
        duration_days = duration_sec / 86400.0
        
        # Allow calculation for short periods, but handle extreme short duration
        if duration_days < 0.001: return 0.0 
        
        # Compound Interest Formula
        # (End / Start) ^ (365 / days) - 1
        
        current_equity = self.initial_capital + total_pnl
        growth_factor = current_equity / self.initial_capital
        
        if growth_factor <= 0: return -100.0 # Bust
        
        try:
            # Cap the exponent to avoid overflow on very fresh wallets with a lucky win
            exponent = 365.0 / duration_days
            if exponent > 10000: exponent = 10000
            
            annual_growth_factor = growth_factor ** exponent
            apy = (annual_growth_factor - 1.0) * 100.0
            
            # Sanity Cap for display (e.g. > 10,000% is meaningless noise)
            if apy > 1000000.0: apy = 1000000.0
            if apy < -100.0: apy = -100.0
            
        except:
            apy = 0.0
            
        return apy

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

    def open_position(self, symbol, side, price, quantity=0.0):
        can_open, reason = self.can_open_new(symbol, side)
        if not can_open:
            return None

        if quantity > 0:
            size = quantity
            margin_cost = size * price # 1x Leverage assumed for manual sizing
            leverage = 1.0
        else:
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

    def add_to_position(self, trade_id, price, quantity=0.0):
        if trade_id not in self.positions: return False
        pos = self.positions[trade_id]
        
        # Calculate Cost for this Add
        if quantity > 0:
             size = quantity
             margin_cost = size * price # 1x Leverage assumed
        else:
             # Default behavior (Double Down? or Fixed Amount?)
             # Let's say fixed 50 EUR for legacy
             margin_cost = 50.0
             size = margin_cost / price
        
        if self.balance_eur < margin_cost:
             logging.warning(f"No funds for DCA #{trade_id} (Need {margin_cost:.2f})")
             return False

        self.balance_eur -= margin_cost
        
        # Fee
        fee_rate = config.FEE_SPOT_TAKER if pos['type'] == 'LONG' else config.FEE_FUTURES_TAKER
        fee_eur = (size * price) * fee_rate
        self.balance_eur -= fee_eur
        pos['itemized_fees'] += fee_eur
        
        # Update Average
        old_val = pos['size'] * pos['avg_price']
        new_val = size * price
        new_total_size = pos['size'] + size
        new_avg = (old_val + new_val) / new_total_size
        
        pos['size'] = new_total_size
        pos['margin'] += margin_cost
        pos['avg_price'] = new_avg
        pos['dca_count'] = pos.get('dca_count', 0) + 1
        pos['last_dca_price'] = price
        
        logging.info(f">>> DCA #{trade_id} {pos['symbol']} | Added {size:.5f} @ {price:.5f} | New Avg: {new_avg:.5f}")
        self.save_state()
        return True

    def execute_dca(self, trade_id, price):
        """Legacy alias for add_to_position."""
        return self.add_to_position(trade_id, price, quantity=0.0)
        
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

    def close_partial(self, trade_id, price, ratio):
        """
        Closes a portion of the position defined by ratio (0.0 to 1.0).
        e.g. ratio=0.5 closes 50% of the CURRENT size.
        """
        if trade_id not in self.positions: return False
        if not (0.0 < ratio < 1.0): return False
        
        pos = self.positions[trade_id]
        
        # Calculate Amounts
        close_size = pos['size'] * ratio
        remain_size = pos['size'] - close_size
        
        # Proportional Margin Release
        # margin is the cash locked. 
        close_margin = pos['margin'] * ratio
        remain_margin = pos['margin'] - close_margin
        
        # Calculate PnL on Closed Portion
        # Gross PnL
        if pos['type'] == 'LONG':
            gross_pnl = (price - pos['avg_price']) * close_size
            fee_rate = config.FEE_SPOT_TAKER
        else:
            gross_pnl = (pos['avg_price'] - price) * close_size
            fee_rate = config.FEE_FUTURES_TAKER
            
        # Exit Fee on Closed Portion
        exit_val = close_size * price
        fee_exit = exit_val * fee_rate
        self.balance_eur -= fee_exit
        
        # Entry Fee was already paid full. 
        # But for Net PnL calculation of this chunk, we should attribute a portion of the entry fee?
        # itemized_fees tracks TOTAL fees paid for the WHOLE position.
        # We shouldn't "refund" fees.
        # For reporting a "Partial Trade Record", we can estimate the entry fee portion.
        total_fees_paid_so_far = pos.get('itemized_fees', 0.0)
        # We don't change itemized_fees in the active pos? 
        # Actually we should reduce it proportionally so the remaining pos track its own remaining fees.
        closed_itemized_fees = total_fees_paid_so_far * ratio
        pos['itemized_fees'] -= closed_itemized_fees # Remove from active
        
        total_fees_for_part = closed_itemized_fees + fee_exit
        net_pnl = gross_pnl - total_fees_for_part
        
        # Update Balance
        # Return Margin + Gross PnL (Fees handled separately via deduction)
        # Balance += MarginReleased + GrossPnL
        self.balance_eur += close_margin
        self.balance_eur += gross_pnl
        
        # Update Position State
        pos['size'] = remain_size
        pos['margin'] = remain_margin
        
        # Log Partial
        logging.info(f">>> PARTIAL CLOSE #{trade_id} {pos['symbol']}: {ratio*100:.0f}% @ {price:.4f} | Net {net_pnl:.2f}")
        
        # Archive Partial Record
        record = pos.copy()
        record['id'] = f"{trade_id}_P{int(time.time())}" # Unique ID for partial
        record['close_price'] = price
        record['close_time'] = time.time()
        record['final_pnl'] = net_pnl
        record['final_fees'] = total_fees_for_part
        record['is_partial'] = True
        record['size'] = close_size # Record only the closed size
        self.trades_history.append(record)
        
        self.save_state()
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

    def update_max_stats(self, trade_id, price):
        """Updates highest/lowest price and Max PnL %."""
        if trade_id not in self.positions: return
        pos = self.positions[trade_id]
        
        # Update Price Extremes
        pos['highest_price'] = max(pos.get('highest_price', price), price)
        pos['lowest_price'] = min(pos.get('lowest_price', price), price)
        
        # Calculate Current Net PnL %
        # Simplified: Use Gross for "Max Profit Reach" or Net?
        # Usually users want to know "Did it reach +1%?". Net is safer.
        current_pnl_pct = self.calc_pnl_pct_net(trade_id, price)
        
        # Init max_pnl_pct if missing
        if 'max_pnl_pct' not in pos:
             pos['max_pnl_pct'] = current_pnl_pct
        else:
             pos['max_pnl_pct'] = max(pos['max_pnl_pct'], current_pnl_pct)

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
            max_pnl = pos.get('max_pnl_pct', 0.0) # Retrieve Max
            
            if price:
                 # Net PnL %
                 pnl_pct = self.calc_pnl_pct_net(t_id, price)
                 # Update Max PnL in case it wasn't updated by tick (e.g. GUI refresh only)
                 # But ideally strategy updates it.
                 if pnl_pct > max_pnl: max_pnl = pnl_pct
                 
                 # Net PnL Value (EUR) - Approximate
                 gross = self.calc_pnl_gross(t_id, price)
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
                'max_pnl_pct': max_pnl, # Add to stats
                'pnl_val': pnl_val,
                'fees_eur': fees, 
                'ts_status': pos.get('ts_status', 'WAIT'),
                'ts_price': pos.get('ts_price', 0.0),
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


