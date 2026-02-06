from data_loader import MarketData
import pandas as pd

try:
    md = MarketData()
    print("Probando descarga PMI desde FRED...")
    pmi = md.get_pmi_data_fred("2020-01-01", "2024-01-01")
    print("\nResumen PMI:")
    print(pmi.describe())
    print("\nPrimeras 5 filas:")
    print(pmi.head())
    
    # Check if constant
    is_constant = pmi['PMI'].nunique() <= 1
    print(f"\n¿Es constante? {is_constant}")
    
except Exception as e:
    print(f"Error test: {e}")
