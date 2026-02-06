import time
from colorama import init, Fore, Style
import pandas as pd
import bot_config as config
from data_loader import MarketData
from strategy import Strategy
from portfolio import PaperPortfolio

init(autoreset=True)

from policy import Policy

def run_backtest():
    print(Fore.CYAN + "================================================")
    print(Fore.CYAN + "   BACKTEST HISTÓRICO [Policy V2]")
    print(Fore.CYAN + "================================================")
    
    market = MarketData()
    strategy = Strategy()
    portfolio = PaperPortfolio()
    policy = Policy()
    
    # 1. Obtener Datos de Mercado
    start_history_date = "2019-06-01" 
    hist_data = market.get_market_data(start_date=start_history_date)
    
    if hist_data.empty:
        print(Fore.RED + "Error crítico: No hay datos de mercado.")
        return

    hist_data = strategy.calculate_indicators(hist_data)
    
    # 2. Obtener Datos Macro (PMI, VIX, TIPS)
    # PMI
    pmi_series = market.get_pmi_data_fred(start_date=hist_data.index[0], end_date=hist_data.index[-1])
    
    # VIX, TIPS
    macro_series = market.get_macro_data(start_date=hist_data.index[0], end_date=hist_data.index[-1])
    
    # 3. Filtrar Periodo de Simulación (Rango Específico)
    start_sim_date = "2020-03-13"
    end_sim_date = "2021-11-10"
    backtest_data = hist_data.loc[start_sim_date:end_sim_date].copy()
    
    # Unir datos Macro
    # join pmi y macro (ffill)
    backtest_data['PMI'] = backtest_data.index.map(lambda d: pmi_series.loc[d]['PMI'] if d in pmi_series.index else config.PMI_DEFAULT)
    backtest_data['PMI'] = backtest_data['PMI'].ffill().fillna(config.PMI_DEFAULT)
    
    # Macro extra (VIX, TIPS) join
    backtest_data = backtest_data.join(macro_series, how='left')
    # Rellenar (VIX y TIPS)
    backtest_data['VIX'] = backtest_data['VIX'].ffill().fillna(20.0) # Default neutral
    backtest_data['TIPS'] = backtest_data['TIPS'].ffill().fillna(1.0) # Default acomodativo

    print(f"Iniciando simulación sobre {len(backtest_data)} días bursátiles...")
    
    total_invested = config.INITIAL_CAPITAL
    
    annual_summary = []
    current_year = backtest_data.index[0].year
    year_start_val = config.INITIAL_CAPITAL
    
    for date, row in backtest_data.iterrows():
        # Detección de cambio de año
        if date.year != current_year:
            year_end_val = portfolio.get_total_value({'BTC': row['BTC_Close'], 'GOLD': row['GOLD_Close']})
            annual_summary.append({
                'Year': current_year,
                'Start': year_start_val,
                'End': year_end_val,
                'Invested_Year_End': total_invested
            })
            current_year = date.year
            year_start_val = year_end_val

        # --- Simulación Diaria ---
        current_prices = {'BTC': row['BTC_Close'], 'GOLD': row['GOLD_Close']}
        
        # Datos Macro Diarios
        pmi_val = row['PMI']
        vix_val = row['VIX']
        tips_val = row['TIPS']
        
        # 1. Aporte Mensual
        if date.day == config.DIA_APORTE_MENSUAL and config.SIMULAR_APORTE_MENSUAL > 0:
             portfolio.add_monthly_contribution(date)
             total_invested += config.SIMULAR_APORTE_MENSUAL
             
        # 2. Señal Técnica + PMI Base
        raw_signal = strategy.get_signal(row, pmi_val)
        
        # 3. POLÍTICA DE CARTERA (Capa Superior)
        # Detectar Régimen
        regimen = policy.detectar_regimen(pmi_val, tips_val, vix_val)
        
        # Aplicar Reglas (Bandas USDC + StopLoss + TakeProfit)
        policy_decision = policy.aplicar_politica(
            raw_weights=raw_signal,
            current_prices=current_prices,
            holdings=portfolio.holdings,
            avg_prices=portfolio.avg_price,
            regimen=regimen
        )
        
        # 4. Rebalanceo (Ejecución)
        portfolio.rebalance(policy_decision, current_prices, date)
            
        # 5. Registro Diario
        portfolio.record_daily_status(date, current_prices, pmi_val)

    # Cerrar el último año
    final_prices = {
        'BTC': backtest_data.iloc[-1]['BTC_Close'],
        'GOLD': backtest_data.iloc[-1]['GOLD_Close']
    }
    final_val_total = portfolio.get_total_value(final_prices)
    annual_summary.append({
        'Year': current_year,
        'Start': year_start_val,
        'End': final_val_total,
        'Invested_Year_End': total_invested
    })
    
    # --- Exportar operaciones a CSV ---
    try:
        ops_df = pd.DataFrame(portfolio.trade_log)
        if not ops_df.empty:
            filename = "operations_log.csv"
            ops_df.to_csv(filename, index=False)
            print(Fore.GREEN + f"\n[SUCCESS] Registro de operaciones guardado en '{filename}' ({len(ops_df)} ops).")
            print("\nÚLTIMAS 5 OPERACIONES:")
            print(ops_df.tail())
    except Exception as e:
        print(f"Error guardando CSV de operaciones: {e}")

    # --- Resultados Finales ---
    print("\n" + Fore.WHITE + "--- REPORTE ANUAL ---")
    print(f"{'AÑO':<6} | {'INICIA €':<12} | {'TERMINA €':<12} | {'ACUMULADO €':<12} | {'RETORNO AÑO'}")
    print("-" * 65)
    
    cumulative_profit = 0
    for y in annual_summary:
        # Nota: El retorno anual "puro" es difícil de calcular exacto con aportes mensuales sin XIRR.
        # Aquí mostramos crecimiento patrimonial bruto.
        delta = y['End'] - y['Start']
        perc = ((y['End'] - y['Start']) / y['Start']) * 100 # Aprox
        print(f"{y['Year']:<6} | {y['Start']:<12.2f} | {y['End']:<12.2f} | {y['Invested_Year_End']:<12.2f} | {perc:+.2f}% (Bruto)")

    profit = final_val_total - total_invested
    roi = (profit / total_invested) * 100
    
    print("\n" + Fore.WHITE + "--- RESULTADOS GLOBALES (2020-HOY) ---")
    print(portfolio.get_status_str(final_prices))
    print(Fore.YELLOW + f"\nCapital Invertido Total: {total_invested:.2f}€")
    print(Fore.GREEN + f"Beneficio Neto:          {profit:.2f}€")
    print(Fore.GREEN + f"ROI Total:               {roi:.2f}%")
    
    # Max Drawdown
    values = [d['TotalValue'] for d in portfolio.history]
    if values:
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
        print(Fore.RED + f"Max Drawdown:            {max_dd*100:.2f}%")

def main():
    # Por defecto ejecutamos Backtest en esta fase
    run_backtest()

if __name__ == "__main__":
    main()
