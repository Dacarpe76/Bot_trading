import sys
import asyncio
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QPushButton, QFrame, QTabWidget, QDialog, QComboBox, QSplitter,
                             QFormLayout, QDoubleSpinBox, QSpinBox, QDialogButtonBox, QTreeWidget, QTreeWidgetItem)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence
import datetime
import time
import pyqtgraph as pg

from kraken_bot import config
from kraken_bot.connector import KrakenConnector
from kraken_bot.paper_wallet import PaperWallet
from kraken_bot.processor import StrategyProcessor
from kraken_bot.reporter import TelegramReporter

STRATEGY_DISPLAY_NAMES = {
    "Aggressive": "Agresivo (Scalping)",
    "AggrCent": "Agresivo (Centrado)",
    "NetScalp": "NetScalping (Red)",
    "RollingDCA": "Rolling DCA (Largo)",
    "Rol_dca_sh": "Rolling DCA (Corto)",
    "Rol_dca_sh_v2": "Rolling DCA Short V2",
    "Rol_dca_sh_v3": "Rolling DCA Short V3",
    "HybridElite": "Híbrido Élite",
    "TrendADX": "Tendencia ADX",
    "Cuchillo_caida": "Cuchillo Caída (Crash)"
}

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
    macro_signal = pyqtSignal(list) # New: [{name, active, equity, holdings, regime}]
    
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
            
            # Fetch History Explicitly
            self.log_signal.emit("Fetching Market History (This may take a moment)...")
            self.strategy.fetch_all_history()
            self.log_signal.emit("History Loaded. Starting Analysis...")
            
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
            
                except Exception as e:
                    self.log_signal.emit(f"Report Failed: {e}")
            
            # --- Periodic Macro Status Update (e.g. every 10s) ---
            if now.second % 10 == 0:
                 try:
                     if hasattr(self.strategy, 'get_aggregated_strategies_status'):
                         macro_statuses = self.strategy.get_aggregated_strategies_status()
                     else:
                         # Fallback for safety
                         macro_statuses = []
                     
                     if macro_statuses:
                         self.macro_signal.emit(macro_statuses)
                 except Exception as e:
                     # self.log_signal.emit(f"Macro Status error: {e}")
                     pass

            await asyncio.sleep(1) # More granular for second check

    def handle_monitor_update(self, monitor_data):
        # self.log_signal.emit(f"DEBUG: Monitor Update received ({len(monitor_data)} symbols)")
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
                'paused': strat.paused,
                'start_time': 0 # Placeholder, calc below
            })
            
            # Determine True Start Time (First Trade)
            all_times = []
            if w.trades_history:
                all_times.extend([t.get('entry_time', float('inf')) for t in w.trades_history])
            if w.positions:
                all_times.extend([p.get('entry_time', float('inf')) for p in w.positions.values()])
            
            if all_times:
                dash_data[-1]['start_time'] = min(all_times)
            else:
                 dash_data[-1]['start_time'] = 0
            
            # 2. Operations
            ops = w.get_positions_status(prices)
            
            # Active Stats
            active_wins = 0
            active_losses = 0
            for op in ops:
                op['strategy_id'] = strat_id # Tag
                all_ops.append(op)
                if op.get('pnl_val', 0.0) >= 0:
                    active_wins += 1
                else:
                    active_losses += 1
            
            # Update Dash Data with Active Split
            dash_data[-1]['active_wins'] = active_wins
            dash_data[-1]['active_losses'] = active_losses
                
            # 3. History
            hist = w.get_history()
            for h in hist:
                h['strategy_id'] = strat_id
                all_hist.append(h)
        
        # Sort History by Close Time (newest first)
        all_hist.sort(key=lambda x: x.get('close_time', x['entry_time']), reverse=True)
        
        # Dashboard Signal
        self.dashboard_signal.emit(dash_data)
        self.operations_signal.emit(all_ops)
        self.history_signal.emit(all_hist)

    def stop(self):
        if self.loop: self.loop.stop()
        self.running = False


# --- CUSTOM WIDGETS ---
class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        # Use UserRole for sorting if available
        v1 = self.data(Qt.ItemDataRole.UserRole)
        v2 = other.data(Qt.ItemDataRole.UserRole)
        
        if v1 is not None and v2 is not None:
             try:
                 return float(v1) < float(v2)
             except:
                 pass
        
        return super().__lt__(other)


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

# --- CONFIG DIALOG ---
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
            'profit_trailing_dist_eur': "Distancia Trailing (€)",
            'rsi_5m_entry': "RSI Entrada (5m - <40)",
            'rsi_5m_short': "RSI Short (5m - >60)",
            'base_size_eur': "Tamaño Base (€)",
            'dca_size_eur': "Tamaño DCA (€)",
            'max_exposure_eur': "Exposición Máxima (€)",
            'dca_min_distance_pct': "Distancia Mín. DCA (%)",
            'trailing_activation_pct': "Activación Trailing (%)",
            'trailing_distance_pct': "Distancia Trailing (%)",
            'max_concurrent': "Máx. Op. Simultáneas"
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

# --- MAIN WINDOW ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TRH Bot - MultiCoin Research Mode")
        self.active_chart = None
        self.previous_prices = {}
        self.resize(1400, 900) # Increased size for Tabs
        
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
        
        # === TAB WIDGET ===
        self.tabs_main = QTabWidget()
        self.tabs_main.setStyleSheet("""
            QTabBar::tab { height: 40px; width: 150px; font-weight: bold; font-size: 11pt; }
        """)
        
        # --- TAB 1: ESTRATEGIAS (Dashboard) ---
        self.tab_strategies = QWidget()
        layout_strat = QVBoxLayout(self.tab_strategies)
        
        # Dashboard Frame (Moved here)
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("background-color: #252526; border-radius: 5px;")
        header_layout = QVBoxLayout(self.header_frame)
        
        # Top Row: Status & Buttons
        top_row = QHBoxLayout()
        self.lbl_status = QLabel("System: CONNECTING...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #FFA500; font-size: 12pt;")
        
        self.btn_panic = QPushButton("PANIC: CLOSE ALL")
        self.btn_panic.setStyleSheet("background-color: #FF0000; color: white; font-weight: bold; padding: 10px;")
        self.btn_panic.clicked.connect(self.panic_close_all)
        
        top_row.addWidget(self.lbl_status)
        top_row.addStretch()
        top_row.addWidget(self.btn_panic)
        header_layout.addLayout(top_row)
        
        # Dashboard Table
        self.table_dashboard = QTableWidget()
        self.table_dashboard.setColumnCount(12)
        self.table_dashboard.setHorizontalHeaderLabels(["ESTRATEGIA", "BALANCE", "EQUIDAD", "PNL", "ROI (Anual)", "ROI (Diario)", "OPs", "G-P", "WIN %", "ACTIVAS", "INICIO", "CONTROL"])
        self.table_dashboard.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_dashboard.setSortingEnabled(True)
        self.table_dashboard.verticalHeader().setVisible(False)
        self.table_dashboard.setStyleSheet("font-size: 11pt;")
        # self.table_dashboard.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # self.table_dashboard.setFixedHeight(300) 
        header_layout.addWidget(self.table_dashboard)
        
        layout_strat.addWidget(self.header_frame)
        self.tabs_main.addTab(self.tab_strategies, "Estrategias")

        # --- TAB 1b: MACRO / INVERSION ---
        self.tab_macro = QWidget()
        layout_macro = QVBoxLayout(self.tab_macro)
        
        # Use QTreeWidget for Hierarchy
        self.tree_macro = QTreeWidget()
        self.tree_macro.setHeaderLabels(["Estrategia / Activo", "Posición", "Precio", "Valor Total", "Info / Régimen"])
        self.tree_macro.setColumnWidth(0, 250)
        self.tree_macro.setStyleSheet("font-size: 11pt; QTreeWidget::item { padding: 4px; }")
        layout_macro.addWidget(self.tree_macro)
        
        self.tabs_main.addTab(self.tab_macro, "Inversión (Macro)")
        
        # --- TAB 2: MERCADO (Monitor Expanded) ---
        self.tab_market = QWidget()
        layout_market = QVBoxLayout(self.tab_market)
        
        self.market_columns = [
            "Symbol", "Price", "Open", "High", "Low", "Close", "Volume", 
            "Vol Mean", "OBV", "MFI 14", "ATR 14", 
            "BB Up", "BB Low", "BB Width", 
            "RSI 14", "Stoch K", "Stoch D", "Stoch RSI", "ADX 14", 
            "Body", "Wick Up", "Wick Down", "W/B Ratio", "PinBar", 
            "Pivot P", "R1", "S1", "R2", "S2", 
            "EMA 200", "Dist EMA%", "Trend 1h", "Fib Lvl", 
            "VRel", "ERR", "Regime"
        ]
        
        self.table_monitor = QTableWidget()
        self.table_monitor.setColumnCount(len(self.market_columns))
        self.table_monitor.setHorizontalHeaderLabels(self.market_columns)
        self.table_monitor.verticalHeader().setVisible(False)
        self.table_monitor.setAlternatingRowColors(True)
        self.table_monitor.setStyleSheet("alternate-background-color: #1A1A1A;")
        # Enable Scrollbars
        self.table_monitor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        layout_market.addWidget(self.table_monitor)
        self.tabs_main.addTab(self.tab_market, "Mercado")
        
        # --- TAB 3: ACTIVE OPERATIONS ---
        self.tab_ops = QWidget()
        layout_ops = QVBoxLayout(self.tab_ops)
        
        ops_header = QHBoxLayout()
        self.combo_filter = QComboBox()
        self.combo_filter.addItem("All Strategies")
        self.combo_filter.currentTextChanged.connect(self.on_filter_changed)
        ops_header.addWidget(QLabel("Filter Strategy: "))
        ops_header.addWidget(self.combo_filter)
        ops_header.addStretch()
        
        layout_ops.addLayout(ops_header)
        
        self.table_ops = QTableWidget()
        self.table_ops.setColumnCount(12) 
        self.table_ops.setHorizontalHeaderLabels(["Estrat", "ID", "Simbolo", "Tipo", "PnL", "Max PnL", "Fees", "Invertido", "Estado TS", "Precio TS", "Grafico", "Cerrar"])
        self.table_ops.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_ops.setSortingEnabled(True)
        self.table_ops.verticalHeader().setVisible(False)
        layout_ops.addWidget(self.table_ops)
        self.tabs_main.addTab(self.tab_ops, "Active Operations")
        
        # --- TAB 4: TRADE HISTORY ---
        self.tab_history = QWidget()
        layout_hist = QVBoxLayout(self.tab_history)

        hist_header = QHBoxLayout()
        self.combo_hist_filter = QComboBox()
        self.combo_hist_filter.addItem("Todas las Estrategias")
        self.combo_hist_filter.currentTextChanged.connect(self.on_hist_filter_changed)
        hist_header.addWidget(QLabel("Filtrar Estrategia: "))
        hist_header.addWidget(self.combo_hist_filter)
        hist_header.addStretch()
        layout_hist.addLayout(hist_header)
        
        self.table_history = QTableWidget()
        self.table_history.setColumnCount(10) 
        self.table_history.setHorizontalHeaderLabels(["Estrat", "ID", "Simbolo", "Tipo", "Apertura", "Cierre", "Fees", "PnL", "Max PnL", "Resultado"])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_history.setSortingEnabled(True)
        self.table_history.verticalHeader().setVisible(False)
        layout_hist.addWidget(self.table_history)
        self.tabs_main.addTab(self.tab_history, "Trade History")
        
        # --- TAB 5: LOGS ---
        self.tab_logs = QWidget()
        layout_logs = QVBoxLayout(self.tab_logs)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas; font-size: 10pt;")
        layout_logs.addWidget(self.log_view)
        self.tabs_main.addTab(self.tab_logs, "Logs")
        
        # Add Tabs to Main Layout
        main_layout.addWidget(self.tabs_main)
        
        # --- WORKER ---
        self.worker = WorkerThread()
        self.worker.log_signal.connect(self.append_log)
        self.worker.monitor_signal.connect(self.update_monitor)
        self.worker.operations_signal.connect(self.update_operations)
        self.worker.history_signal.connect(self.update_history)
        self.worker.dashboard_signal.connect(self.update_dashboard)
        self.worker.macro_signal.connect(self.update_macro)
        
        # Setup Logging
        log_handler = QtLogHandler(self.worker.log_signal)
        log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)
        
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
            self.lbl_status.setText("System: ONLINE (Kraken Multi-Strategy)")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #00FF00;")
            
            # Force Initial Dashboard Render (Zero Values)
            QTimer.singleShot(2000, lambda: self.handle_monitor_update([]))

    def update_macro(self, data):
        self.tree_macro.clear()
        
        for d in data:
            # 1. Strategy Root Item
            strat_name = d.get('name', 'Unknown')
            active = d.get('active', True)
            status_str = "ACTIVO" if active else "INACTIVO"
            
            # Total Value
            total_val = d.get('equity', d.get('balance_usdt', 0.0))
            currency = "€" if "Kraken" in strat_name else "$"
            
            regime = d.get('regime', d.get('mode', 'Unknown'))
            
            root = QTreeWidgetItem(self.tree_macro)
            root.setText(0, strat_name)
            root.setText(3, f"{total_val:.2f}{currency}")
            root.setText(4, f"{status_str} | {regime}")
            
            # Style Root
            root.setForeground(0, QColor("#00FFFF")) # Cyan Names
            root.setExpanded(True)
            
            # 2. Holdings (Children)
            holdings = d.get('holdings', {})
            prices = d.get('prices', {})
            
            # Handle Cash for Binance
            if "Binance" in strat_name:
                cash = d.get('balance_usdt', 0.0)
                if cash > 0.01:
                    item = QTreeWidgetItem(root)
                    item.setText(0, "USDT (Cash)")
                    item.setText(1, f"{cash:.2f}")
                    item.setText(2, f"1.00$")
                    item.setText(3, f"{cash:.2f}$")
            
            for asset, amt in holdings.items():
                if amt < 0.0001: continue
                
                # Get Price
                price = prices.get(asset, 0.0)
                
                # Correction for EUR cash in Kraken
                if asset == 'EUR': price = 1.0
                
                val = amt * price
                
                item = QTreeWidgetItem(root)
                item.setText(0, asset)
                item.setText(1, f"{amt:.4f}")
                item.setText(2, f"{price:.2f}{currency}")
                item.setText(3, f"{val:.2f}{currency}")
                
                # Color code Amount/Value
                item.setForeground(3, QColor("#00FF00" if val > 0 else "#FFFFFF"))

    def update_dashboard(self, data):
        # Dynamic Filter Population (One-time Init)
        if self.combo_filter.count() == 1 and len(data) > 0:
            strat_ids = sorted([d['id'] for d in data])
            display_names = [STRATEGY_DISPLAY_NAMES.get(sid, sid) for sid in strat_ids]
            # Map back? Just add raw IDs to combo for filtering logic simplicity or handle mapping
            # Actually dashboard combo filters Active Ops, keep IDs there or Names?
            # Let's keep IDs in combo for now for simplicity of filtering, or use Names.
            # User wants Names.
            self.combo_filter.clear()
            self.combo_filter.addItem("Todas las Estrategias")
            self.combo_filter.addItems(strat_ids) # Logic uses ID

            # History combo
            self.combo_hist_filter.clear()
            self.combo_hist_filter.addItem("Todas las Estrategias")
            self.combo_hist_filter.addItems(strat_ids)
            
        self.table_dashboard.setSortingEnabled(False) # Disable during update
        self.table_dashboard.setRowCount(len(data))
        
        total_global_equity = 0.0
        
        for r, d in enumerate(data):
             # Spanish Name
             strat_name = STRATEGY_DISPLAY_NAMES.get(d['id'], d['id'])
             
             # Sortable Items (Name)
             self.table_dashboard.setItem(r, 0, QTableWidgetItem(strat_name))
             
             # Numeric Sorting Helper (Balance)
             item_bal = QTableWidgetItem(f"{d['balance']:.2f}€")
             item_bal.setData(Qt.ItemDataRole.UserRole, d['balance']) # Store value for sort if we used custom sorter
             self.table_dashboard.setItem(r, 1, item_bal)
             
             item_eq = QTableWidgetItem(f"{d['equity']:.2f}€")
             self.table_dashboard.setItem(r, 2, item_eq)
             
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

             # ROI Daily
             start_t = d.get('start_time', 0)
             if start_t > 0:
                 days_active = (time.time() - start_t) / 86400.0
                 if days_active < 1.0: days_active = 1.0 # Minimum 1 day to avoid infinity
                 
                 # Calculate Total ROI %
                 # Assuming Initial Balance is constant defined in config, or we infer from balance - pnl?
                 # Better to use: Total PnL / Initial * 100
                 initial_bal = config.INITIAL_BALANCE
                 total_roi_pct = (d['pnl_total'] / initial_bal) * 100
                 daily_roi = total_roi_pct / days_active
             else:
                 daily_roi = 0.0
                 
             d_roi_item = QTableWidgetItem(f"{daily_roi:.2f}%")
             if daily_roi >= 0: d_roi_item.setForeground(QColor("#00FF00"))
             else: d_roi_item.setForeground(QColor("#FF0000"))
             self.table_dashboard.setItem(r, 5, d_roi_item)

             self.table_dashboard.setItem(r, 6, QTableWidgetItem(str(d['total_ops'])))
             self.table_dashboard.setItem(r, 7, QTableWidgetItem(f"{d['wins']}-{d['losses']}"))
             
             self.table_dashboard.setItem(r, 7, QTableWidgetItem(f"{d['wins']}-{d['losses']}"))
             
             self.table_dashboard.setItem(r, 8, QTableWidgetItem(f"{d['win_rate']:.1f}%"))
             
             # Active: Total (W-L)
             act_str = f"{d['open_pos']} ({d.get('active_wins',0)}-{d.get('active_losses',0)})"
             act_item = QTableWidgetItem(act_str)
             if d.get('active_wins',0) > d.get('active_losses',0): act_item.setForeground(QColor("#00FF00"))
             elif d.get('active_losses',0) > d.get('active_wins',0): act_item.setForeground(QColor("#FF0000"))
             self.table_dashboard.setItem(r, 9, act_item)
             
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
             widget.setLayout(layout)
             self.table_dashboard.setCellWidget(r, 11, widget)

             # Started Time
             start_t = d.get('start_time', 0)
             if start_t > 0:
                 diff = time.time() - start_t
                 
                 # Constants
                 MINUTE = 60
                 HOUR = 3600
                 DAY = 86400
                 MONTH = 2592000 # Approx 30 days
                 YEAR = 31536000 # Approx 365 days
                 
                 years = int(diff // YEAR)
                 diff %= YEAR
                 
                 months = int(diff // MONTH)
                 diff %= MONTH
                 
                 days = int(diff // DAY)
                 diff %= DAY
                 
                 hours = int(diff // HOUR)
                 diff %= HOUR
                 
                 mins = int(diff // MINUTE)
                 secs = int(diff % MINUTE)
                 
                 parts = []
                 if years > 0: parts.append(f"{years}y")
                 if months > 0: parts.append(f"{months}mo")
                 if days > 0: parts.append(f"{days}d")
                 if hours > 0: parts.append(f"{hours}h")
                 if mins > 0: parts.append(f"{mins}m")
                 if secs > 0: parts.append(f"{secs}s")
                 
                 if not parts:
                     time_str = "0s"
                 else:
                     time_str = " ".join(parts)
             else:
                 time_str = ""
             self.table_dashboard.setItem(r, 10, QTableWidgetItem(time_str))
             
        self.table_dashboard.setSortingEnabled(True) # Re-enable
        
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
            
            QTableWidget.keyPressEvent(table, event)

        table.keyPressEvent = handle_key_press

    def update_monitor(self, data):
        self.table_monitor.setRowCount(len(data))
        
        # Map Column Name -> Data Key
        for r, row in enumerate(data):
            for c, col_name in enumerate(self.market_columns):
                # Mapping Logic (col_name to key)
                key_map = {
                    "Symbol": "symbol", "Price": "price", "Open": "Open", "High": "High", "Low": "Low", "Close": "Close", 
                    "Volume": "Volume", "Vol Mean": "Volume_Mean_20", "OBV": "OBV", "MFI 14": "MFI_14", 
                    "ATR 14": "ATR_14", "BB Up": "Bollinger_Upper", "BB Low": "Bollinger_Lower", "BB Width": "Bollinger_Width",
                    "RSI 14": "Stoch K", "Stoch K": "Stoch_K", "Stoch D": "Stoch_D", "Stoch RSI": "Stoch_RSI_K", 
                    "ADX 14": "ADX_14", "Body": "Candle_Body_Size", "Wick Up": "Upper_Wick_Size", 
                    "Wick Down": "Lower_Wick_Size", "W/B Ratio": "Wick_Body_Ratio", "PinBar": "PinBar", 
                    "Pivot P": "Pivot_P", "R1": "Pivot_R1", "S1": "Pivot_S1", "R2": "Pivot_R2", "S2": "Pivot_S2", 
                    "EMA 200": "EMA_200", "Dist EMA%": "Dist_EMA200_Pct", "Trend 1h": "Current_Trend_1h", 
                    "Fib Lvl": "Fibonacci_Level", "VRel": "vrel", "ERR": "err", "Regime": "Market_Regime"
                }
                
                # Special Handle for RSI key
                if col_name == "RSI 14": 
                     val = row.get("rsi") # Use the float one if simple, or string 'RSI_14' if rich
                     if "RSI_14" in row: val = row["RSI_14"]
                     text = str(val) if val else "50.0"
                elif col_name == "VRel":
                     val = row.get("vrel")
                     text = f"{val:.2f}" if val is not None else "0.00"
                elif col_name == "ERR":
                     val = row.get("err")
                     text = f"{val:.2f}" if val is not None else "0.00"
                else: 
                     k = key_map.get(col_name, col_name)
                     val = row.get(k, "")
                     text = str(val)
                
                item = QTableWidgetItem(text)
                
                item = QTableWidgetItem(text)
                
                # Coloring
                if col_name == "Price":
                    try:
                        p = float(text)
                        # Check against Open (Candle Color)
                        o_val = row.get("Open")
                        if o_val:
                            o = float(o_val)
                            if p > o: item.setForeground(QColor("#00FF00"))
                            elif p < o: item.setForeground(QColor("#FF0000"))
                    except: pass

                elif col_name == "RSI 14":
                     try:
                         v = float(text)
                         if v < config.RSI_OVERSOLD: item.setForeground(QColor("#00FF00"))
                         elif v > config.RSI_OVERBOUGHT: item.setForeground(QColor("#FF0000"))
                     except: pass
                elif col_name == "VRel":
                     try:
                         v = float(text)
                         if v > config.VREL_THRESHOLD: item.setForeground(QColor("#FFA500"))
                     except: pass
                elif col_name == "ERR":
                     try:
                         v = float(text)
                         if v > config.ERR_THRESHOLD: item.setForeground(QColor("#FFA500"))
                     except: pass
                elif col_name == "PinBar" and text == "True":
                     item.setForeground(QColor("#00FFFF"))
                     
                self.table_monitor.setItem(r, c, item)

    def on_filter_changed(self, text):
        if hasattr(self, 'last_ops_data'):
            self.update_operations(self.last_ops_data)

    def on_hist_filter_changed(self, text):
        if hasattr(self, 'last_hist_data'):
            self.update_history(self.last_hist_data)

    def update_operations(self, data):
        self.last_ops_data = data 
        
        # Filter Data
        filter_strat = self.combo_filter.currentText()
        filtered_data = []
        
        for pos in data:
            strat_id = pos.get('strategy_id', '??')
            if filter_strat == "Todas las Estrategias" or filter_strat == "All Strategies" or strat_id == filter_strat:
                filtered_data.append(pos)
        
        # Sort by PnL
        # filtered_data.sort(key=lambda x: x.get('pnl_val', 0.0), reverse=True) # Let user sort via table header now
        
        self.table_ops.setSortingEnabled(False) # Disable while populating
        self.table_ops.setRowCount(len(filtered_data))
        
        for r, pos in enumerate(filtered_data):
            strat_id = pos.get('strategy_id', '??')
            # Use Spanish if available
            strat_name = STRATEGY_DISPLAY_NAMES.get(strat_id, strat_id)
            self.table_ops.setItem(r, 0, QTableWidgetItem(strat_name))
            
            # ID
            id_item = SortableTableWidgetItem(str(pos['id']))
            id_item.setData(Qt.ItemDataRole.UserRole, pos['id']) # Numeric sort
            self.table_ops.setItem(r, 1, id_item)
            
            sym = pos.get('symbol', '???') 
            self.table_ops.setItem(r, 2, QTableWidgetItem(sym))
            
            type_item = QTableWidgetItem(pos['type'])
            if pos['type'] == 'LONG': type_item.setForeground(QColor("#00FF00"))
            else: type_item.setForeground(QColor("#FF0000"))
            self.table_ops.setItem(r, 3, type_item)
            
            pnl_val = pos.get('pnl_val', 0.0)
            pnl_pct = pos.get('pnl_pct', 0.0)
            pnl_str = f"{pnl_val:+.2f}€ ({pnl_pct:+.2f}%)"
            pnl_item = SortableTableWidgetItem(pnl_str)
            pnl_item.setData(Qt.ItemDataRole.UserRole, pnl_val) # Numeric sort
            
            if pnl_val < 0:
                pnl_item.setForeground(QColor("#FF0000")) 
            elif pnl_pct < 0:
                pnl_item.setForeground(QColor("#FFA500")) 
            else:
                pnl_item.setForeground(QColor("#00FF00")) 
                
            self.table_ops.setItem(r, 4, pnl_item)
            
            # Max PnL
            max_pnl = pos.get('max_pnl_pct', 0.0)
            max_pnl_item = SortableTableWidgetItem(f"{max_pnl:+.2f}%")
            max_pnl_item.setData(Qt.ItemDataRole.UserRole, max_pnl)
            
            if max_pnl >= 0: max_pnl_item.setForeground(QColor("#00FF00"))
            else: max_pnl_item.setForeground(QColor("#FF0000"))
            self.table_ops.setItem(r, 5, max_pnl_item)

            fees = pos.get('fees_eur', 0.0)
            fees_item = SortableTableWidgetItem(f"{fees:.2f}€")
            fees_item.setData(Qt.ItemDataRole.UserRole, fees)
            self.table_ops.setItem(r, 6, fees_item)
            
            invested = pos.get('margin', 0.0)
            inv_item = SortableTableWidgetItem(f"{invested:.2f}€")
            inv_item.setData(Qt.ItemDataRole.UserRole, invested)
            self.table_ops.setItem(r, 7, inv_item)
            
            ts_stat = pos.get('ts_status', 'WAIT')
            stat_item = QTableWidgetItem(ts_stat)
            if "ACTIVE" in ts_stat: stat_item.setForeground(QColor("#00FF00"))
            else: stat_item.setForeground(QColor("#FFA500"))
            self.table_ops.setItem(r, 8, stat_item)
            
            ts_price = pos.get('ts_price', 0.0)
            ts_item = SortableTableWidgetItem(f"{ts_price:.4f}")
            ts_item.setData(Qt.ItemDataRole.UserRole, ts_price)
            self.table_ops.setItem(r, 9, ts_item)
            
            btn_graph = QPushButton("GRAPH")
            btn_graph.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold;")
            btn_graph.clicked.connect(lambda checked, pid=pos['id'], sid=strat_id, s=sym: self.open_chart(pid, sid, s))
            self.table_ops.setCellWidget(r, 10, btn_graph)
            
            btn_close = QPushButton("CLOSE")
            btn_close.clicked.connect(lambda checked, pid=pos['id'], sid=strat_id, pprice=pos.get('mark_price', 0.0): self.manual_close(pid, sid, pprice))
            btn_close.setStyleSheet("background-color: #AA0000; color: white; font-weight: bold;")
            self.table_ops.setCellWidget(r, 11, btn_close)

            # Update Active Chart if Open
            if self.active_chart and self.active_chart.isVisible() and self.active_chart.trade_id == pos['id']:
                 pass
                 
        self.table_ops.setSortingEnabled(True)

    def update_history(self, data):
        self.last_hist_data = data
        
        # Filter
        filter_strat = self.combo_hist_filter.currentText()
        filtered_data = []
        for h in data:
            strat_id = h.get('strategy_id', '??')
            if filter_strat == "Todas las Estrategias" or filter_strat == "All Strategies" or strat_id == filter_strat:
                filtered_data.append(h)

        self.table_history.setSortingEnabled(False)
        self.table_history.setRowCount(len(filtered_data))
        
        for r, h in enumerate(filtered_data):
            strat_id = h.get('strategy_id', '??')
            strat_name = STRATEGY_DISPLAY_NAMES.get(strat_id, strat_id)
            self.table_history.setItem(r, 0, QTableWidgetItem(strat_name))
            
            id_item = QTableWidgetItem(str(h['id']))
            id_item.setData(Qt.ItemDataRole.UserRole, h['id'])
            self.table_history.setItem(r, 1, id_item)
            
            self.table_history.setItem(r, 2, QTableWidgetItem(h['symbol']))
            
            type_item = QTableWidgetItem(h['type'])
            if h['type'] == 'LONG': type_item.setForeground(QColor("#00FF00"))
            else: type_item.setForeground(QColor("#FF0000"))
            self.table_history.setItem(r, 3, type_item)
            
            # Times
            ot = datetime.datetime.fromtimestamp(h['entry_time']).strftime("%d/%m %H:%M")
            self.table_history.setItem(r, 4, QTableWidgetItem(ot))
            
            ct = datetime.datetime.fromtimestamp(h.get('close_time', 0)).strftime("%d/%m %H:%M")
            self.table_history.setItem(r, 5, QTableWidgetItem(ct))
            
            fees = h.get('fees_eur', 0.0)
            self.table_history.setItem(r, 6, QTableWidgetItem(f"{fees:.2f}€"))
            
            pnl = h.get('final_pnl', 0.0)
            pnl_item = QTableWidgetItem(f"{pnl:.2f}€")
            if pnl >= 0: pnl_item.setForeground(QColor("#00FF00"))
            else: pnl_item.setForeground(QColor("#FF0000"))
            self.table_history.setItem(r, 7, pnl_item)
            
            m_pnl = h.get('max_pnl_pct', 0.0)
            m_item = QTableWidgetItem(f"{m_pnl:.2f}%")
            if m_pnl >= 0: m_item.setForeground(QColor("#00FF00"))
            else: m_item.setForeground(QColor("#FF0000"))
            self.table_history.setItem(r, 8, m_item)
            
            self.table_history.setItem(r, 9, QTableWidgetItem(h.get('exit_reason', '')))
            
        self.table_history.setSortingEnabled(True)

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
        logging.warning("!!! GLOBAL PANIC CLOSE TRIGGERED !!!")
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
