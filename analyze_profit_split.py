import json
import os
import glob

def analyze_profitability():
    wallet_files = glob.glob("wallet_state_*.json")
    
    total_long_realized = 0.0
    total_short_realized = 0.0
    total_long_count = 0
    total_short_count = 0
    
    active_long_count = 0
    active_short_count = 0
    
    print(f"Analyzing {len(wallet_files)} wallet files...")
    
    for wf in wallet_files:
        try:
            with open(wf, 'r') as f:
                data = json.load(f)
                
            # Realized PnL (History)
            history = data.get('history', [])
            for trade in history:
                pnl = trade.get('final_pnl', 0.0)
                side = trade.get('type', 'UNKNOWN')
                
                if side == 'LONG':
                    total_long_realized += pnl
                    total_long_count += 1
                elif side == 'SHORT':
                    total_short_realized += pnl
                    total_short_count += 1
            
            # Active Positions (Count only, PnL requires live price)
            positions = data.get('positions', {})
            for pid, pos in positions.items():
                side = pos.get('type', 'UNKNOWN')
                if side == 'LONG':
                    active_long_count += 1
                elif side == 'SHORT':
                    active_short_count += 1
                    
        except Exception as e:
            print(f"Error reading {wf}: {e}")

    print("\n--- RESULTS: Realized PnL (Closed Trades) ---")
    print(f"LONGs:  {total_long_realized:+.2f} EUR (over {total_long_count} trades)")
    print(f"SHORTs: {total_short_realized:+.2f} EUR (over {total_short_count} trades)")
    
    print("\n--- STATUS: Active Positions ---")
    print(f"Open LONGs:  {active_long_count}")
    print(f"Open SHORTs: {active_short_count}")

    if total_long_count > 0:
        avg_long = total_long_realized / total_long_count
        print(f"\nAvg PnL per LONG:  {avg_long:+.2f} EUR")
    
    if total_short_count > 0:
        avg_short = total_short_realized / total_short_count
        print(f"Avg PnL per SHORT: {avg_short:+.2f} EUR")

if __name__ == "__main__":
    analyze_profitability()
