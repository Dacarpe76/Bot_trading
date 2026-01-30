import json
import time
import datetime

# Configuration
INITIAL_CAPITAL = 500.0  # Assumed from context
FILES = {
    "Aggressive": "wallet_state_Aggressive.json",
    "AggrCent": "wallet_state_AggrCent.json"
}

def analyze_strategy(name, filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[{name}] File not found.")
        return

    history = data.get('history', [])
    start_time = data.get('start_time', time.time())
    
    # Filter valid history (ignore empty or invalid timestamps)
    if not history:
        print(f"[{name}] No closed trades.")
        return

    # Calculate Total Realized PnL
    total_pnl = sum(t.get('final_pnl', 0.0) for t in history)
    total_fees = sum(t.get('final_fees', 0.0) for t in history)
    wins = len([t for t in history if t.get('final_pnl', 0) > 0])
    losses = len(history) - wins
    
    # Duration
    # Use first trade entry time if earlier than recorded start_time (logic from paper_wallet)
    first_entry = min(t.get('entry_time', start_time) for t in history)
    effective_start = min(start_time, first_entry)
    
    # End Time (Last close)
    last_close = max(t.get('close_time', time.time()) for t in history)
    
    # Duration in Days (Trade Span)
    # If duration is too short (< 1 day), we clamp to avoid infinite projection? 
    # Or keep it real? User wants projection.
    # Let's use 'Now' as end time to be conservative about "idle time" too?
    # Actually, using 'Now' is better for "Run Rate".
    duration_sec = time.time() - effective_start
    days = duration_sec / 86400.0
    
    if days < 0.01: days = 0.01

    # Calculation
    current_capital = INITIAL_CAPITAL + total_pnl
    growth_ratio = current_capital / INITIAL_CAPITAL
    
    # Daily Compound Rate
    # (End / Start) ^ (1 / days)
    if growth_ratio <= 0:
        daily_rate = 0
        projected_1y = 0
    else:
        daily_rate = growth_ratio ** (1 / days)
        # Projected 1 Year Balance
        projected_1y_balance = INITIAL_CAPITAL * (daily_rate ** 365)
        projected_1y_pnl = projected_1y_balance - INITIAL_CAPITAL
        
        # Simple Linear Projection for comparison (bot's "ROI")
        # ROI_Daily = (PnL / Start) / days
        # ROI_Yearly = ROI_Daily * 365
        simple_roi_yr_pct = ((total_pnl / INITIAL_CAPITAL) / days * 365) * 100

    print(f"--- {name} ---")
    print(f"Duration: {days:.2f} days")
    print(f"Trades: {len(history)} (W:{wins} L:{losses})")
    print(f"Realized PnL: {total_pnl:.2f} EUR")
    print(f"Current Cap (Realized): {current_capital:.2f} EUR")
    print(f"Daily Growth: {(daily_rate - 1)*100:.2f}%")
    print(f"Projected PnL (1 Yr Compound): {projected_1y_pnl:,.2f} EUR")
    print(f"Projected Balance (1 Yr): {projected_1y_balance:,.2f} EUR")
    print(f"Simple APY (Ref): {simple_roi_yr_pct:.1f}%")
    print("")

print(f"Current Time: {datetime.datetime.now()}")
for name, path in FILES.items():
    analyze_strategy(name, path)
