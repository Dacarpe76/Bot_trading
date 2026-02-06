import time
import schedule
import logging
from datetime import datetime
import database
import telegram_bot
from kraken_bot import KrakenBot

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def job_analysis(bots):
    """Scheduled analysis job for all bots."""
    logger.info("Starting scheduled analysis for all modes...")
    for bot in bots:
        try:
            logger.info(f"Running analysis for mode: {bot.mode}")
            bot.run_analysis()
        except Exception as e:
            logger.error(f"Error during analysis ({bot.mode}): {e}")

def job_daily_report(bots):
    """Scheduled daily report."""
    logger.info("Sending hourly report...")
    try:
        # Collect data from all bots
        breakdowns = {} # Key: mode, Value: dict breakdown
        
        for bot in bots:
            breakdowns[bot.mode] = bot.get_portfolio_breakdown()
        
        expense_cube = database.get_expense_cube_balance()
        
        # Pass structured data to telegram_bot
        telegram_bot.send_consolidated_report(
            real_data=breakdowns['real'],
            test1_data=breakdowns['test_1'],
            test2_data=breakdowns['test_2'],
            expense_cube_eur=expense_cube
        )
    except Exception as e:
        logger.error(f"Error sending report: {e}")

def main():
    logger.info("🤖 Iniciando Bot de Inversión Kraken (Multi-Modo)")
    
    # 1. Initialize Database
    database.init_db()
    
    # 2. Initialize Bots
    # Real Mode (Standard Strategy, Real Money)
    bot_real = KrakenBot(mode='real', strategy='standard')
    
    # Test 1 (Standard Strategy, Simulated Money)
    bot_test1 = KrakenBot(mode='test_1', strategy='standard')
    
    # Test 2 (Instant Strategy, Simulated Money)
    bot_test2 = KrakenBot(mode='test_2', strategy='instant')
    
    bots = [bot_real, bot_test1, bot_test2]
    
    # Send startup message
    telegram_bot.send_message("🤖 *Bot Iniciado (Multi-Modo)*\n✅ Real\n✅ Test 1 (500€ Standard)\n✅ Test 2 (500€ Instant)\nEsperando ciclo de análisis...")

    # 3. Schedule Jobs
    # Analysis every hour
    schedule.every(1).hours.do(job_analysis, bots)
    
    # Hourly Report
    schedule.every(1).hours.do(job_daily_report, bots)
    
    # Run one analysis immediately on startup to seed/check
    job_analysis(bots)

    # 4. Main Loop
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario.")
