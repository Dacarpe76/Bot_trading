import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Credentials
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

# Kraken Credentials
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY")
KRAKEN_PRIVATE_KEY = os.getenv("KRAKEN_PRIVATE_KEY")

# Validation
if not all([TELEGRAM_TOKEN, MY_CHAT_ID, KRAKEN_API_KEY, KRAKEN_PRIVATE_KEY]):
    raise ValueError("Missing essential environment variables. Please check your .env file.")
