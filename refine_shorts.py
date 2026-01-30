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

def run_tests():
    print("Loading data...")
    ops = pd.read_csv(LOG_FILE)
    ops['Timestamp'] = pd.to_datetime(ops['Timestamp'])
    
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
    
    # Scenarios: ADX Scan
    scenarios = []
    for adx_val in range(20, 65, 5):
        scenarios.append({
            "name": f"RSI > 75 + ADX > {adx_val}",
            "filter": lambda r, val=adx_val: r['RSI'] > 75 and r['ADX'] > val
            # Note: lambda needs default arg to capture value in loop
        })
    
    for sc in scenarios:
        print(f"\nRunning Scenario: {sc['name']}")
        candidates = ops[ops.apply(sc['filter'], axis=1)]
        
        if candidates.empty:
            print("No candidates found.")
            continue
            
        wins = 0
        losses = 0
        
        for idx, row in candidates.iterrows():
            entry_time = row['Timestamp']
            entry_price = row['Price']
            end_time = entry_time + timedelta(hours=TIME_LIMIT)
            
            # Use boolean mask to avoid KeyError on exact timestamp lookup
            future = market[(market.index >= entry_time) & (market.index <= end_time)]
            if future.empty: continue
            
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
            
        total = wins + losses
        if total == 0:
            print("No completed trades.")
        else:
            wr = (wins/total)*100
            print(f"Trades: {total} | Wins: {wins} | Losses: {losses} | Win Rate: {wr:.1f}%")

if __name__ == "__main__":
    run_tests()
