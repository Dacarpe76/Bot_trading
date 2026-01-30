import pandas as pd
import itertools

# Files
RESULTS_FILE = "Short_Analysis_Results.csv"
LOG_FILE = "TRH_Opportunities_Log.csv"

def optimize():
    print("Loading data...")
    try:
        results = pd.read_csv(RESULTS_FILE)
        log = pd.read_csv(LOG_FILE)
    except FileNotFoundError:
        print("Required files not found.")
        return

    # Merge to get PinBar
    # Ensure Timestamps match format
    results['Timestamp'] = pd.to_datetime(results['Timestamp'])
    log['Timestamp'] = pd.to_datetime(log['Timestamp'])
    
    # Merge
    data = pd.merge(results, log[['Timestamp', 'PinBar']], on='Timestamp', how='left')
    
    # Deduplicate timestamps to avoid inflated counts
    data = data.drop_duplicates(subset=['Timestamp'])
    
    # Fill NaN PinBar with False
    data['PinBar'] = data['PinBar'].fillna(False)

    print(f"Loaded {len(data)} unique simulated trades.")

    # Grid Search Parameters
    rsi_levels = [50, 55, 60, 65, 70, 75, 80]
    vrel_levels = [0, 1, 2, 3, 5, 8]
    err_levels = [0, 1, 2, 3, 5]
    pinbar_options = [None, True, False] # None = Don't care

    best_configs = []

    print("Running Grid Search...")
    
    # Using itertools to generate combinations
    for rsi, vrel, err, pinbar in itertools.product(rsi_levels, vrel_levels, err_levels, pinbar_options):
        
        # Apply Filters
        subset = data[
            (data['RSI'] >= rsi) &
            (data['VRel'] >= vrel) &
            (data['ERR'] >= err)
        ]
        
        if pinbar is not None:
            subset = subset[subset['PinBar'] == pinbar]
            
        count = len(subset)
        if count < 20: continue # Ignore small samples
        
        wins = len(subset[subset['Outcome'] == 'TAKE_PROFIT'])
        win_rate = (wins / count) * 100
        
        if win_rate > 50: # Only care about > 50%
            best_configs.append({
                'RSI': rsi,
                'VRel': vrel,
                'ERR': err,
                'PinBar': pinbar,
                'Count': count,
                'Wins': wins,
                'WinRate': win_rate
            })

    # Convert to DF and Sort
    results_df = pd.DataFrame(best_configs)
    
    if results_df.empty:
        print("No configuration found with > 50% Win Rate (min 20 trades).")
        return

    top_results = results_df.sort_values(by='WinRate', ascending=False).head(20)
    
    print("\n--- Top 20 Short Filter Configurations ---")
    print(top_results.to_string(index=False))
    
    # Also find "High Volume" winners (most profit count with > 60% WR)
    solid_results = results_df[results_df['WinRate'] > 60].sort_values(by='Count', ascending=False).head(5)
    print("\n--- Most Robust Configs (>60% WR, Max Trades) ---")
    print(solid_results.to_string(index=False))

if __name__ == "__main__":
    optimize()
