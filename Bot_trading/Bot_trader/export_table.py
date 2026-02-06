import pandas as pd
from colorama import init, Fore

init(autoreset=True)

try:
    df = pd.read_csv('operations_log.csv')
    
    # Formatear columnas numéricas para visualización limpia
    if 'Price' in df.columns:
        df['Price'] = df['Price'].apply(lambda x: f"{x:.2f}")
    if 'Value' in df.columns:
        df['Value'] = df['Value'].apply(lambda x: f"{x:.2f}")
    if 'Profit' in df.columns:
        df['Profit'] = df['Profit'].apply(lambda x: f"{x:.2f}")
    if 'Cash_After' in df.columns:
        df['Cash_After'] = df['Cash_After'].apply(lambda x: f"{x:.2f}")
    if 'Amount' in df.columns:
         df['Amount'] = df['Amount'].apply(lambda x: f"{x:.6f}")

    # Renombrar columnas para ahorrar espacio si es necesario
    # df = df.rename(columns={'Cash_After': 'Cash'})

    output_file = "operations_table.txt"
    
    # Intentar usar tabulate para formato grid/markdown bonito
    try:
        content = df.to_markdown(index=False, tablefmt="grid")
    except ImportError:
        # Fallback a to_string de pandas si falta tabulate
        content = df.to_string(index=False)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(Fore.GREEN + f"[SUCCESS] Tabla guardada en '{output_file}'")
    print("\nPrimeras 10 filas del archivo generado:\n")
    print("\n".join(content.splitlines()[:15]))
            
except Exception as e:
    print(Fore.RED + f"Error generando tabla: {e}")
