import requests
import config

def send_message(message):
    """Sends a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.MY_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False

from datetime import datetime

def send_consolidated_report(real_data, test1_data, test2_data, expense_cube_eur):
    """Formats and sends the consolidated hourly report."""
    
    def format_section(title, data):
        total = data['BTC'] + data['PAXG'] + data['USDC'] + data['EUR']
        return f"""
*{title}* (Total: {total:.2f} €)
Bitcoin: {data['BTC']:.2f} €
Oro: {data['PAXG']:.2f} €
Liquidez (EUR/USDC): {data['EUR'] + data['USDC']:.2f} €
"""
    
    # Calculate Grand Total
    grand_total = (
        sum(real_data.values()) + 
        sum(test1_data.values()) + 
        sum(test2_data.values()) + 
        expense_cube_eur
    )

    report = f"""
📊 *Informe Kraken Detallado*
📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}

{format_section("REAL", real_data)}
{format_section("PRUEBA 1 (Std 500€)", test1_data)}
{format_section("PRUEBA 2 (Fast 500€)", test2_data)}

🏦 *Cubo de Gastos:* {expense_cube_eur:.2f} €

∑ *TOTAL GLOBAL:* {grand_total:.2f} €
    """
    send_message(report)
