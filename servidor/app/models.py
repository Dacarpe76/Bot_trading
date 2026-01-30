from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import enum
import datetime

Base = declarative_base()

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"

class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.VIEWER)
    is_active = Column(Boolean, default=True)

class BotState(Base):
    __tablename__ = "bot_state"
    id = Column(Integer, primary_key=True)
    is_running = Column(Boolean, default=False)
    config_json = Column(JSON, default={}) # Stores active strategy params

class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    strategy = Column(String) # e.g. "RollingDCA"
    status = Column(String) # OPEN, CLOSED
    
    # Tracking
    avg_price = Column(Float)
    total_size = Column(Float)
    total_cost = Column(Float) # USDT
    
    # DCA Specific
    dca_step = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class OrderHistory(Base):
    __tablename__ = "order_history"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    side = Column(Enum(OrderSide))
    price = Column(Float)
    quantity = Column(Float)
    cost = Column(Float)
    status = Column(String) # FILLED, CANCELED
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)

class LogEntry(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(String) # INFO, ERROR, WARNING
    message = Column(String)
