import pandas as pd

def generate_report():
    try:
        df = pd.read_csv("backtest_full_results.csv")
    except FileNotFoundError:
        print("Error: backtest_full_results.csv not found.")
        return

    # Filter S4
    s4 = df[df['Strategy'] == 'S4_AggrCent'].copy()
    
    if s4.empty:
        print("No trades found for S4_AggrCent.")
        return

    # Convert Times
    s4['Entry_Time'] = pd.to_datetime(s4['Entry_Time'])
    s4['Exit_Time'] = pd.to_datetime(s4['Exit_Time'])
    
    # Calc Duration
    s4['Duration'] = s4['Exit_Time'] - s4['Entry_Time']
    
    # Calc PnL Euro (Assuming 10% of 500€ = 50€ Position)
    POSITION_SIZE = 50.0
    s4['PnL_EUR'] = POSITION_SIZE * (s4['Net_PnL_Pct'] / 100)
    
    print("\nREPORTE DETALLADO ESTRATEGIA S4 (AggrCent) - 10% SIZE")
    print("=======================================================")
    print(f"Capital por Operación (10% de 500€): {POSITION_SIZE}€\n")
    
    total_eur = 0
    
    # Updated Header with Dates
    print(f"{'SYMBOL':<8} | {'START TIME':<16} | {'END TIME':<16} | {'ENTRY':<10} | {'EXIT':<10} | {'PNL (€)':<8} | {'REASON'}")
    print("-" * 100)
    
    for idx, row in s4.iterrows():
        start_str = row['Entry_Time'].strftime('%m-%d %H:%M')
        end_str = row['Exit_Time'].strftime('%m-%d %H:%M')
        
        pnl = row['PnL_EUR']
        total_eur += pnl
        
        print(f"{row['Symbol']:<8} | {start_str:<16} | {end_str:<16} | {row['Entry_Price']:<10.4f} | {row['Exit_Price']:<10.4f} | {pnl:>7.2f}€ | {row['Reason']}")
        
    print("-" * 100)
    print(f"TOTAL BENEFICIO/PÉRDIDA: {total_eur:.2f}€")
    print(f"TOTAL OPERACIONES: {len(s4)}")

if __name__ == "__main__":
    generate_report()
