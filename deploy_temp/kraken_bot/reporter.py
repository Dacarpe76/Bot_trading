import logging
import requests
import datetime
from kraken_bot import config

class TelegramReporter:
    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.last_report_time = datetime.datetime.now()

    def send_message(self, text):
        if not self.token or not self.chat_id:
            logging.warning("Telegram config missing. Skipping report.")
            return

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown" # Or HTML
            }
            resp = requests.post(self.base_url, json=payload, timeout=10)
            if resp.status_code != 200:
                logging.error(f"Telegram Send Error: {resp.text}")
            else:
                logging.info("Telegram Report Sent.")
        except Exception as e:
            logging.error(f"Telegram Connection Error: {e}")

    def generate_report(self, strategies):
        """
        Generates a summary report for all strategies.
        strategies: dict of {id: StrategyObject}
        """
        now = datetime.datetime.now()
        report = []
        report.append(f"📊 *HOURLY REPORT* 📊")
        report.append(f"_{now.strftime('%d/%m/%Y %H:%M')}_")
        report.append("")
        
        total_balance = 0.0
        total_pnl = 0.0
        
        # 1. Strategy Performance
        for strat_id, strat in strategies.items():
            w = strat.wallet
            
            # ROI Calc
            roi = w.get_annualized_roi() # Returns float percentage
            
            # Win Rate
            wins = len([t for t in w.trades_history if t['final_pnl'] >= 0])
            total_closed = len(w.trades_history)
            wr = (wins / total_closed * 100) if total_closed > 0 else 0.0
            
            # PnL
            strat_pnl = sum([t['final_pnl'] for t in w.trades_history])
            
            total_balance += w.balance_eur
            total_pnl += strat_pnl
            
            report.append(f"🔹 *{strat_id}*")
            report.append(f"   💰 Bal: `{w.balance_eur:.2f}€`")
            report.append(f"   📈 PnL: `{strat_pnl:+.2f}€`")
            report.append(f"   🏆 WR: `{wr:.1f}%` ({wins}/{total_closed})")
            report.append(f"   🚀 ROI: `{roi:.1f}%`")
            
            # Active Ops Count
            report.append(f"   ⚡ Active: {len(w.positions)}")
            report.append("")

        # 2. Activity Last Hour
        report.append("🕒 *Activity (Last 60m)*")
        
        activity_found = False
        time_threshold = now.timestamp() - 3600
        
        for strat_id, strat in strategies.items():
            # Check History
            recent_closes = [t for t in strat.wallet.trades_history if t.get('close_time', 0) > time_threshold]
            for t in recent_closes:
                activity_found = True
                res = "✅CYAN" if t['final_pnl'] >= 0 else "dX" # Emoji choice
                res_icon = "🟢" if t['final_pnl'] >= 0 else "🔴"
                report.append(f"{res_icon} [{strat_id}] {t['symbol']} {t['type']} : `{t['final_pnl']:+.2f}€`")
                
            # Check New Opens? (Optional, wallet doesn't easily store open time in history until closed, but positions have entry_time)
            # Iterate Open Positions
            recent_opens = [p for p in strat.wallet.positions.values() if p['entry_time'] > time_threshold]
            for p in recent_opens:
                activity_found = True
                report.append(f"🆕 [{strat_id}] {p['symbol']} {p['type']} Opened")

        if not activity_found:
            report.append("_No closed trades or new entries._")

        return "\n".join(report)

