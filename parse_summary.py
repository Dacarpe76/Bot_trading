import re
import sys

def analyze(text):
    total_trades = 0
    wins = 0
    losses = 0
    total_pnl = 0.0
    
    lines = text.split('\n')
    strat_pnl = {}
    
    for i, line in enumerate(lines):
        if 'TRADE CLOSED' in line:
            total_trades += 1
            if '✅' in line:
                wins += 1
            else:
                losses += 1
                
            # Extract strategy
            # [WEB] ✅ TRADE CLOSED (Kraken Sentinel 2026): DOT/EUR
            m = re.search(r'\((.*?)\):', line)
            if m:
                strat = m.group(1)
                if strat not in strat_pnl:
                    strat_pnl[strat] = {'trades': 0, 'pnl': 0.0}
                strat_pnl[strat]['trades'] += 1
                
        if 'Net PnL:' in line:
            # Net PnL: +0.08 EUR or -0.01 EUR
            m2 = re.search(r'Net PnL: ([\+\-]?[\d\.]+) EUR', line)
            if m2:
                pnl_val = float(m2.group(1))
                total_pnl += pnl_val
                
                # Assign to last seen strategy (assuming block order)
                # Walk back to find the strategy name
                for j in range(i, max(-1, i-10), -1):
                    sm = re.search(r'\((.*?)\):', lines[j])
                    if sm:
                        last_strat = sm.group(1)
                        if last_strat in strat_pnl:
                             strat_pnl[last_strat]['pnl'] += pnl_val
                        break

    print(f"--- RESUMEN ÚLTIMAS 24 HORAS ---")
    print(f"Operaciones totales: {total_trades}")
    print(f"Ganadoras: {wins} ({(wins/total_trades*100):.1f}%)" if total_trades > 0 else "Ganadoras: 0")
    print(f"Perdedoras: {losses} ({(losses/total_trades*100):.1f}%)" if total_trades > 0 else "Perdedoras: 0")
    print(f"PnL Total (+ comisiones restadas): {total_pnl:+.2f} EUR")
    print("\n--- DESGLOSE POR ESTRATEGIA ---")
    for s, data in sorted(strat_pnl.items(), key=lambda x: x[1]['pnl'], reverse=True):
        print(f"{s}: {data['trades']} trades | PnL: {data['pnl']:+.2f} EUR")

if __name__ == "__main__":
    with open("telegram_trades.txt", "r") as f:
        text = f.read()
    analyze(text)
