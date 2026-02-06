import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def plot_equity():
    print("🎨 Generating Equity Chart...")
    
    # 1. Read Data
    try:
        df = pd.read_csv("daily_equity_comparison.csv", parse_dates=['date'])
        df.set_index('date', inplace=True)
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return

    # 2. Plot Setup
    plt.figure(figsize=(14, 8))
    
    print(f"{'STRATEGY':<25} | {'MAX DRAWDOWN':<12} | {'VOLATILITY':<10}")
    print("-" * 55)

    # Plot each column (strategies)
    for column in df.columns:
        if column != 'Leader': # Ignore analysis columns if present
            # Calculate Risk Metrics
            series = df[column]
            
            # Max Drawdown
            rolling_max = series.cummax()
            drawdown = (series - rolling_max) / rolling_max
            max_drawdown = drawdown.min() * 100
            
            # Volatility (Daily Returns Std Dev * sqrt(365))
            returns = series.pct_change().dropna()
            volatility = returns.std() * (365 ** 0.5) * 100
            
            print(f"{column:<25} | {max_drawdown:>11.2f}% | {volatility:>9.1f}%")

            plt.plot(df.index, df[column], label=f"{column} (MDD: {max_drawdown:.1f}%)", linewidth=1, alpha=0.9)
            
            # Annotate final value
            final_val = df[column].iloc[-1]
            plt.annotate(f"{final_val:.0f}€", 
                         xy=(df.index[-1], final_val), 
                         xytext=(10, 0), textcoords='offset points',
                         fontsize=10, fontweight='bold')

    # Formatting
    plt.title('Multi-Strategy Equity Comparison (2020-Present)', fontsize=16, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Equity (€)', fontsize=12)
    plt.legend(loc='upper left', fontsize=11)
    plt.grid(True, linestyle='--', alpha=0.6)
    
    # Format X-axis dates
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.gca().xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.gcf().autofmt_xdate() # Rotate dates

    # Save
    output_file = "equity_comparison.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✅ Chart saved to: {output_file}")
    
if __name__ == "__main__":
    plot_equity()
