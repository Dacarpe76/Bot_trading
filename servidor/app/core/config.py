import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MEXC Trading Bot"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "YOUR_SUPER_SECRET_KEY_CHANGE_THIS"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 1 Week
    
    # Database
    DATABASE_URL: str = "sqlite:///./mexc_bot.db"
    
    # MEXC Credentials
    MEXC_API_KEY: str = os.getenv("MEXC_API_KEY", "")
    MEXC_SECRET_KEY: str = os.getenv("MEXC_SECRET_KEY", "")
    
    # Trading Config
    # XBT replaced with BTC for MEXC standard
    TRADING_PAIRS: list = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
        "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT"
    ]
    
    # Default Strategy Params
    DEFAULT_STAKE_USDT: float = 15.0 # Min order usually 5 USDT
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
