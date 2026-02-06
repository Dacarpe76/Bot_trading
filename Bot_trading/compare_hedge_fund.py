
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime

# Add path
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

from run_macro_live import MacroPolicyBacktester
from hedge_fund_backtest import HedgeFundBacktester
import warnings
warnings.filterwarnings('ignore')

def simulate_dca_benchmark(price_series, initial_cash=500.0, monthly_contribution=100.0):
    equity_curve = []
    cash = initial_cash
    shares = 0.0
    total_invested = 0.0
    
    # Init
    first_price = price_series.iloc[0]
    if not pd.isna(first_price) and first_price > 0:
        shares = cash / first_price
        total_invested = cash
        cash = 0.0
        
    for date, price in price_series.items():
        if date.day == 10:
             shares += monthly_contribution / price if (not pd.isna(price) and price > 0) else 0
             total_invested += monthly_contribution
             
        val = (shares * price) + cash if not pd.isna(price) else (shares * 0) + cash
        equity_curve.append(val)
        
    return equity_curve, total_invested

def main():
    print("--- HEDGE FUND STRATEGY SIMULATION ---")
    years = 5
    start_date_str = "01/01/2020"
    
    # 1. Run Baseline (Macro Policy V2)
    print("\n[1/4] Running Baseline (Macro Policy)...")
    base_bot = MacroPolicyBacktester(initial_capital=500.0)
    base_res = base_bot.run_simulation(start_date_str, quiet=True, dca_amount=100.0)
    
    base_equity = pd.DataFrame(base_bot.daily_equity)
    base_equity['date'] = pd.to_datetime(base_equity['date'])
    base_equity.set_index('date', inplace=True)
    base_equity.rename(columns={'equity': 'Base_Equity'}, inplace=True)
    
    # 2. Run Hedge Fund Strategy
    print("\n[2/4] Running Hedge Fund Strategy (Shorts + Staking + ETH)...")
    hedge_bot = HedgeFundBacktester(initial_capital=500.0)
    hedge_res = hedge_bot.run_simulation(start_date_str, quiet=True, dca_amount=100.0)
    
    hedge_equity = pd.DataFrame(hedge_bot.daily_equity)
    hedge_equity['date'] = pd.to_datetime(hedge_equity['date'])
    hedge_equity.set_index('date', inplace=True)
    hedge_equity.rename(columns={'equity': 'Hedge_Equity'}, inplace=True)
    
    # 3. Fetch Benchmarks
    print("\n[3/4] Fetching S&P 500 (SPY)...")
    yf_start = "2020-01-01"
    benchmarks = yf.download("SPY", start=yf_start, progress=False, auto_adjust=False)
    
    # Process SPY
    if isinstance(benchmarks.columns, pd.MultiIndex):
        benchmarks.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in benchmarks.columns.values]
    
    col_name = None
    for c in benchmarks.columns:
        if 'Adj Close' in c or 'Close' in c:
            col_name = c
            break
    
    sp500 = benchmarks[[col_name]].copy()
    sp500.columns = ['SP500_Price']
    if sp500.index.tz is not None: sp500.index = sp500.index.tz_localize(None)

    # 4. Compare
    print("\n[4/4] Generating Report...")
    
    # Align to Base
    comparison = base_equity.join(hedge_equity, how='inner').join(sp500, how='left').ffill()
    
    # Benchmark DCA
    sp500_vals, invested = simulate_dca_benchmark(comparison['SP500_Price'])
    comparison['SP500_Equity'] = sp500_vals
    
    final_base = comparison['Base_Equity'].iloc[-1]
    final_hedge = comparison['Hedge_Equity'].iloc[-1]
    final_sp500 = comparison['SP500_Equity'].iloc[-1]
    
    print("\n" + "="*60)
    print(f"RESULTADOS FINAL HEDGE FUND v1.0 (DCA 100€/mes)")
    print(f"Periodo: {comparison.index[0].date()} - {comparison.index[-1].date()}")
    print("="*60)
    print(f"{'Estrategia':<20} | {'Final (€)':<12} | {'Rentab.':<10}")
    print("-" * 50)
    
    def gain(final, inv): return ((final - inv) / inv) * 100
    
    print(f"{'S&P 500':<20} | {final_sp500:10.2f} | {gain(final_sp500, invested):+.1f}%")
    print(f"{'Macro Policy (Base)':<20} | {final_base:10.2f} | {gain(final_base, invested):+.1f}%")
    print(f"{'Hedge Fund (New)':<20} | {final_hedge:10.2f} | {gain(final_hedge, invested):+.1f}%")
    print("="*60)
    
    # Plot
    plt.style.use('bmh')
    plt.figure(figsize=(12, 6))
    
    plt.plot(comparison.index, comparison['Base_Equity'], label=f'Macro Policy ({final_base:.0f}€)', linewidth=1.5, color='gray', linestyle='--')
    plt.plot(comparison.index, comparison['SP500_Equity'], label=f'S&P 500 ({final_sp500:.0f}€)', linewidth=1.5, color='#3498db', alpha=0.6)
    plt.plot(comparison.index, comparison['Hedge_Equity'], label=f'Hedge Fund ({final_hedge:.0f}€)', linewidth=2.5, color='#e74c3c')
    
    plt.title(f'Hedge Fund Strategy: Shorts, Staking & ETH (vs Macro & SP500)', fontsize=14)
    plt.xlabel('Date')
    plt.ylabel('Total Equity (€)')
    plt.legend(loc='upper left')
    plt.grid(True, alpha=0.3)
    
    plot_file = "hedge_performance.png"
    plt.savefig(plot_file, dpi=150)
    print(f"Chart saved to {plot_file}")
    
    comparison.to_csv("hedge_results.csv")

if __name__ == "__main__":
    main()
