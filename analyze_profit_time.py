import json
import os
import time
import math

# Define paths
BASE_DIR = "/home/daniel/Bot_agresivo"
pd = None # Mock to avoid name errors if leftover refs exist, though we replace all.

def calculate_stats(values):
    if not values: return 0, 0, 0, 0
    n = len(values)
    mean = sum(values) / n
    sorted_vals = sorted(values)
    median = sorted_vals[n // 2]
    return n, sum(values), mean, median

def load_wallet_states():
    files = [f for f in os.listdir(BASE_DIR) if f.startswith("wallet_state_") and f.endswith(".json") and "L.json" not in f and "S.json" not in f]
    print(f"Found files: {files}")

    all_trades = {}

    for filename in files:
        strategy_id = filename.replace("wallet_state_", "").replace(".json", "")
        filepath = os.path.join(BASE_DIR, filename)
        
        trades = []
        try:
            with open(filepath, "r") as f:
                state = json.load(f)
                history = state.get("history", [])
                
                for trade in history:
                    entry_time = trade.get("entry_time", 0)
                    close_time = trade.get("close_time", 0)
                    final_pnl = trade.get("final_pnl", 0.0)
                    
                    if entry_time > 0 and close_time > 0:
                        duration_sec = close_time - entry_time
                        duration_hours = max(duration_sec / 3600.0, 0.001)
                        
                        profit_per_hour = final_pnl / duration_hours
                        
                        trades.append({
                            "strategy": strategy_id,
                            "pnl": final_pnl,
                            "duration_hours": duration_hours,
                            "profit_per_hour": profit_per_hour
                        })
        except Exception as e:
            print(f"Error reading {filename}: {e}")
        
        if trades:
            all_trades[strategy_id] = trades
            
    return all_trades

def analyze_data(all_trades):
    if not all_trades:
        print("No closed trades found.")
        return

    print("\n--- Summary per Strategy ---")
    print(f"{'Strategy':<15} | {'Count':<5} | {'Sum PnL':<10} | {'Mean PnL':<10} | {'Mean Dur(h)':<12} | {'Mean P/h':<10}")
    print("-" * 80)

    for strat, trades in all_trades.items():
        pnls = [t['pnl'] for t in trades]
        durs = [t['duration_hours'] for t in trades]
        phours = [t['profit_per_hour'] for t in trades]
        
        count, total_pnl, mean_pnl, median_pnl = calculate_stats(pnls)
        _, _, mean_dur, median_dur = calculate_stats(durs)
        _, _, mean_ph, median_ph = calculate_stats(phours)
        
        print(f"{strat:<15} | {count:<5} | {total_pnl:<10.2f} | {mean_pnl:<10.2f} | {mean_dur:<12.2f} | {mean_ph:<10.2f}")

    print("\n\n--- Time vs Profit Efficiency ---")
    
    bins = [
        (0, 1, "0-1h"),
        (1, 4, "1-4h"),
        (4, 12, "4-12h"),
        (12, 24, "12-24h"),
        (24, 48, "24-48h"),
        (48, 168, "2-7d"),
        (168, 9999, "7d+")
    ]

    for strat, trades in all_trades.items():
        print(f"\nAnalysis for: {strat}")
        print(f"{'Bin':<10} | {'Count':<5} | {'Mean PnL':<10} | {'Mean P/h':<10}")
        print("-" * 50)
        
        for min_h, max_h, label in bins:
            bin_trades = [t for t in trades if min_h <= t['duration_hours'] < max_h]
            if not bin_trades:
                continue
                
            pnls = [t['pnl'] for t in bin_trades]
            phours = [t['profit_per_hour'] for t in bin_trades]
            
            _, _, mean_pnl, _ = calculate_stats(pnls)
            _, _, mean_ph, _ = calculate_stats(phours)
            
            print(f"{label:<10} | {len(bin_trades):<5} | {mean_pnl:<10.2f} | {mean_ph:<10.2f}")
            
        # Winners vs Losers
        winners = [t for t in trades if t['pnl'] > 0]
        losers = [t for t in trades if t['pnl'] <= 0]
        
        _, _, w_dur, _ = calculate_stats([t['duration_hours'] for t in winners])
        _, _, l_dur, _ = calculate_stats([t['duration_hours'] for t in losers])
        
        print(f"Avg Duration Winners: {w_dur:.2f}h")
        print(f"Avg Duration Losers: {l_dur:.2f}h")

if __name__ == "__main__":
    data = load_wallet_states()
    analyze_data(data)
