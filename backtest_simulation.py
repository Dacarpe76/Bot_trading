import pandas as pd
import glob
import ta

# CONFIG
FEE_TAKER = 0.0006 
FEE_MAKER = 0.0002 
SLIPPAGE = 0.0001 

class BacktestStrategy:
    def __init__(self, name):
        self.name = name
        self.active_trade = None 
        self.trades = []
        
    def check_entry(self, row): pass
    def check_exit(self, row): pass
        
    def open_trade(self, row, side):
        self.active_trade = {
            'entry_time': row['Timestamp'],
            'entry_price': row['Close'],
            'side': side,
            'highest_price': row['Close'],
            'lowest_price': row['Close'],
            'symbol': row['Symbol'],
            'ts_price': None # For Cent/ERIT specific
        }

    def close_trade(self, row, reason, override_price=None):
        t = self.active_trade
        exit_price = override_price if override_price else row['Close']
        
        # Apply Slippage on Stop Hits
        if override_price:
             if t['side'] == 'LONG': exit_price *= (1 - SLIPPAGE)
             else: exit_price *= (1 + SLIPPAGE)
        
        if t['side'] == 'LONG':
            gross = (exit_price - t['entry_price']) / t['entry_price']
        else:
            gross = (t['entry_price'] - exit_price) / t['entry_price']
            
        net = gross - (FEE_TAKER * 2)
        
        self.trades.append({
            'Strategy': self.name,
            'Symbol': t['symbol'],
            'Entry_Time': t['entry_time'],
            'Exit_Time': row['Timestamp'],
            'Entry_Price': t['entry_price'],
            'Exit_Price': exit_price,
            'Reason': reason,
            'Net_PnL_Pct': net * 100
        })
        self.active_trade = None

# --- STRATEGIES ---

class StratS1_Sniper(BacktestStrategy):
    def check_entry(self, row):
        if self.active_trade: return
        # Strict Wick: VRel > 4, ERR > 3.5, Wick > 70%
        if row['VRel'] > 4.0 and row['ERR'] > 3.5 and row['Wick_Pct'] > 0.70:
             # Direction based on RSI
             if row['RSI'] < 40: self.open_trade(row, 'LONG')
             elif row['RSI'] > 60: self.open_trade(row, 'SHORT')

    def check_exit(self, row):
         if not self.active_trade: return
         t = self.active_trade
         atr = row.get('ATR_14', row['Close']*0.01)
         
         if t['side'] == 'LONG':
             t['highest_price'] = max(t['highest_price'], row['High'])
             ts = t['highest_price'] - (3.0 * atr)
             if row['Low'] < ts: self.close_trade(row, "TS_Hit", override_price=ts)
         else:
             t['lowest_price'] = min(t['lowest_price'], row['Low'])
             ts = t['lowest_price'] + (3.0 * atr)
             if row['High'] > ts: self.close_trade(row, "TS_Hit", override_price=ts)

class StratS5_Pullback(BacktestStrategy):
    def check_entry(self, row):
        if self.active_trade: return
        is_bullish = "Bullish" in str(row['Current_Trend_1h']) or "Up" in str(row['Current_Trend_1h'])
        ema_ok = 0 <= row['Dist_EMA200_Pct'] <= 0.005
        if is_bullish and ema_ok and row['VRel'] > 1.5 and row['ADX_14'] > 25:
             self.open_trade(row, 'LONG')

    def check_exit(self, row):
        if not self.active_trade: return
        # Standard Exits use Close
        if row['ADX_14'] > 60: self.close_trade(row, "ADX_Climax"); return
        elif row['Stoch_K'] > 95 and row['MFI_14'] > 85: self.close_trade(row, "Osc_Sat"); return
        elif row['Dist_EMA200_Pct'] > 0.05: self.close_trade(row, "Over_Extended"); return
        
        atr = row.get('ATR_14', row['Close']*0.01)
        ts = self.active_trade['highest_price'] - (3.0 * atr)
        self.active_trade['highest_price'] = max(self.active_trade['highest_price'], row['High'])
        if row['Low'] < ts: self.close_trade(row, "Safety_TS", override_price=ts)

class StratS2_Cent(BacktestStrategy):
    """Cent Scalper (Simulated)"""
    def check_entry(self, row):
        if self.active_trade: return
        # Same entry as S1
        if row['VRel'] > 4.0 and row['ERR'] > 3.5 and row['Wick_Pct'] > 0.70:
             if row['RSI'] < 40: self.open_trade(row, 'LONG')
             elif row['RSI'] > 60: self.open_trade(row, 'SHORT')

    def check_exit(self, row):
        if not self.active_trade: return
        t = self.active_trade
        # Cent Logic Approximation:
        # Activation at ~0.1% Profit. Step Trail every 0.05%.
        # Assumed Entry Amount ~60 EUR. 0.04 EUR profit ~= 0.06%.
        
        activation_pct = 0.0008 # 0.08%
        
        current_price = row['Close']
        
        if t['side'] == 'LONG':
            pnl_pct = (current_price - t['entry_price']) / t['entry_price']
            
            # Update TS
            if pnl_pct >= activation_pct:
                if t['ts_price'] is None:
                    # Init TS at break-even + small profit
                    t['ts_price'] = t['entry_price'] * (1 + 0.0004)
            
            # Dynamic Step update
            if t['ts_price'] is not None:
                # For simulation, let's use a Tight Trailing Stop of 0.05% once activated.
                ts_tight = t['highest_price'] * (1 - 0.0005)
                if t['ts_price'] < ts_tight: t['ts_price'] = ts_tight

            t['highest_price'] = max(t['highest_price'], row['High'])
            
            # Check Hit
            if t['ts_price'] and row['Low'] < t['ts_price']:
                self.close_trade(row, "Cent_TS_Hit", override_price=t['ts_price']); return
                
            # Stop Loss (Safety) - Not explicitly in Cent S2 logic but implicit via DCA or liquidation. 
            # Implied large stop. Let's set 5% safety.
            if row['Low'] < t['entry_price'] * 0.95: self.close_trade(row, "Safety_SL", override_price=t['entry_price']*0.95); return

        else: # SHORT
            pnl_pct = (t['entry_price'] - current_price) / t['entry_price']
            if pnl_pct >= activation_pct:
                if t['ts_price'] is None:
                    t['ts_price'] = t['entry_price'] * (1 - 0.0004)
            
            if t['ts_price'] is not None:
                 ts_tight = t['lowest_price'] * (1 + 0.0005)
                 if t['ts_price'] > ts_tight: t['ts_price'] = ts_tight

            t['lowest_price'] = min(t['lowest_price'], row['Low'])
            
            if t['ts_price'] and row['High'] > t['ts_price']:
                self.close_trade(row, "Cent_TS_Hit", override_price=t['ts_price']); return
            
            if row['High'] > t['entry_price'] * 1.05: self.close_trade(row, "Safety_SL", override_price=t['entry_price']*1.05); return

class StratS3_Aggressive(BacktestStrategy):
    def check_entry(self, row):
        if self.active_trade: return
        # VRel > 3, ERR > 2.5 OR Climax
        base = (row['VRel'] > 3.0) and (row['ERR'] > 2.5)
        climax_L = (row['VRel'] > 10.0) and (row['RSI'] < 15.0)
        climax_S = (row['VRel'] > 10.0) and (row['RSI'] > 85.0)
        
        if climax_L: self.open_trade(row, 'LONG'); return
        if climax_S: self.open_trade(row, 'SHORT'); return
        
        if base:
             # Direction via RSI
             if row['RSI'] < 40: self.open_trade(row, 'LONG')
             elif row['RSI'] > 60: self.open_trade(row, 'SHORT')

    def check_exit(self, row):
        if not self.active_trade: return
        t = self.active_trade
        atr = row.get('ATR_14', row['Close']*0.01)
        if t['side'] == 'LONG':
            t['highest_price'] = max(t['highest_price'], row['High'])
            ts = t['highest_price'] - (3.0 * atr)
            if row['Low'] < ts: self.close_trade(row, "TS_Hit", override_price=ts)
        else:
            t['lowest_price'] = min(t['lowest_price'], row['Low'])
            ts = t['lowest_price'] + (3.0 * atr)
            if row['High'] > ts: self.close_trade(row, "TS_Hit", override_price=ts)

class StratS4_AggrCent(StratS2_Cent):
    """S2 Exit Logic (Cent), S3 Entry Logic (Aggressive)"""
    def check_entry(self, row):
        if self.active_trade: return
        # Aggressive Inputs
        base = (row['VRel'] > 3.0) and (row['ERR'] > 2.5)
        climax_L = (row['VRel'] > 10.0) and (row['RSI'] < 15.0)
        climax_S = (row['VRel'] > 10.0) and (row['RSI'] > 85.0)
        
        if climax_L: self.open_trade(row, 'LONG'); return
        if climax_S: self.open_trade(row, 'SHORT'); return
        
        if base:
             if row['RSI'] < 40: self.open_trade(row, 'LONG')
             elif row['RSI'] > 60: self.open_trade(row, 'SHORT')

class StratS6_ERIT(BacktestStrategy):
    def check_entry(self, row):
        if self.active_trade: return
        # PinBar + Confluence
        # Assume 'PinBar' col or calc on fly
        # Approximation: Wick > 60% + VRel > 1.5 + ADX > 25
        # PinBar col exists in CSV usually
        is_pin = "True" in str(row.get('PinBar', '')) or row['Wick_Pct'] > 0.60
        if is_pin and row['VRel'] > 1.5 and row['ADX_14'] > 25:
             # Direction? Bull Pin -> Long, Bear Pin -> Short
             # From Wick Analysis
             body = abs(row['Open'] - row['Close'])
             upper = row['High'] - max(row['Open'], row['Close'])
             lower = min(row['Open'], row['Close']) - row['Low']
             
             if lower > upper: self.open_trade(row, 'LONG')
             else: self.open_trade(row, 'SHORT')

    def check_exit(self, row):
         # ERIT: TSL 1.5% or Climax
         if not self.active_trade: return
         t = self.active_trade
         
         if t['side'] == 'LONG':
             t['highest_price'] = max(t['highest_price'], row['High'])
             ts = t['highest_price'] * (1 - 0.015)
             if row['Low'] < ts: self.close_trade(row, "TSL_1.5%", override_price=ts); return
             
             # Climax
             if row['Stoch_K'] > 95 and row['ADX_14'] > 30: # Simplified Climax
                  self.close_trade(row, "Climax_Exit"); return
                  
         else:
             t['lowest_price'] = min(t['lowest_price'], row['Low'])
             ts = t['lowest_price'] * (1 + 0.015)
             if row['High'] > ts: self.close_trade(row, "TSL_1.5%", override_price=ts); return
             
             if row['Stoch_K'] < 5 and row['ADX_14'] > 30:
                  self.close_trade(row, "Climax_Exit"); return


def run_backtest():
    files = glob.glob("TRH_Research_*.csv")
    if not files: return
    
    df_list = []
    for f in files:
        try:
             df = pd.read_csv(f)
             if 'Timestamp' in df.columns:
                 df['Timestamp'] = pd.to_datetime(df['Timestamp'])
             df_list.append(df)
        except: pass
        
    df = pd.concat(df_list, ignore_index=True).sort_values('Timestamp')
    
    # Calc RSI if missing
    if 'RSI' not in df.columns:
         df['RSI'] = 50.0 # Placeholder, should be pre-calced if possible or allow logic to work
         # (Assuming previous fix applied RSI calc, but let's be robust)
    
    # Ensure numeric
    cols = ['VRel','ERR','RSI','ADX_14','Dist_EMA200_Pct','Close','High','Low','Open', 'ATR_14','Stoch_K','MFI_14', 'Upper_Wick_Size', 'Lower_Wick_Size']
    for c in cols:
         if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')

    # Wick Pct
    df['Total_Len'] = df['High'] - df['Low']
    df['Max_Wick'] = df[['Upper_Wick_Size', 'Lower_Wick_Size']].max(axis=1) 
    df['Wick_Pct'] = df['Max_Wick'] / df['Total_Len'].replace(0, 1)

    # Collect all trades
    all_trades = []
    
    print("Simulating Strategies...")
    for sym in df['Symbol'].unique():
        sub_df = df[df['Symbol'] == sym].sort_values('Timestamp')
        
        # Calc RSI per symbol if needed
        if 'RSI' not in sub_df.columns or sub_df['RSI'].iloc[0] == 50.0:
             sub_df['RSI'] = ta.momentum.RSIIndicator(sub_df['Close'], window=14).rsi().fillna(50)
             
        # INSTANTIATE STRATEGIES PER SYMBOL TO AVOID STATE LEAK
        strats = [
            StratS1_Sniper("S1_Sniper"),
            StratS2_Cent("S2_Cent"),
            StratS3_Aggressive("S3_Aggressive"),
            StratS4_AggrCent("S4_AggrCent"),
            StratS5_Pullback("S5_Pullback"),
            StratS6_ERIT("S6_ERIT")
        ]
        
        for idx, row in sub_df.iterrows():
            for s in strats:
                s.check_exit(row)
                s.check_entry(row)
                
        # Collect trades for this symbol
        for s in strats:
            all_trades.extend(s.trades)
                
    # Report
    print("\n=== RESULTADOS SIMULACIÓN COMPLETA ===")
    
    # helper dict to aggregate results by name
    results = {}
    
    for t in all_trades:
        name = t['Strategy']
        if name not in results: results[name] = {'wins':0, 'count':0, 'pnl':0.0}
        results[name]['count'] += 1
        results[name]['pnl'] += t['Net_PnL_Pct']
        if t['Net_PnL_Pct'] > 0: results[name]['wins'] += 1
        
    for name, res in results.items():
        count = res['count']
        wins = res['wins']
        pnl = res['pnl']
        win_rate = (wins/count*100) if count > 0 else 0
        print(f"\n>> {name}")
        print(f"   Ops: {count} | Wins: {wins} ({win_rate:.1f}%) | PnL Total: {pnl:.2f}%")
        
    pd.DataFrame(all_trades).to_csv("backtest_full_results.csv", index=False)

if __name__ == "__main__":
    run_backtest()
