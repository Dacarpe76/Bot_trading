
import flet as ft
import time
import threading
import sys
import os
from datetime import datetime

# Add Bot_trader to path
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))

try:
    from kraken_connector import KrakenConnector
    from strategy import Strategy
    from policy import Policy
    from data_loader import MarketData
    import bot_config as config
except ImportError as e:
    print(f"Error importing modules: {e}")

# GLOBAL STATE
class BotState:
    is_running = True
    panic_mode = False
    status_msg = "Inicializando..."
    equity = 0.0
    last_update = "Nunca"

state = BotState()
connector = KrakenConnector()
market = MarketData()
strategy = Strategy()
policy = Policy()

def bot_loop(page):
    """Background Loop"""
    while True:
        try:
            if not state.is_running:
                time.sleep(1)
                continue
                
            if state.panic_mode:
                state.status_msg = "🛑 MODO PÁNICO ACTIVO. Bot Detenido."
                connector.panic_close_all()
                page.update()
                time.sleep(5)
                continue
            
            # --- NORMAL TRADING OPERATION ---
            state.status_msg = "📡 Analizando mercado..."
            page.update()
            
            # 1. Fetch Data (Real Time)
            # For simplicity, we assume Daily candles logic, but check every hour
            # OR fetches live price compared to signals. 
            # Here we just show Equity update for the UI demo:
            equity, _ = connector.get_balance_equity()
            state.equity = equity
            state.last_update = datetime.now().strftime("%H:%M:%S")
            state.status_msg = "✅ Bot Activo - Esperando cierre diario"
            
            # --- TRADING LOGIC PLACEHOLDER ---
            # To be fully implemented: Check time (e.g. 00:00 UTC), run strategy, rebalance.
            # For now, assumes passive monitoring.
            
            page.update()
            time.sleep(10) # Update UI every 10s
            
        except Exception as e:
            state.status_msg = f"❌ Error: {str(e)}"
            page.update()
            time.sleep(10)

def main(page: ft.Page):
    page.title = "Macro Bot Controller"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    
    # UI Elements
    lbl_status = ft.Text(value=state.status_msg, size=20, color=ft.colors.WHITE)
    lbl_equity = ft.Text(value="Equity: -- €", size=30, weight=ft.FontWeight.BOLD)
    lbl_time = ft.Text(value="Ultima actualización: --", italic=True)
    
    def update_ui_loop():
        while True:
            lbl_status.value = state.status_msg
            lbl_status.color = ft.colors.RED if state.panic_mode else ft.colors.GREEN
            lbl_equity.value = f"Equity: {state.equity:.2f} €"
            lbl_time.value = f"Update: {state.last_update}"
            page.update()
            time.sleep(1)

    def on_panic_click(e):
        if not state.panic_mode:
            # ACTIVATE PANIC
            state.panic_mode = True
            btn_panic.text = "ACTIVAR!!"
            btn_panic.bgcolor = ft.colors.GREEN
            btn_panic.icon = ft.icons.PLAY_ARROW
            state.status_msg = "EJECUTANDO VENTA DE EMERGENCIA..."
        else:
            # DEACTIVATE PANIC
            state.panic_mode = False
            btn_panic.text = "PANIC!!"
            btn_panic.bgcolor = ft.colors.RED
            btn_panic.icon = ft.icons.WARNING
            state.status_msg = "Reanudando operaciones..."
        page.update()

    btn_panic = ft.ElevatedButton(
        text="PANIC!!",
        bgcolor=ft.colors.RED,
        color=ft.colors.WHITE,
        width=200,
        height=200,
        style=ft.ButtonStyle(shape=ft.CircleBorder()),
        on_click=on_panic_click
    )

    page.add(
        ft.Column(
            [
                lbl_equity,
                lbl_status,
                ft.Container(height=20),
                btn_panic,
                ft.Container(height=20),
                lbl_time
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )
    
    # Start Threads
    t_bot = threading.Thread(target=bot_loop, args=(page,), daemon=True)
    t_bot.start()
    
    t_ui = threading.Thread(target=update_ui_loop, daemon=True)
    t_ui.start()

# Ejecutar como Aplicación Web accesible en red local
# Esto permite abrirlo desde el móvil en la misma Wifi: http://<IP_PC>:8080
print("🚀 Iniciando Servidor Web...")
print("📲 Para ver en el móvil: Conecta ambos a la misma WiFi y abre http://<TU_IP_LOCAL>:8080")
ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8080, host="0.0.0.0")
