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
            logging.info("Telegram config missing. Skipping report.")
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
            
            strat_name = getattr(strat, 'name', strat_id)
            report.append(f"🔹 *{strat_name}*")
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
                strat_name = getattr(strat, 'name', strat_id)
                report.append(f"{res_icon} [{strat_name}] {t['symbol']} {t['type']} : `{t['final_pnl']:+.2f}€`")
                
            # Check New Opens? (Optional, wallet doesn't easily store open time in history until closed, but positions have entry_time)
            # Iterate Open Positions
            recent_opens = [p for p in strat.wallet.positions.values() if p['entry_time'] > time_threshold]
            for p in recent_opens:
                activity_found = True
                strat_name = getattr(strat, 'name', strat_id)
                report.append(f"🆕 [{strat_name}] {p['symbol']} {p['type']} Opened")

        if not activity_found:
            report.append("_No closed trades or new entries._")

        return "\n".join(report)

    def generate_daily_summary(self, strategies):
        """
        Generates a 24h summary report for all strategies.
        Includes performance, open operations with duration, and capital usage.
        """
        now = datetime.datetime.now()
        timestamp_now = now.timestamp()
        report = []
        report.append(f"☀️ *DAILY STRATEGY SUMMARY* ☀️")
        report.append(f"_{now.strftime('%d/%m/%Y %H:%M')}_")
        
        try:
            import requests
            public_ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
            report.append(f"🌐 Server IP: `{public_ip}`")
        except Exception as e:
            logging.info(f"Could not fetch public IP: {e}")
            report.append(f"🌐 Server IP: `Unknown`")
            
        report.append("")

        total_equity = 0.0
        total_margin = 0.0
        
        # 1. Strategy Performance (Last 24h)
        report.append("📈 *24h Performance*")
        time_24h = timestamp_now - 86400
        
        for strat_id, strat in strategies.items():
            w = strat.wallet
            recent_trades = [t for t in w.trades_history if t.get('close_time', 0) > time_24h]
            pnl_24h = sum([t['final_pnl'] for t in recent_trades])
            wins_24h = len([t for t in recent_trades if t['final_pnl'] >= 0])
            
            # Using current prices for equity calculation if available
            margin, equity, usage = w.get_capital_usage()
            total_equity += equity
            total_margin += margin
            
            strat_name = getattr(strat, 'name', strat_id)
            report.append(f"🔹 *{strat_name}*")
            report.append(f"   24h PnL: `{pnl_24h:+.2f}€` ({wins_24h}/{len(recent_trades)})")
            report.append(f"   Equity: `{equity:.2f}€` | Usage: `{usage*100:.1f}%`")
            report.append("")

        # 2. Open Operations & Duration
        report.append("🕒 *Open Operations*")
        open_ops_found = False
        
        for strat_id, strat in strategies.items():
            for t_id, pos in strat.wallet.positions.items():
                open_ops_found = True
                duration_sec = timestamp_now - pos['entry_time']
                
                # Format duration
                days = int(duration_sec // 86400)
                hours = int((duration_sec % 86400) // 3600)
                mins = int((duration_sec % 3600) // 60)
                
                dur_str = ""
                if days > 0: dur_str += f"{days}d "
                dur_str += f"{hours}h {mins}m"
                
                strat_name_ops = getattr(strat, 'name', strat_id)
                report.append(f"🔸 [{strat_name_ops}] {pos['symbol']} {pos['type']}")
                report.append(f"   Entry: `{pos['avg_price']:.4f}` | Time: `{dur_str}`")
        
        if not open_ops_found:
            report.append("_No open operations._")
        
        report.append("")

        # 3. Global Capital Status
        global_usage = (total_margin / total_equity) if total_equity > 0 else 0.0
        report.append("🚨 *Global Capital Status*")
        report.append(f"   Total Margin: `{total_margin:.2f}€`")
        report.append(f"   Total Equity: `{total_equity:.2f}€`")
        report.append(f"   Overall Usage: `{global_usage*100:.1f}%`")
        
        if global_usage > 0.35: # Close to 40% limit from config
            report.append("⚠️ *WARNING: Capital limit approaching!*")

        return "\n".join(report)

    def generate_technical_summary(self, strategies):
        """
        Generates a 24h technical summary report for all strategies.
        Format: Strategy: X cerradas (Y Long - Z short) (PnLong: +A.BB - PnShort: +C.DD) tiempo medio: HH:MM:SS
        """
        now = datetime.datetime.now()
        timestamp_now = now.timestamp()
        time_24h = timestamp_now - 86400
        
        report = []
        report.append(f"📋 *TECHNICAL SUMMARY (Last 24h)*")
        report.append(f"_{now.strftime('%d/%m/%Y %H:%M')}_")
        report.append("")

        for strat_id, strat in strategies.items():
            w = strat.wallet
            recent_trades = [t for t in w.trades_history if t.get('close_time', 0) > time_24h]
            
            if not recent_trades:
                continue

            closed_count = len(recent_trades)
            long_trades = [t for t in recent_trades if t['type'] == 'LONG']
            short_trades = [t for t in recent_trades if t['type'] == 'SHORT']
            
            pnl_long = sum([t['final_pnl'] for t in long_trades])
            pnl_short = sum([t['final_pnl'] for t in short_trades])
            
            # Duration calculation
            total_dur_sec = sum([t['close_time'] - t['entry_time'] for t in recent_trades])
            avg_dur_sec = total_dur_sec / closed_count if closed_count > 0 else 0
            
            # Realized Balance (Initial + All Realized PnL)
            total_realized_pnl = sum([t['final_pnl'] for t in w.trades_history])
            realized_balance = w.initial_capital + total_realized_pnl
            
            # Format duration: HH:MM:SS
            hours = int(avg_dur_sec // 3600)
            minutes = int((avg_dur_sec % 3600) // 60)
            seconds = int(avg_dur_sec % 60)
            dur_str = f"{hours}H {minutes}min {seconds}seg"
            
            strat_display = getattr(w, 'display_name', strat_id)
            
            line = (f"*{strat_display}*: {closed_count} cerradas "
                    f"({len(long_trades)} Long - {len(short_trades)} short) "
                    f"(PnLong: `{pnl_long:+.2f}€` - PnShort: `{pnl_short:+.2f}€`) "
                    f"tiempo medio: `{dur_str}` | Saldo: `{realized_balance:.2f}€`")
            report.append(line)

        if len(report) <= 3:
            report.append("_No se cerraron operaciones en las últimas 24h._")

        return "\n".join(report)

