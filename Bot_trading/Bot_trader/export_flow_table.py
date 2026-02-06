import pandas as pd
from colorama import init, Fore

init(autoreset=True)

try:
    df = pd.read_csv('operations_log.csv')
    
    # Crear lista para la nueva tabla estructurada
    flow_data = []
    
    for _, row in df.iterrows():
        date = row['Date']
        action = row['Action']
        asset = row['Asset']
        
        # Parsear valores
        amount = float(row['Amount'])
        price = float(row['Price'])
        value = float(row['Value']) # Negativo para Buy, Positivo para Sell
        cash_after = float(row['Cash_After'])
        profit = float(row['Profit']) if 'Profit' in row and pd.notnull(row['Profit']) else 0.0
        
        btc_bal = float(row['BTC_After']) if 'BTC_After' in row and pd.notnull(row['BTC_After']) else 0.0
        gold_bal = float(row['GOLD_After']) if 'GOLD_After' in row and pd.notnull(row['GOLD_After']) else 0.0
        
        entry = {
            'Date': date,
            'Type': action,
            'Source (Sale)': "",
            'Destination (Entra)': "",
            'Details': "",
            'Profit': "",
            'BTC Bal': f"{btc_bal:.6f}",
            'Gold Bal': f"{gold_bal:.4f}",
            'USDC Bal': f"{cash_after:.2f}"
        }
        
        if action == 'BUY':
            cost_usdc = abs(value)
            entry['Source (Sale)'] = f"{cost_usdc:.2f} USDC"
            entry['Destination (Entra)'] = f"{amount:.6f} {asset}"
            entry['Details'] = f"Price: {price:.2f}"
            entry['Profit'] = "-"
            
        elif action == 'SELL':
            revenue_usdc = value
            entry['Source (Sale)'] = f"{amount:.6f} {asset}"
            entry['Destination (Entra)'] = f"{revenue_usdc:.2f} USDC"
            entry['Details'] = f"Price: {price:.2f}"
            if profit > 0:
                entry['Profit'] = f"+{profit:.2f} (Win)"
            elif profit < 0:
                entry['Profit'] = f"{profit:.2f} (Loss)"
            else:
                entry['Profit'] = "0.00"
                
        elif action == 'DEPOSIT':
            entry['Source (Sale)'] = "Bank (Fiat)"
            entry['Destination (Entra)'] = f"{value:.2f} USDC"
            entry['Details'] = "Mthly Contribution"
            entry['Profit'] = "-"
            
        flow_data.append(entry)
        
    # Crear DataFrame formateado
    flow_df = pd.DataFrame(flow_data)
    
    # Reordenar columnas para mejor lectura
    cols = ['Date', 'Type', 'Source (Sale)', 'Destination (Entra)', 'Profit', 'BTC Bal', 'Gold Bal', 'USDC Bal']
    flow_df = flow_df[cols]
    
    output_file = "detailed_flow_table.txt"
    
    # Usar tabulate con formato 'grid' para mejor alineación
    try:
        content = flow_df.to_markdown(index=False, tablefmt="grid")
    except ImportError:
        content = flow_df.to_string(index=False)
        
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(Fore.GREEN + f"[SUCCESS] Tabla de flujo guardada en '{output_file}'")
    print("\nPrimeras 15 filas del flujo:\n")
    print("\n".join(content.splitlines()[:20]))

except Exception as e:
    print(Fore.RED + f"Error generando tabla detallada: {e}")
