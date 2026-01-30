import pandas as pd
import glob
from datetime import timedelta

# Configuration
LOG_FILE = "TRH_Opportunities_Log.csv"
RESEARCH_PATTERN = "TRH_Research_*.csv"

# Target Strategy
TARGET_RSI = 75
TARGET_VREL = 3.0

# Simulation Params
TP_PCT = 0.015
SL_PCT = 0.015
TIME_LIMIT_HOURS = 8

def verify():
    # Load Logs
    try:
        ops = pd.read_csv(LOG_FILE)
        ops['Timestamp'] = pd.to_datetime(ops['Timestamp'])
    except:
        print("Log error")
        return
        
    # Filter Candidates
    candidates = ops[
        (ops['RSI'] > TARGET_RSI) &
        (ops['VRel'] > TARGET_VREL)
    ].copy()
    
    print(f"Simulating {len(candidates)} trades with RSI > {TARGET_RSI} and VRel > {TARGET_VREL}...")
    
    if candidates.empty:
        return

    # Load Market Data
    all_files = sorted(glob.glob(RESEARCH_PATTERN))
    dfs = []
    for f in all_files:
        try:
            df = pd.read_csv(f, on_bad_lines='skip', engine='python')
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            dfs.append(df)
        except: pass
        
    if not dfs: return
    market_data = pd.concat(dfs).sort_values('Timestamp').reset_index(drop=True)
    market_data.set_index('Timestamp', inplace=True)
    market_data = market_data[~market_data.index.duplicated(keep='first')]

    # Simulation Loop
    results = []
    total_pnl_pct = 0.0
    
    for idx, row in candidates.iterrows():
        entry_time = row['Timestamp']
        entry_price = row['Price']
        
        end_time = entry_time + timedelta(hours=TIME_LIMIT_HOURS)
        future = market_data[entry_time:end_time]
        
        if future.empty: continue
        
        # Check outcome
        outcome = "TIME_LIMIT" 
        final_pnl = (entry_price - future.iloc[-1]['Close']) / entry_price
        
        for t, candle in future.iterrows():
            # Check SL
            high = candle['High']
            dd = (high - entry_price) / entry_price
            if dd >= SL_PCT:
                outcome = "STOP_LOSS"
                final_pnl = -SL_PCT
                break
                
            # Check TP
            low = candle['Low']
            prof = (entry_price - low) / entry_price
            if prof >= TP_PCT:
                outcome = "TAKE_PROFIT"
                final_pnl = TP_PCT
                break
        
        results.append(final_pnl)
        total_pnl_pct += final_pnl

    # Report
    wins = len([r for r in results if r > 0])
    losses = len([r for r in results if r < 0]) # Strict losses
    total = len(results)
    
    if total == 0:
        print("No valid trades found in market data coverage.")
        return

    win_rate = (wins / total) * 100
    avg_pnl = sum(results) / total * 100

    print("\n--- PERFORMANCE REPORT (RSI > 75, VRel > 3) ---")
    print(f"Total Trades: {total}")
    print(f"Wins: {wins} ({win_rate:.1f}%)")
    print(f"Losses: {losses} ({100-win_rate:.1f}%)")
    print(f"Total Accumulated PnL: {total_pnl_pct*100:.2f}% (uncompounded)")
    print(f"Average PnL per Trade: {avg_pnl:.2f}%")
    print("-----------------------------------------------")

if __name__ == "__main__":
    verify()
