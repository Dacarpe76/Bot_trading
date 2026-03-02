import json
import re
import datetime
import glob
import os

TXT_FILE = "operaciones.txt"

# Mapping from Telegram display name to internal strategy ID
STRAT_MAP = {
    "Aggressive Sniper": "Aggressive",
    "Aggressive Cent": "AggrCent",
    "NetScalp DCA": "NetScalp",
    "Rolling DCA v3": "RollingDCA_v3",
    "Hybrid Elite": "HybridElite",
    "Rolling DCA": "RollingDCA",
    "Rolling DCA v2": "RollingDCA_v2",
    "Rolling DCA Short": "Rol_dca_sh_v1",
    "Rolling DCA Short v2": "Rol_dca_sh_v2",
    "Aspiradora Sniper": "Aspiradora",
    "Hormiga": "Hormiga",
    "NetScalp_Rolling": "NetScalp_Rolling",
    "Rolling DCA Evolution": "RollingDCA_Evolution",
    "Rolling DCA Inmortal": "RollingDCA_Inmortal",
    "Kraken Sentinel 2026": "KrakenEvent",
    "Kraken Sentinel Turbo": "SentinelTurbo",
    "Antigravity Sniper": "Antigravity",
    "Saint-Grial Master": "SaintGrial",
    "Saint-Grial PRO X3": "SaintGrialProX3",
    "Vector Flujo V1": "VectorFlujo_V1"
}

def parse_txt(filepath):
    trades = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern to match each block
    blocks = content.split("Bot_inversor, ")
    for block in blocks:
        if not block.strip(): continue
        
        try:
            # Bot_inversor, [1/3/26 0:41]
            time_match = re.search(r'\[(.*?)\]', block)
            if not time_match: continue
            time_str = time_match.group(1) # e.g. "1/3/26 0:41", assumes dd/mm/yy HH:MM
            dt = datetime.datetime.strptime(time_str, "%d/%m/%y %H:%M")
            close_time = dt.timestamp()
            
            # [WEB] ✅ TRADE CLOSED (Rolling DCA v2): DOT/EUR
            trade_match = re.search(r'TRADE CLOSED \((.*?)\):\s*(\w+/\w+)', block)
            if not trade_match: continue
            display_name = trade_match.group(1)
            symbol = trade_match.group(2)
            
            # Type: LONG
            side_match = re.search(r'Type:\s*(LONG|SHORT)', block)
            side = side_match.group(1) if side_match else "LONG"
            
            # Entry: 1.3928
            entry = float(re.search(r'Entry:\s*([0-9.]+)', block).group(1))
            exit_pr = float(re.search(r'Exit:\s*([0-9.]+)', block).group(1))
            
            # Net PnL: +0.10 EUR
            pnl_match = re.search(r'Net PnL:\s*([+\-0-9.]+)', block)
            net_pnl = float(pnl_match.group(1)) if pnl_match else 0.0
            
            # Fees: 0.01 EUR
            fee_match = re.search(r'Fees:\s*([0-9.]+)', block)
            fees = float(fee_match.group(1)) if fee_match else 0.0
            
            # Recover size: PnL = (Exit - Entry)*Size - Fees --> Size = (PnL + Fees) / (Exit - Entry)
            diff = exit_pr - entry if side == 'LONG' else entry - exit_pr
            if diff != 0:
                size = (net_pnl + fees) / diff
                if size < 0: size = abs(size) # Failsafe
            else:
                size = 0.0
                
            margin = size * entry
            
            strat_id = STRAT_MAP.get(display_name, display_name)
            
            trades.append({
                "strat_id": strat_id,
                "record": {
                    "symbol": symbol,
                    "type": side,
                    "size": size,
                    "margin": margin,
                    "leverage": 1.0,
                    "avg_price": entry,
                    "entry_price": entry,
                    "entry_time": close_time - 3600, # Approximate 1 hr before
                    "close_price": exit_pr,
                    "close_time": close_time,
                    "final_pnl": net_pnl,
                    "final_fees": fees,
                    "id": f"recov_{int(close_time)}"
                }
            })
        except Exception as e:
            print(f"Failed parsing block: {e}")
            
    return trades

def restore():
    print("Iniciando recuperación de datos...")
    trades = parse_txt(TXT_FILE)
    print(f"Se encontraron {len(trades)} operaciones cerradas en el texto.")
    
    # Group by strat_id
    grouped = {}
    for t in trades:
        stid = t["strat_id"]
        if stid not in grouped: grouped[stid] = []
        grouped[stid].append(t["record"])
        
    for stid, records in grouped.items():
        state_file = f"wallet_state_{stid}.json"
        if not os.path.exists(state_file):
            print(f"Advertencia: Archivo {state_file} no encontrado. Creando uno vacío...")
            state = {"balance": 500.0, "positions": {}, "history": [], "next_id": 1, "start_time": 1772323200}
        else:
            with open(state_file, 'r') as f:
                state = json.load(f)
                
        # Inject records, avoiding exact duplicates
        added = 0
        for rec in records:
            # Check for existing
            exists = False
            for hist in state.get("history", []):
                diff_time = abs(hist.get("close_time", 0) - rec["close_time"])
                if hist.get("symbol") == rec["symbol"] and diff_time < 300: # Found trade within 5 mins
                    exists = True
                    break
            if not exists:
                if "history" not in state: state["history"] = []
                state["history"].append(rec)
                added += 1
                
        # Sort by close_time
        state["history"] = sorted(state.get("history", []), key=lambda x: x.get("close_time", 0))
        
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=4)
            
        print(f"[*] {stid}: +{added} operaciones inyectadas (Total historial: {len(state.get('history', []))})")

if __name__ == "__main__":
    restore()
