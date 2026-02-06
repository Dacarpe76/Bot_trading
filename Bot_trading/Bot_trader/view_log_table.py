import pandas as pd

try:
    df = pd.read_csv('operations_log.csv')
    
    # Formatear columnas numéricas
    # df['Price'] = df['Price'].apply(lambda x: f"{x:.2f}")
    # df['Value'] = df['Value'].apply(lambda x: f"{x:.2f}")
    # df['Cash_After'] = df['Cash_After'].apply(lambda x: f"{x:.2f}")
    
    print(f"### Historial de Operaciones (Total: {len(df)})")
    
    # Función simple para imprimir fila Markdown
    def print_md_row(vals):
        # Convertir a string y pad
        fmt_vals = [str(v).replace('\n', ' ') for v in vals]
        print("| " + " | ".join(fmt_vals) + " |")
        
    cols = list(df.columns)
    
    # Imprimir Header
    print_md_row(cols)
    print("|" + "|".join(["---"] * len(cols)) + "|")
    
    # Primeras 20 filas
    for _, row in df.head(20).iterrows():
        print_md_row(row.values)
        
    # Separador si es largo
    if len(df) > 40:
        print(f"| ... ({len(df)-40} operaciones ocultas) ... |" + "|".join(["..."] * (len(cols)-1)) + "|")
        
    # Últimas 20 filas
    if len(df) > 20:
        for _, row in df.tail(20).iterrows():
            print_md_row(row.values)
            
except Exception as e:
    print(f"Error reading log: {e}")
