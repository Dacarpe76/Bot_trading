import sys
try:
    from kraken_bot import strategies
    print("Syntax Valid")
except ImportError as e:
    print(f"Import Error: {e}")
except SyntaxError as e:
    print(f"Syntax Error: {e}")
except Exception as e:
    print(f"Other Error: {e}")
