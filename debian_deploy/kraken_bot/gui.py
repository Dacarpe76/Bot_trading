import sys
import asyncio
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QPushButton, QFrame, QTabWidget, QDialog, QComboBox, QSplitter,
                             QFormLayout, QDoubleSpinBox, QSpinBox, QDialogButtonBox)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence
import datetime
import time
import pyqtgraph as pg

from kraken_bot import config
from kraken_bot.connector import KrakenConnector
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot.processor import StrategyProcessor
from kraken_bot.reporter import TelegramReporter

# --- LOGGING ---
class QtLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

# --- WORKER THREAD ---
class WorkerThread(QThread):
    log_signal = pyqtSignal(str)
    monitor_signal = pyqtSignal(list)
    operations_signal = pyqtSignal(list)
    history_signal = pyqtSignal(list)
    dashboard_signal = pyqtSignal(list) # New: [{id, balance, pnl, open_pos, win_rate}]
    
    def __init__(self):
        super().__init__()
        self.loop = None
        self.running = True
        
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.log_signal.emit("Initializing System (Multi-Strategy)...")
            queue = asyncio.Queue()
            
            # Connector
            connector = KrakenConnector(
                symbols=config.SYMBOLS,
                channels=["trade"],
                output_queue=queue
            )
            
            # Processor (Manages Strategies & Wallets)
            self.strategy = StrategyProcessor()
            
            # Callbacks
            self.strategy.on_monitor_update = self.handle_monitor_update
            
            # Reporter
            self.reporter = TelegramReporter()
            self.reporter.send_message("🤖 *TRH Bot Started* \nSystem is Online.")
            self.last_hour_check = datetime.datetime.now().hour
            
            # Tasks
            self.loop.create_task(self.run_reporter_loop())
            self.loop.create_task(connector.connect())
            self.loop.create_task(self.strategy.process_queue(queue))
            
            self.log_signal.emit("Backend Started. Connecting to Kraken...")
            self.loop.run_forever()
        except Exception as e:
            err_msg = f"CRITICAL WORKER ERROR: {e}"
            print(err_msg) # Force stdout
            import traceback
            traceback.print_exc()
            self.log_signal.emit(err_msg)

    async def run_reporter_loop(self):
        """Checks every minute if a new hour has started."""
        while self.running:
            now = datetime.datetime.now()
            if now.hour != self.last_hour_check:
                # New Hour!
                self.last_hour_check = now.hour
                self.log_signal.emit("Sending Hourly Telegram Report...")
                
                try:
                    report_text = self.reporter.generate_report(self.strategy.strategies)
                    # Run in executor to avoid blocking loop? requests is sync.
                    # Since it takes ~100ms, strictly speaking yes, but for simplicity:
                    await self.loop.run_in_executor(None, self.reporter.send_message, report_text)
                except Exception as e:
                    self.log_signal.emit(f"Report Failed: {e}")
            
            await asyncio.sleep(60)

    def handle_monitor_update(self, monitor_data):
        self.monitor_signal.emit(monitor_data)
        
        # Sync Operations & Dashboard (Aggregation)
        prices = {d['symbol']: d['price'] for d in monitor_data}
        
        all_ops = []
        all_hist = []
        dash_data = []
        
        for strat_id, strat in self.strategy.strategies.items():
            w = strat.wallet
            
            # 1. Dashboard Data
            # Calc Win Rate / Stats
            wins_list = [t for t in w.trades_history if t['final_pnl'] >= 0]
            wins = len(wins_list)
            total = len(w.trades_history)
            losses = total - wins
            wr = (wins / total * 100) if total > 0 else 0.0
            
            roi = w.get_annualized_roi()
            
            # PnL Total
            total_pnl = sum([t['final_pnl'] for t in w.trades_history])
            
            # Active Pos Count
            active_count = len(w.positions)
            
            dash_data.append({
                'id': strat_id,
                'balance': w.balance_eur,
                'equity': w.get_portfolio_value(prices),
                'pnl_total': total_pnl,
                'open_pos': active_count,
                'win_rate': wr,
                'roi_annual': roi,
                'total_ops': total,
                'wins': wins,
                'losses': losses,
                'paused': strat.paused
            })
            
            # 2. Operations
            ops = w.get_positions_status(prices)
            for op in ops:
                op['strategy_id'] = strat_id # Tag
                all_ops.append(op)
                
            # 3. History
            hist = w.get_history()
            for h in hist:
                h['strategy_id'] = strat_id
                all_hist.append(h)
        
        # Sort History by Close Time (newest first)
        # Assuming get_history returns reversed list (newest first), but we are merging 4 lists.
        # Need to resort.
        all_hist.sort(key=lambda x: x.get('close_time', x['entry_time']), reverse=True)
        
        
        # Global Equity Calc
        total_global_equity = sum([d['equity'] for d in dash_data])
        
        # Update Header Status with Global Equity
        # "System: ONLINE (Kraken Multi-Strategy) | Global Eq: 3000.00 EUR"
        base_msg = "System: ONLINE (Kraken Multi-Strategy)"
        
        # We can update the label from here using signal or just emit to update_dashboard?
        # Worker emits to 'monitor_signal', 'dashboard_signal' etc.
        # Let's add 'global_equity' to dashboard data or send a separate signal?
        # Simplest: Append it to the dashboard_signal payload or emitted separately.
        # Let's modify 'dashboard_signal' to send a tuple (data_list, global_equity) or just rely on MainWindow to sum it up.
        # MainWindow.update_dashboard receives 'data'. Better to let MainWindow sum it up from 'data' to keep Worker simple?
        # Actually Worker already calculated 'dash_data'.
        
        # Let's just pass raw list and let MainWindow sum it.
        self.dashboard_signal.emit(dash_data)
        self.operations_signal.emit(all_ops)
        self.history_signal.emit(all_hist)

    def stop(self):
        if self.loop: self.loop.stop()
        self.running = False


# --- CHART AXIS UTILS ---
class DateAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        strns = []
        for x in values:
            try:
                dt = datetime.datetime.fromtimestamp(x)
                if spacing < 3600: # Less than an hour
                     strns.append(dt.strftime("%H:%M:%S"))
                elif spacing < 3600 * 24: # Less than a day
                     strns.append(dt.strftime("%H:%M"))
                else:
                     strns.append(dt.strftime("%d/%m %H:%M"))
            except ValueError:
                strns.append("")
        return strns

# --- CHART DIALOG ---
class ChartDialog(QDialog):
    def __init__(self, trade_id, symbol, entry_price, entry_time, candles, parent=None):
        super().__init__(parent)
        self.trade_id = trade_id
        self.setWindowTitle(f"Trade #{trade_id} - {symbol}")
        self.resize(800, 600)
        self.layout = QVBoxLayout(self)
        
        # Plot Setup
        date_axis = DateAxisItem(orientation='bottom')
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': date_axis})
        self.plot_widget.setBackground('#121212')
        self.plot_widget.setTitle(f"{symbol} Price Action", color='#E0E0E0')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.layout.addWidget(self.plot_widget)
        
        self.entry_price = entry_price
        self.ts_line = None
        
        # Prepare Data
        self.times = []
        self.closes = []
        
        for c in candles:
            # timestamp is datetime object
            t = c['timestamp'].timestamp()
            if t >= entry_time:
                self.times.append(t)
                self.closes.append(c['close'])
                
        # Handle case where no history yet
        if not self.times:
             self.times.append(entry_time)
             self.closes.append(entry_price)

        self.curve = self.plot_widget.plot(self.times, self.closes, pen=pg.mkPen('#00FF00', width=2))
        self.plot_widget.addLine(y=entry_price, pen=pg.mkPen('#FFFFFF', style=Qt.PenStyle.DashLine), label="Entry")
        
    def update_state(self, current_price, current_time, ts_price, ts_active):
        self.times.append(current_time)
        self.closes.append(current_price)
        self.curve.setData(self.times, self.closes)
        
        if ts_active and ts_price > 0:
            if self.ts_line:
                self.plot_widget.removeItem(self.ts_line)
            pen = pg.mkPen('#FFA500', width=1, style=Qt.PenStyle.DashLine)
            self.ts_line = self.plot_widget.addLine(y=ts_price, pen=pen)

# --- MAIN WINDOW ---
class StrategyConfigDialog(QDialog):
    def __init__(self, strategy, parent=None):
        super().__init__(parent)
        self.strategy = strategy
        self.setWindowTitle(f"Config: {strategy.id}")
        self.setModal(True)
        self.setMinimumWidth(300)
        
        layout = QFormLayout()
        self.inputs = {}
        
        # Parameter Translation Mapping
        self.param_labels = {
            'vrel_min': "Volumen Relativo Mínimo",
            'err_min': "Ratio Esfuerzo/Result Mín",
            'rsi_long_max': "RSI Máximo (Largos)",
            'rsi_short_min': "RSI Mínimo (Cortos)",
            'adx_min': "ADX Mínimo",
            'wick_min': "Ratio Mecha/Cuerpo Mín",
            'ts_atr_mult': "Multiplicador ATR (Trailing)",
            'tsl_pct': "Trailing Stop (%)",
            'climax_vrel': "Volumen Relativo (Clímax)",
            'climax_rsi_long': "RSI Largo (Clímax)",
            'climax_rsi_short': "RSI Corto (Clímax)",
            'momentum_mfi_limit': "Límite MFI (Momentum)",
            'momentum_adx_min': "ADX Mín (Momentum)",
            'momentum_ts_pct': "Trailing Stop Momentum (%)",
            'profit_activation_eur': "Activación Beneficio (€)",
            'profit_preserve_eur': "Beneficio Asegurado (€)",
            'profit_step_eur': "Paso del Trailing (€)",
            'dca_step_pct': "Distancia DCA (%)",
            'max_dca_count': "Máx. Recompras DCA",
            'profit_initial_stop_eur': "Stop Inicial Ganador (€)",
            'profit_trailing_dist_eur': "Distancia Trailing (€)"
        }
        
        for key, value in self.strategy.params.items():
            # Get Descriptive Label
            label_text = self.param_labels.get(key, key)
            lbl = QLabel(label_text)
            # High Visibility Style: Cyan, Bold, Slightly Larger
            lbl.setStyleSheet("color: #00FFFF; font-weight: bold; font-size: 11pt; border-bottom: 1px solid #444; margin-bottom: 2px;")
            
            # Create input based on type
            if isinstance(value, float):
                inp = QDoubleSpinBox()
                inp.setDecimals(4)
                inp.setRange(0.0, 1000.0) # Assume positive params
                inp.setValue(value)
                # Specific ranges
                if "pct" in key or "max" in key or "min" in key:
                     inp.setSingleStep(0.01)
                else:
                     inp.setSingleStep(0.1)
                self.inputs[key] = inp
                layout.addRow(lbl, inp)
            elif isinstance(value, int):
                inp = QSpinBox()
                inp.setRange(0, 10000)
                inp.setValue(value)
                self.inputs[key] = inp
                layout.addRow(lbl, inp)
                
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.save_params)
        btn_box.rejected.connect(self.reject)
        
        layout.addRow(btn_box)
        self.setLayout(layout)
        
    def save_params(self):
        for key, inp in self.inputs.items():
            self.strategy.params[key] = inp.value()
        logging.info(f"Updated params for {self.strategy.id}: {self.strategy.params}")
        self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TRH Bot - MultiCoin Research Mode")
        self.active_chart = None
        self.previous_prices = {}
        self.resize(1200, 800)
        
        # Dark Mode Style
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; color: #E0E0E0; }
            QLabel { color: #E0E0E0; font-family: Consolas; }
            QTableWidget { 
                background-color: #1E1E1E; color: #E0E0E0; 
                gridline-color: #333; border: 1px solid #333;
                font-family: Consolas; font-size: 10pt;
            }
            QHeaderView::section { background-color: #2C2C2C; color: #AAA; border: 1px solid #333; padding: 4px; }
            QTextEdit { background-color: #000; color: #0F0; font-family: Consolas; border: 1px solid #333; }
            QPushButton { background-color: #333; color: #FFF; border: 1px solid #555; padding: 5px; }
            QPushButton:hover { background-color: #444; }
            QTabWidget::pane { border: 1px solid #333; }
            QTabBar::tab { background: #2C2C2C; color: #AAA; padding: 8px; margin-right: 2px; }
            QTabBar::tab:selected { background: #3E3E3E; color: #FFF; border-bottom: 2px solid #007ACC; }
        """)

        # Main Widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # === SPLITTER MAIN (Vertical) ===
        splitter_main = QSplitter(Qt.Orientation.Vertical)
        
        # --- TOP: SYSTEM DASHBOARD ---
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("background-color: #252526; border-radius: 5px;")
        header_layout = QVBoxLayout(self.header_frame)
        
        # Top Row: Status & Buttons
        top_row = QHBoxLayout()
        self.lbl_status = QLabel("System: CONNECTING...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #FFA500;")
        
        self.btn_panic = QPushButton("PANIC: CLOSE ALL")
        self.btn_panic.setStyleSheet("background-color: #FF0000; color: white; font-weight: bold; padding: 5px;")
        self.btn_panic.clicked.connect(self.panic_close_all)
        
        top_row.addWidget(self.lbl_status)
        top_row.addStretch()
        top_row.addWidget(self.btn_panic)
        header_layout.addLayout(top_row)
        
        # Dashboard Table
        self.table_dashboard = QTableWidget()
        self.table_dashboard.setColumnCount(10) # Added ROI, OPS, W/L
        self.table_dashboard.setHorizontalHeaderLabels(["STRAT", "BALANCE", "EQUITY", "PNL", "ROI (Yr)", "OPS", "W-L", "WIN %", "ACTIVE", "CONTROL"])
        self.table_dashboard.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_dashboard.verticalHeader().setVisible(False)
        self.table_dashboard.setStyleSheet("font-size: 10pt;") # Explicit 10pt
        self.table_dashboard.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_dashboard.setFixedHeight(220) # Fits ~6 rows + Header
        header_layout.addWidget(self.table_dashboard)
        
        splitter_main.addWidget(self.header_frame)
        
        # --- MIDDLE: SPLITTER (Horizontal) ---
        splitter_middle = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT: PRICE MONITOR WIDGET
        wid_monitor = QWidget()
        layout_monitor = QVBoxLayout(wid_monitor)
        layout_monitor.setContentsMargins(0,0,0,0)
        
        lbl_mon = QLabel("MARKET MONITOR (Top 10)")
        lbl_mon.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        layout_monitor.addWidget(lbl_mon)
        
        self.table_monitor = QTableWidget()
        self.table_monitor.setColumnCount(6)
        self.table_monitor.setHorizontalHeaderLabels(["Symbol", "Price", "RSI", "Vol", "Vrel", "ERR"])
        self.table_monitor.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_monitor.verticalHeader().setVisible(False)
        layout_monitor.addWidget(self.table_monitor)
        
        splitter_middle.addWidget(wid_monitor)
        
        # RIGHT: OPERATIONS WIDGET
        wid_ops = QWidget()
        layout_ops = QVBoxLayout(wid_ops)
        layout_ops.setContentsMargins(0,0,0,0)
        
        # Header Row for Ops
        ops_header = QHBoxLayout()
        lbl_ops = QLabel("ACTIVE OPERATIONS")
        lbl_ops.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        ops_header.addWidget(lbl_ops)
        ops_header.addStretch()
        
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["All Strategies", "Aggressive", "AggrCent", "NetScalp"])
        self.combo_filter.currentTextChanged.connect(self.on_filter_changed)
        ops_header.addWidget(QLabel("Filter:"))
        ops_header.addWidget(self.combo_filter)
        
        layout_ops.addLayout(ops_header)
        
        self.table_ops = QTableWidget()
        self.table_ops.setColumnCount(11) 
        self.table_ops.setHorizontalHeaderLabels(["Strat", "ID", "Symbol", "Type", "PnL", "Fees", "Invested", "TS Stat", "TS Price", "Graph", "Close"])
        self.table_ops.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_ops.verticalHeader().setVisible(False)
        layout_ops.addWidget(self.table_ops)
        
        splitter_middle.addWidget(wid_ops)
        
        # Initial Sizes for Middle (1:2 ratio roughly)
        splitter_middle.setStretchFactor(0, 1)
        splitter_middle.setStretchFactor(1, 2)
        
        splitter_main.addWidget(splitter_middle)
        
        # --- BOTTOM: TABS (LOGS & HISTORY) ---
        self.tabs = QTabWidget()
        
        # Tab 1: System Logs
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.tabs.addTab(self.log_view, "System Logs")
        
        # Tab 2: Trade History
        self.table_history = QTableWidget()
        self.table_history.setColumnCount(9) 
        self.table_history.setHorizontalHeaderLabels(["Strat", "ID", "Symbol", "Type", "Open Time", "Close Time", "Fees", "PnL", "Result"])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_history.verticalHeader().setVisible(False)
        self.tabs.addTab(self.table_history, "Trade History")
        
        splitter_main.addWidget(self.tabs)
        
        # Add Splitter to Main Layout
        main_layout.addWidget(splitter_main)
        
        # --- WORKER ---
        self.worker = WorkerThread()
        self.worker.log_signal.connect(self.append_log)
        self.worker.monitor_signal.connect(self.update_monitor)
        self.worker.operations_signal.connect(self.update_operations)
        self.worker.history_signal.connect(self.update_history)
        self.worker.dashboard_signal.connect(self.update_dashboard)
        
        # Setup Logging
        log_handler = QtLogHandler(self.worker.log_signal)
        log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)
        
        # Configure Dashboard Table Columns (Resize Modes)
        self.table_dashboard.setColumnCount(10) 
        self.table_dashboard.setHorizontalHeaderLabels(["STRAT", "BALANCE", "EQUITY", "PNL", "ROI (Yr)", "OPS", "W-L", "WIN %", "ACTIVE", "CONTROL"])
        header = self.table_dashboard.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # STRAT
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Balance
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Equity
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # PnL
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # ROI
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # OPS
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # W-L
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents) # WIN %
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents) # ACTIVE
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed) # CONTROL
        self.table_dashboard.setColumnWidth(9, 120)

        # Enable Copy/Paste
        self.enable_copy(self.table_monitor)
        self.enable_copy(self.table_ops)
        self.enable_copy(self.table_history)
        self.enable_copy(self.table_dashboard)
        
        self.worker.start()

    def append_log(self, msg):
        self.log_view.append(msg)
        if "Connected" in msg:
            self.lbl_status.setText("System: ONLINE (Kraken Multi-Strategy)")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #00FF00;")

    def update_dashboard(self, data):
        # data comes from worker.dashboard_signal (list of dicts)
        self.table_dashboard.setRowCount(len(data))
        
        total_global_equity = 0.0
        
        for r, d in enumerate(data):
             # ["ID", "Balance", "Equity", "PnL", "Open Pos", "Win Rate", "Accion"]
             self.table_dashboard.setItem(r, 0, QTableWidgetItem(d['id']))
             self.table_dashboard.setItem(r, 1, QTableWidgetItem(f"{d['balance']:.2f}€"))
             self.table_dashboard.setItem(r, 2, QTableWidgetItem(f"{d['equity']:.2f}€"))
             
             total_global_equity += d['equity']
             
             pnl_item = QTableWidgetItem(f"{d['pnl_total']:.2f}€")
             if d['pnl_total'] >= 0: pnl_item.setForeground(QColor("#00FF00"))
             else: pnl_item.setForeground(QColor("#FF0000"))
             self.table_dashboard.setItem(r, 3, pnl_item)
             
             # ROI
             roi_item = QTableWidgetItem(f"{d['roi_annual']:.1f}%")
             if d['roi_annual'] >= 0: roi_item.setForeground(QColor("#00FF00"))
             else: roi_item.setForeground(QColor("#FF0000"))
             self.table_dashboard.setItem(r, 4, roi_item)

             self.table_dashboard.setItem(r, 5, QTableWidgetItem(str(d['total_ops'])))
             self.table_dashboard.setItem(r, 6, QTableWidgetItem(f"{d['wins']}-{d['losses']}"))
             
             self.table_dashboard.setItem(r, 7, QTableWidgetItem(f"{d['win_rate']:.1f}%"))
             self.table_dashboard.setItem(r, 8, QTableWidgetItem(str(d['open_pos'])))
             
             # Actions (Double Button: Pause | Config)
             widget = QWidget()
             layout = QHBoxLayout()
             layout.setContentsMargins(0,0,0,0)
             layout.setSpacing(2)
             
             # Pause Button
             btn_pause = QPushButton("⏸" if not d['paused'] else "▶")
             btn_pause.setFixedSize(30, 25)
             btn_pause.clicked.connect(lambda checked, sid=d['id']: self.toggle_pause(sid))
             
             # Config Button
             btn_conf = QPushButton("⚙")
             btn_conf.setFixedSize(30, 25)
             btn_conf.clicked.connect(lambda checked, sid=d['id']: self.open_config(sid))
             
             layout.addWidget(btn_pause)
             layout.addWidget(btn_conf)
             
             widget.setLayout(layout)
             self.table_dashboard.setCellWidget(r, 9, widget)
             
        # Update Global Header Label
        self.lbl_status.setText(f"System: ONLINE | Global Eq: {total_global_equity:.2f} EUR")
        if len(data) > 0 and total_global_equity >= (len(data) * config.INITIAL_BALANCE):
             self.lbl_status.setStyleSheet("font-weight: bold; color: #00FF00; font-size: 12pt;")
        else:
             self.lbl_status.setStyleSheet("font-weight: bold; color: #FFA500; font-size: 12pt;")

    def open_config(self, strat_id):
        if not self.worker: return
        strat = self.worker.strategy.strategies.get(strat_id)
        if strat:
            dlg = StrategyConfigDialog(strat, self)
            dlg.exec()

    def toggle_pause(self, strat_id):
        if not self.worker: return
        strat = self.worker.strategy.strategies.get(strat_id)
        if strat:
            strat.paused = not strat.paused
            logging.info(f"Strategy {strat_id} PAUSED status toggled to: {strat.paused}")

    def enable_copy(self, table):
        """Enables Ctrl+C copy functionality on a QTableWidget."""
        def handle_key_press(event):
            if event.matches(QKeySequence.StandardKey.Copy) or (event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C):
                selection = table.selectedRanges()
                if selection:
                    rows = sorted(list(set(range(selection[0].topRow(), selection[0].bottomRow() + 1))))
                    columns = sorted(list(set(range(selection[0].leftColumn(), selection[0].rightColumn() + 1))))
                    
                    text_str = ""
                    for r in rows:
                        row_data = []
                        for c in columns:
                            item = table.item(r, c)
                            if item: row_data.append(item.text())
                            else: row_data.append("")
                        text_str += "\t".join(row_data) + "\n"
                        
                    QApplication.clipboard().setText(text_str)
                    return
            
            # Pass to original keyPressEvent (monkey patch style)
            # Since we replaced the instance method, 'QTableWidget.keyPressEvent' is unbound.
            # We call it passing 'table' (self) and 'event'.
            QTableWidget.keyPressEvent(table, event)

        table.keyPressEvent = handle_key_press

    def update_monitor(self, data):
        self.table_monitor.setRowCount(len(data))
        for r, row in enumerate(data):
            symbol = row['symbol'].split('/')[0]
            price = row['price']
            
            self.table_monitor.setItem(r, 0, QTableWidgetItem(symbol))
            
            price_item = QTableWidgetItem(f"{price:.4f}")
            
            # Color Logic
            prev_price = self.previous_prices.get(row['symbol'])
            if prev_price is not None:
                if price > prev_price:
                    price_item.setForeground(QColor("#00FF00")) # Green
                elif price < prev_price:
                    price_item.setForeground(QColor("#FF0000")) # Red
                else:
                    price_item.setForeground(QColor("#FFFFFF")) # White
            else:
                price_item.setForeground(QColor("#FFFFFF")) # White (First tick)
            
            self.previous_prices[row['symbol']] = price
            
            self.table_monitor.setItem(r, 1, price_item)
            
            rsi_item = QTableWidgetItem(f"{row.get('rsi',0):.1f}")
            rsi_val = row.get('rsi', 0)
            if rsi_val < config.RSI_OVERSOLD: rsi_item.setForeground(QColor("#00FF00"))
            elif rsi_val > config.RSI_OVERBOUGHT: rsi_item.setForeground(QColor("#FF0000"))
            self.table_monitor.setItem(r, 2, rsi_item)
            
            self.table_monitor.setItem(r, 3, QTableWidgetItem(f"{row.get('volume',0):.2f}"))
            
            vrel_item = QTableWidgetItem(f"{row.get('vrel',0):.2f}")
            if row.get('vrel',0) > config.VREL_THRESHOLD: vrel_item.setForeground(QColor("#FFA500"))
            self.table_monitor.setItem(r, 4, vrel_item)
            
            err_item = QTableWidgetItem(f"{row.get('err',0):.2f}")
            if row.get('err',0) > config.ERR_THRESHOLD: err_item.setForeground(QColor("#FFA500"))
            self.table_monitor.setItem(r, 5, err_item)

    def on_filter_changed(self, text):
        # Trigger update if we have data
        if hasattr(self, 'last_ops_data'):
            self.update_operations(self.last_ops_data)

    def update_operations(self, data):
        self.last_ops_data = data # Store for filter updates
        
        # Filter Data
        filter_strat = self.combo_filter.currentText()
        filtered_data = []
        
        for pos in data:
            strat_id = pos.get('strategy_id', '??')
            if filter_strat == "All Strategies" or strat_id == filter_strat:
                filtered_data.append(pos)
        
        # Sort by PnL (Highest Profit First)
        filtered_data.sort(key=lambda x: x.get('pnl_val', 0.0), reverse=True)
                
        self.table_ops.setRowCount(len(filtered_data))
        
        # Removed legacy capital usage updates (now in Dashboard)

        for r, pos in enumerate(filtered_data):
            # ["Strat", "ID", "Symbol", "Type", "PnL", "Fees", "DCA#", "TS Stat", "TS Price", "Graph", "Close"]
            strat_id = pos.get('strategy_id', '??')
            self.table_ops.setItem(r, 0, QTableWidgetItem(strat_id))
            
            self.table_ops.setItem(r, 1, QTableWidgetItem(str(pos['id'])))
            
            sym = pos.get('symbol', '???') 
            self.table_ops.setItem(r, 2, QTableWidgetItem(sym))
            
            type_item = QTableWidgetItem(pos['type'])
            if pos['type'] == 'LONG': type_item.setForeground(QColor("#00FF00"))
            else: type_item.setForeground(QColor("#FF0000"))
            self.table_ops.setItem(r, 3, type_item)
            
            pnl_val = pos.get('pnl_val', 0.0)
            pnl_pct = pos.get('pnl_pct', 0.0)
            pnl_str = f"{pnl_val:+.2f}€ ({pnl_pct:+.2f}%)"
            pnl_item = QTableWidgetItem(pnl_str)
            
            # Color Logic
            if pnl_val < 0:
                pnl_item.setForeground(QColor("#FF0000")) 
            elif pnl_pct < 0:
                pnl_item.setForeground(QColor("#FFA500")) 
            else:
                pnl_item.setForeground(QColor("#00FF00")) 
                
            self.table_ops.setItem(r, 4, pnl_item)
            
            # Fees
            fees = pos.get('fees_eur', 0.0)
            self.table_ops.setItem(r, 5, QTableWidgetItem(f"{fees:.2f}€"))
            
            # Invested Amount instead of DCA#
            invested = pos.get('margin', 0.0)
            self.table_ops.setItem(r, 6, QTableWidgetItem(f"{invested:.2f}€"))
            
            # TS Status
            ts_stat = pos.get('ts_status', 'WAIT')
            stat_item = QTableWidgetItem(ts_stat)
            if "ACTIVE" in ts_stat: stat_item.setForeground(QColor("#00FF00"))
            else: stat_item.setForeground(QColor("#FFA500"))
            self.table_ops.setItem(r, 7, stat_item)
            
            # TS Price
            ts_price = pos.get('ts_price', 0.0)
            self.table_ops.setItem(r, 8, QTableWidgetItem(f"{ts_price:.4f}"))
            
            # Graph Button
            btn_graph = QPushButton("GRAPH")
            btn_graph.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold;")
            btn_graph.clicked.connect(lambda checked, pid=pos['id'], sid=strat_id, s=sym: self.open_chart(pid, sid, s))
            self.table_ops.setCellWidget(r, 9, btn_graph)
            
            # Action Button
            btn_close = QPushButton("CLOSE")
            btn_close.clicked.connect(lambda checked, pid=pos['id'], sid=strat_id, pprice=pos.get('mark_price', 0.0): self.manual_close(pid, sid, pprice))
            btn_close.setStyleSheet("background-color: #AA0000; color: white; font-weight: bold;")
            self.table_ops.setCellWidget(r, 10, btn_close)

            # Update Active Chart if Open
            if self.active_chart and self.active_chart.isVisible() and self.active_chart.trade_id == pos['id']:
                 # Check Strat ID too if possible, but ChartDialog doesn't store it yet. 
                 # Currently we assume ID + Symbol?
                 # If ID collision, checking symbol helps?
                 # Better: Add Strat ID to ChartDialog.
                 pass

    def update_history(self, history):
        # history = list of closed trade dicts (Already unified)
        self.table_history.setRowCount(len(history))

        for r, trade in enumerate(history):
             # ["Strat", "ID", "Symbol", "Type", "Open Time", "Close Time", "Fees", "PnL", "Result"]
             
             strat = trade.get('strategy_id', '?')
             self.table_history.setItem(r, 0, QTableWidgetItem(strat))
             
             tid = str(trade.get('id', 'OLD')) 
             self.table_history.setItem(r, 1, QTableWidgetItem(tid))
             self.table_history.setItem(r, 2, QTableWidgetItem(trade['symbol']))
             
             type_item = QTableWidgetItem(trade['type'])
             if trade['type'] == 'LONG': type_item.setForeground(QColor("#00FF00"))
             else: type_item.setForeground(QColor("#FF0000"))
             self.table_history.setItem(r, 3, type_item)
             
             open_t = datetime.datetime.fromtimestamp(trade['entry_time']).strftime('%d/%m %H:%M')
             self.table_history.setItem(r, 4, QTableWidgetItem(open_t))
             
             close_t = datetime.datetime.fromtimestamp(trade.get('close_time',0)).strftime('%d/%m %H:%M')
             self.table_history.setItem(r, 5, QTableWidgetItem(close_t))
             
             fees = trade.get('final_fees', 0.0)
             self.table_history.setItem(r, 6, QTableWidgetItem(f"{fees:.2f}€"))
             
             pnl = trade.get('final_pnl', 0.0)
             pnl_item = QTableWidgetItem(f"{pnl:+.2f} EUR")
             if pnl >= 0: pnl_item.setForeground(QColor("#00FF00"))
             else: pnl_item.setForeground(QColor("#FF0000"))
             self.table_history.setItem(r, 7, pnl_item)
             
             res_str = "WIN" if pnl >= 0 else "LOSS"
             self.table_history.setItem(r, 8, QTableWidgetItem(res_str))

    def manual_close(self, trade_id, strat_id, price):
        if price <= 0:
             logging.warning("Cannot close: Price unknown")
             return
        logging.info(f"MANUAL CLOSE REQUEST: [{strat_id}] #{trade_id} @ {price}")
        
        strat = self.worker.strategy.strategies.get(strat_id)
        if strat and strat.wallet:
            success = strat.wallet.close_position(trade_id, price)
            if success:
                 logging.info(f"Manual Close [{strat_id}] #{trade_id} SUCCESS.")
            else:
                 logging.warning(f"Manual Close [{strat_id}] #{trade_id} FAILED.")
        else:
             logging.error(f"Strategy {strat_id} not found.")

    def panic_close_all(self):
        # Iterate all strategies
        logging.warning("!!! GLOBAL PANIC CLOSE TRIGGERED !!!")
        
        # Need prices. StrategyProcessor has market_state.
        prices = {}
        for sym, state in self.worker.strategy.market_state.items():
             if state['current_candle']:
                 prices[sym] = state['current_candle']['close']
             elif state['candles']:
                 prices[sym] = state['candles'][-1]['close']
        
        if not prices:
             logging.warning("Panic Close: No prices available yet!")
             return

        for strat_id, strat in self.worker.strategy.strategies.items():
             strat.wallet.close_all_positions(prices)
        
        logging.info("Panic Close Executed across all strategies.")

    def open_chart(self, trade_id, strat_id, symbol):
        if not self.worker: return
        
        strat = self.worker.strategy.strategies.get(strat_id)
        if not strat: return
        
        if trade_id not in strat.wallet.positions:
             return
             
        pos = strat.wallet.positions[trade_id]
        entry_time = pos['entry_time']
        entry_price = pos['entry_price']
        
        state = self.worker.strategy.market_state.get(symbol, {})
        candles = state.get('candles', [])
        
        if self.active_chart:
            self.active_chart.close()
            
        self.active_chart = ChartDialog(trade_id, symbol, entry_price, entry_time, candles, self)
        self.active_chart.show()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
