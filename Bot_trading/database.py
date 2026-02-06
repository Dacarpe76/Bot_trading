import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "trading_data.db"

def init_db():
    """Initializes the database with necessary tables."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table for trades (Simulation & Real)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            side TEXT,
            price REAL,
            amount REAL,
            cost REAL,
            type TEXT, -- 'simulated' or 'real'
            status TEXT, -- 'open', 'closed'
            execution_mode TEXT -- 'real', 'test_1', 'test_2'
        )
    ''')

    # Table for Expense Cube (Cubo de Gastos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expense_cube (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            amount_eur REAL,
            source_trade_id INTEGER,
            description TEXT
        )
    ''')
    
    # Migration for existing tables (simple check)
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN execution_mode TEXT")
    except sqlite3.OperationalError:
        pass # Column likely exists

    conn.commit()
    conn.close()
    print(f"Database {DB_NAME} initialized.")

def log_trade(symbol, side, price, amount, cost, trade_type='simulated', status='open', execution_mode='test_1'):
    """Logs a trade execution."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO trades (timestamp, symbol, side, price, amount, cost, type, status, execution_mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, symbol, side, price, amount, cost, trade_type, status, execution_mode))
    conn.commit()
    trade_id = cursor.lastrowid
    conn.close()
    return trade_id

def log_expense(amount_eur, source_trade_id, description="10% Profit Allocation"):
    """Logs an allocation to the Expense Cube."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO expense_cube (timestamp, amount_eur, source_trade_id, description)
        VALUES (?, ?, ?, ?)
    ''', (timestamp, amount_eur, source_trade_id, description))
    conn.commit()
    conn.close()

def get_expense_cube_balance():
    """Returns total balance in the Expense Cube."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(amount_eur) FROM expense_cube')
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0.0

def get_simulated_balance(mode, initial_capital=500.0):
    """Calculates available EUR balance for a simulation mode."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Sum cost of all open trades (buy side) to deduce from capital
    # Assumption: We only have 'buy' trades so far. If we sell, we'll need logic for PnL.
    # For now (Phase 1), simply: Balance = Initial - Sum(Cost of Open Trades)
    # If we implement selling, we'd add 'sell' proceeds back.
    
    # Get total cost of buys
    cursor.execute('''
        SELECT SUM(cost) FROM trades 
        WHERE execution_mode = ? AND side = 'buy'
    ''', (mode,))
    result = cursor.fetchone()[0]
    total_spent = result if result else 0.0
    
    conn.close()
    return initial_capital - total_spent

def get_open_positions_amounts(mode):
    """Returns a dict of symbol -> total amount for open positions in a mode."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Sum amounts of buys (and subtract sells if we had them)
    # For now just buys
    cursor.execute('''
        SELECT symbol, SUM(amount) FROM trades 
        WHERE execution_mode = ? AND side = 'buy' AND status = 'open'
        GROUP BY symbol
    ''', (mode,))
    
    rows = cursor.fetchall()
    conn.close()
    
    positions = {}
    for symbol, amount in rows:
        positions[symbol] = amount
    return positions

if __name__ == "__main__":
    init_db()
