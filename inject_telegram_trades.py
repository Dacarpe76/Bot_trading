import re
import datetime
import csv
import json

def parse_telegram_trades(text):
    trades = []
    # Pattern to match each trade block
    # Example:
    # Bot_inversor, [26/2/26 0:11]
    # [WEB] ✅ TRADE CLOSED (Kraken Sentinel 2026): DOT/EUR
    # Type: LONG
    # Entry: 1.4197
    # Exit: 1.4278
    # ------------------
    # Net PnL: +0.08 EUR
    # Fees: 0.02 EUR
    # Balance: 420.79 EUR

    blocks = text.split("Bot_inversor, [")
    for block in blocks:
        if not block.strip():
            continue
        try:
            # Parse Date/Time
            date_time_str = block.split("]")[0]
            # 26/2/26 0:11 -> 2026-02-26 00:11:00
            dt = datetime.datetime.strptime(date_time_str, "%d/%m/%y %H:%M")
            timestamp = int(dt.timestamp())

            # Determine WIN / LOSS
            is_win = "✅" in block
            
            # Extract Strategy and Symbol
            strat_match = re.search(r"TRADE CLOSED \((.*?)\): (.*?)\n", block)
            if not strat_match:
                continue
            strategy_name = strat_match.group(1).strip()
            symbol = strat_match.group(2).strip()

            # Extract Side
            side_match = re.search(r"Type: (LONG|SHORT)", block)
            side = side_match.group(1) if side_match else "UNKNOWN"

            # Extract Entry
            entry_match = re.search(r"Entry: ([\d\.]+)", block)
            entry = float(entry_match.group(1)) if entry_match else 0.0

            # Extract Exit
            exit_match = re.search(r"Exit: ([\d\.]+)", block)
            exit_price = float(exit_match.group(1)) if exit_match else 0.0

            # Extract PnL
            pnl_match = re.search(r"Net PnL: ([\+\-]?[\d\.]+) EUR", block)
            pnl = float(pnl_match.group(1)) if pnl_match else 0.0

            # Map strategy names to internal IDs based on history
            internal_ids = {
                "Kraken Sentinel 2026": "Sentinel2026",
                "Aggressive Sniper": "Aggressive",
                "NetScalp_Rolling": "NetScalp_Rolling",
                "Rolling DCA Inmortal": "RollingDCA_Inmortal",
                "Antigravity Sniper": "Antigravity",
                "Rolling DCA v2": "RollingDCA_v2",
                "Rolling DCA": "RollingDCA",
                "Saint-Grial PRO X3": "SaintGrialProX3",
                "NetScalp DCA": "NetScalp",
                "Hybrid Elite": "HybridElite",
                "Kraken Sentinel Turbo": "SentinelTurbo"
            }
            strat_id = internal_ids.get(strategy_name, strategy_name)

            trade = {
                "strategy_id": strat_id,
                "strategy_display_name": strategy_name,
                "timestamp": timestamp,
                "datetime": dt.strftime('%Y-%m-%d %H:%M:%S'),
                "symbol": symbol,
                "type": side,
                "entry_price": entry,
                "exit_price": exit_price,
                "final_pnl": pnl,
                "pnl_percentage": ((exit_price - entry) / entry * 100) if side == 'LONG' else ((entry - exit_price) / entry * 100)
            }
            trades.append(trade)
        except Exception as e:
            print(f"Error parsing block: {e}")

    return trades

if __name__ == "__main__":
    with open("telegram_trades.txt", "r") as f:
        text = f.read()

    parsed = parse_telegram_trades(text)
    print(f"Parsed {len(parsed)} trades.")
    
    # 1. Update Paper Wallets
    for trade in parsed:
        wallet_file = f"backup_datos/wallet_state_{trade['strategy_id']}.json"
        try:
            with open(wallet_file, "r") as f:
                data = json.load(f)
            
            # Create the history object
            # Note: We don't have exact entry_time, we'll approximate entry_time = close_time - 3600 (1 hour for now)
            history_item = {
                "id": f"manual_{trade['timestamp']}",
                "symbol": trade['symbol'],
                "type": trade['type'],
                "entry_time": trade['timestamp'] - 3600,
                "close_time": trade['timestamp'],
                "entry_price": trade['entry_price'],
                "exit_price": trade['exit_price'],
                "final_pnl": trade['final_pnl'],
                "pnl_pct": trade['pnl_percentage']
            }
            
            # Check if this exact timestamp already exists to prevent duplicate injection
            exists = False
            for t in data.get('trades_history', []):
                if t.get('close_time') == trade['timestamp'] and t.get('symbol') == trade['symbol']:
                    exists = True
                    break
                    
            if not exists:
                if 'trades_history' not in data:
                    data['trades_history'] = []
                data['trades_history'].append(history_item)
                
                with open(wallet_file, "w") as f:
                    json.dump(data, f, indent=4)
                print(f"Added trade {trade['symbol']} to {trade['strategy_id']}")
            else:
                print(f"Trade already exists in {trade['strategy_id']}")

        except FileNotFoundError:
            # Fallback for root path
            wallet_file_root = f"wallet_state_{trade['strategy_id']}.json"
            try:
                with open(wallet_file_root, "r") as f:
                    data = json.load(f)
                
                history_item = {
                    "id": f"manual_{trade['timestamp']}",
                    "symbol": trade['symbol'],
                    "type": trade['type'],
                    "entry_time": trade['timestamp'] - 3600,
                    "close_time": trade['timestamp'],
                    "entry_price": trade['entry_price'],
                    "exit_price": trade['exit_price'],
                    "final_pnl": trade['final_pnl'],
                    "pnl_pct": trade['pnl_percentage']
                }
                
                exists = False
                for t in data.get('trades_history', []):
                    if t.get('close_time') == trade['timestamp'] and t.get('symbol') == trade['symbol']:
                        exists = True
                        break
                        
                if not exists:
                    if 'trades_history' not in data:
                        data['trades_history'] = []
                    data['trades_history'].append(history_item)
                    
                    with open(wallet_file_root, "w") as f:
                        json.dump(data, f, indent=4)
                    print(f"Added trade {trade['symbol']} to {trade['strategy_id']} (root)")
                else:
                    print(f"Trade already exists in {trade['strategy_id']} (root)")
            except:
                print(f"Could not find wallet file for {trade['strategy_id']}")

    print("Injection complete.")
