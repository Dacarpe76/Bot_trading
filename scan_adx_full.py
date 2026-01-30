import pandas as pd
import glob
from datetime import timedelta

# Logs
LOG_FILE = "TRH_Opportunities_Log.csv"
RESEARCH_PATTERN = "TRH_Research_*.csv"

# Params
SL = 0.015
TP = 0.015
TIME_LIMIT = 8
RSI_MIN = 75

def scan_adx():
    print("Loading data...")
    try:
        ops = pd.read_csv(LOG_FILE)
        ops['Timestamp'] = pd.to_datetime(ops['Timestamp'])
    except:
        print("Error loading log.")
        return
    
    # Load Market Data
    dfs = []
    for f in sorted(glob.glob(RESEARCH_PATTERN)):
        try: dfs.append(pd.read_csv(f, on_bad_lines='skip', engine='python'))
        except: pass
    if not dfs: return
    market = pd.concat(dfs)
    market['Timestamp'] = pd.to_datetime(market['Timestamp'])
    market.set_index('Timestamp', inplace=True)
    market = market[~market.index.duplicated(keep='first')]
    
    results = []
    
    print("Scanning ADX 1 to 100...")
    
    # Pre-filter for RSI to speed up
    base_candidates = ops[ops['RSI'] > RSI_MIN].copy()
    
    for adx_threshold in range(1, 101):
        # Filter candidates for this ADX level
        # Note: 'ADX' column in log? Check verify_shorts or previous scripts.
        # Log has 'ADX'.
        
        candidates = base_candidates[base_candidates['ADX'] > adx_threshold]
        
        trades = 0
        wins = 0
        losses = 0
        
        for idx, row in candidates.iterrows():
            entry_time = row['Timestamp']
            entry_price = row['Price']
            end_time = entry_time + timedelta(hours=TIME_LIMIT)
            
            # Fast boolean lookup
            future = market[(market.index >= entry_time) & (market.index <= end_time)]
            if future.empty: continue
            
            trades += 1
            outcome = "TIME"
            
            for t, candle in future.iterrows():
                # Check SL
                if (candle['High'] - entry_price)/entry_price >= SL:
                    outcome = "LOSS"
                    break
                # Check TP
                if (entry_price - candle['Low'])/entry_price >= TP:
                    outcome = "WIN"
                    break
            
            if outcome == "WIN": wins += 1
            elif outcome == "LOSS": losses += 1
            
        win_rate = (wins/trades)*100 if trades > 0 else 0.0
        
        results.append({
            "ADX_Threshold": adx_threshold,
            "Trades": trades,
            "Wins": wins,
            "Losses": losses,
            "Win_Rate": win_rate
        })
        
        if adx_threshold % 10 == 0:
            print(f"Done ADX > {adx_threshold} ...")

    # Output to CSV
    df = pd.DataFrame(results)
    df.to_csv("adx_scan_1_100.csv", index=False)
    print("Scan Complete. Saved to adx_scan_1_100.csv")

if __name__ == "__main__":
    scan_adx()
