import sys
import os
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Ensure Bot_trader is in path
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

# Import the backtester class from run_macro_live.py
from run_macro_live import MacroPolicyBacktester

def main():
    # 1. Configuration
    # years = 5
    end_date = datetime.now()
    # start_date = end_date - timedelta(days=years*365)
    start_date = datetime(2020, 1, 1) # FIXED START DATE
    
    start_date_str = start_date.strftime("%d/%m/%Y") # Format required by run_simulation
    yf_start_date = start_date.strftime("%Y-%m-%d") # Format for yfinance
    
    print(f"--- Running Comparison: Macro Policy vs S&P 500 ---")
    print(f"Start Date: {start_date_str}")
    
    # 2. Run Macro Policy Backtest
    print("\n[1/3] Running Macro Policy Backtest (with DCA)...")
    bot = MacroPolicyBacktester(initial_capital=500.0)
    
    # Run simulation with DCA 100 EUR
    try:
        res = bot.run_simulation(start_date_str, quiet=True, dca_amount=100.0)
    except Exception as e:
        print(f"Error running simulation: {e}")
        return

    # Extract equity curve
    if not bot.daily_equity:
        print("Error: No equity data generated from Macro Policy.")
        return

    macro_equity = pd.DataFrame(bot.daily_equity)
    macro_equity['date'] = pd.to_datetime(macro_equity['date'])
    macro_equity.set_index('date', inplace=True)
    macro_equity.rename(columns={'equity': 'Macro_Equity'}, inplace=True)
    
    print(f"   Macro Policy Final Equity: {res['final_equity']:.2f} EUR")
    
    # 3. Fetch S&P 500 & MSCI World Data
    print("\n[2/3] Fetching Benchmarks (SPY + URTH)...")
    try:
        # Fetch both tickers
        benchmarks = yf.download("SPY URTH", start=yf_start_date, progress=False, group_by='ticker', auto_adjust=False)
    except Exception as e:
        print(f"Error fetching benchmarks: {e}")
        return

    # Process SPY
    try:
        spy_data = benchmarks['SPY'] if 'SPY' in benchmarks.columns.levels[0] else benchmarks
        close_col = [c for c in spy_data.columns if 'Adj Close' in c]
        if not close_col: close_col = [c for c in spy_data.columns if 'Close' in c]
        sp500 = spy_data[close_col].copy()
        sp500.columns = ['SP500_Price']
    except Exception as e:
         print(f"Error processing SPY: {e}")
         return

    # Process MSCI World (URTH)
    try:
        urth_data = benchmarks['URTH'] if 'URTH' in benchmarks.columns.levels[0] else None
        if urth_data is not None:
             close_col = [c for c in urth_data.columns if 'Adj Close' in c]
             if not close_col: close_col = [c for c in urth_data.columns if 'Close' in c]
             msci = urth_data[close_col].copy()
             msci.columns = ['MSCI_Price']
        else:
             print("Warning: URTH data not found in response.")
             msci = pd.DataFrame()
    except Exception as e:
         print(f"Error processing URTH: {e}")
         msci = pd.DataFrame()

    if sp500.index.tz is not None: sp500.index = sp500.index.tz_localize(None) 
    if not msci.empty and msci.index.tz is not None: msci.index = msci.index.tz_localize(None)


    # 4. Align and Compare
    print("\n[3/3] Generating Comparison...")
    
    # Merge
    comparison = macro_equity.join(sp500, how='inner')
    if not msci.empty:
        comparison = comparison.join(msci, how='left') # Left join to keep macro dates, fill ffill
        comparison['MSCI_Price'] = comparison['MSCI_Price'].ffill()
    
    if comparison.empty:
        print("Error: No overlapping data found!")
        return

    # --- BENCHMARK DCA SIMULATION ---
    def simulate_dca(price_series, initial_cash=500.0, monthly_contribution=100.0):
        equity_curve = []
        cash = initial_cash
        shares = 0.0
        total_invested = 0.0
        
        # Initial buy
        first_price = price_series.iloc[0]
        if not pd.isna(first_price) and first_price > 0:
            shares = cash / first_price
            total_invested = cash
            cash = 0.0
            
        for date, price in price_series.items():
            # Day 10 contribution
            if date.day == 10:
                shares += monthly_contribution / price if (not pd.isna(price) and price > 0) else 0
                total_invested += monthly_contribution
                
            val = (shares * price) + cash if not pd.isna(price) else (shares * 0) + cash
            equity_curve.append(val)
            
        return equity_curve, total_invested

    # Run SPY DCA
    sp500_vals, sp500_invested = simulate_dca(comparison['SP500_Price'])
    comparison['SP500_Equity'] = sp500_vals
    
    # Run MSCI DCA
    if 'MSCI_Price' in comparison.columns:
        msci_vals, msci_invested = simulate_dca(comparison['MSCI_Price'])
        comparison['MSCI_Equity'] = msci_vals
    else:
        comparison['MSCI_Equity'] = 0.0
        msci_invested = 0

    # Metrics
    final_macro = comparison['Macro_Equity'].iloc[-1]
    final_sp500 = comparison['SP500_Equity'].iloc[-1]
    final_msci = comparison['MSCI_Equity'].iloc[-1] if 'MSCI_Equity' in comparison else 0
    
    print("\n" + "="*60)
    print(f"RESULTADOS DCA (500€ Inicio + 100€/mes dia 10)")
    print(f"Periodo: {comparison.index[0].date()} - {comparison.index[-1].date()}")
    print("="*60)
    print(f"{'Estrategia':<15} | {'Final (€)':<10} | {'Total Inv.':<10}")
    print("-" * 50)
    print(f"{'Macro Policy':<15} | {final_macro:10.2f} | ~{sp500_invested:10.0f}")
    print(f"{'S&P 500':<15} | {final_sp500:10.2f} |  {sp500_invested:10.0f}")
    if final_msci > 0:
        print(f"{'MSCI World':<15} | {final_msci:10.2f} |  {msci_invested:10.0f}")
    print("="*60)
    
    # Save CSV
    comparison.to_csv("comparison_result_dca.csv")
    
    # Plot
    plt.style.use('bmh')
    plt.figure(figsize=(12, 6))
    
    plt.plot(comparison.index, comparison['Macro_Equity'], label=f'Macro Policy ({final_macro:.0f}€)', linewidth=2, color='#2ecc71')
    plt.plot(comparison.index, comparison['SP500_Equity'], label=f'S&P 500 ({final_sp500:.0f}€)', linewidth=2, color='#3498db', alpha=0.8)
    if final_msci > 0:
        plt.plot(comparison.index, comparison['MSCI_Equity'], label=f'MSCI World ({final_msci:.0f}€)', linewidth=2, color='#9b59b6', alpha=0.8)
    
    plt.title(f'DCA Strategy Comparison (Since 2020)', fontsize=14)
    plt.xlabel('Fecha')
    plt.ylabel('Equity (EUR)')
    plt.legend(loc='upper left')
    plt.grid(True, alpha=0.3)
    
    # Add watermark or text
    plt.text(comparison.index[-1], comparison['Macro_Equity'].iloc[-1], f"{final_macro:.0f}€", fontsize=10, verticalalignment='bottom')
    
    plot_file = "comparison_plot.png"
    plt.savefig(plot_file, dpi=150)
    print(f"Gráfico guardado en: {plot_file}")

if __name__ == "__main__":
    main()
