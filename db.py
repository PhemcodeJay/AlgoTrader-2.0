# db.py (fixed version)
# Fixes: Completed truncated sections.
# Added missing imports.
# Fixed get_trade_by_id to use order_id.
# Ensured all methods are complete.
# Added handling for real trades in get_profitable_trades_stats.
# Fixed get_ml_training_data to handle both real and virtual.

import os
import json
from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Union, cast, Any
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, String, Integer, Float, DateTime, Boolean, JSON, text
)
import pandas as pd
from sqlalchemy.orm import (
    declarative_base, sessionmaker, Session, Mapped, mapped_column
)

from sqlalchemy import update

# Load .env file if it exists
load_dotenv()

Base = declarative_base()

# === SQLAlchemy Models ===
class Signal(Base):
    __tablename__ = 'signals'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String)
    interval: Mapped[str] = mapped_column(String)
    signal_type: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float)
    indicators: Mapped[dict] = mapped_column(JSON)
    strategy: Mapped[str] = mapped_column(String, default="Auto")
    side: Mapped[str] = mapped_column(String, default="LONG")
    sl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    leverage: Mapped[Optional[int]] = mapped_column(Integer, default=20)
    margin_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "interval": self.interval,
            "signal_type": self.signal_type,
            "score": self.score,
            "strategy": self.strategy,
            "side": self.side,
            "sl": self.sl,
            "tp": self.tp,
            "entry": self.entry,
            "leverage": self.leverage,
            "margin_usdt": self.margin_usdt,
            "market": self.market,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "indicators": self.indicators,
        }

class Trade(Base):
    __tablename__ = 'trades'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    leverage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    margin_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String)
    order_id: Mapped[str] = mapped_column(String)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    virtual: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "leverage": self.leverage,
            "margin": self.margin_usdt,
            "pnl": self.pnl,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else None,
            "status": self.status,
            "order_id": self.order_id,
            "unrealized_pnl": self.unrealized_pnl,
            "virtual": self.virtual,
        }

class Portfolio(Base):
    __tablename__ = 'portfolio'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, unique=True)
    qty: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    value: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    capital: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "value": self.value,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
            "capital": self.capital,
            "unrealized_pnl": self.unrealized_pnl,
            "is_virtual": self.is_virtual,
        }

class SystemSetting(Base):
    __tablename__ = 'settings'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    value: Mapped[str] = mapped_column(String)

# === DB Setup ===

db_url = os.getenv("DATABASE_URL_RENDER") or os.getenv("DATABASE_URL")

if not db_url:
    raise RuntimeError("❌ DATABASE_URL not set")

engine = create_engine(db_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

class DatabaseManager:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._settings_file = "settings.json"
        self._load_settings_from_file()

    def get_session(self):
        return self.SessionLocal()

    def _load_settings_from_file(self):
        if os.path.exists(self._settings_file):
            with open(self._settings_file, "r") as f:
                file_settings = json.load(f)
            with self.get_session() as session:
                for key, value in file_settings.items():
                    setting = session.query(SystemSetting).filter_by(key=key).first()
                    if not setting:
                        setting = SystemSetting(key=key, value=json.dumps(value))
                        session.add(setting)
                session.commit()

    def _save_settings_to_file(self):
        with self.get_session() as session:
            settings = session.query(SystemSetting).all()
            file_settings = {s.key: json.loads(s.value) for s in settings}
        with open(self._settings_file, "w") as f:
            json.dump(file_settings, f)

    def add_signal(self, signal_data: dict):
        with self.get_session() as session:
            signal = Signal(**signal_data)
            session.add(signal)
            session.commit()
            return signal.to_dict()

    def add_trade(self, trade_data: dict):
        with self.get_session() as session:
            trade = Trade(**trade_data)
            session.add(trade)
            session.commit()
            return trade.to_dict()

    def update_trade_unrealized_pnl(self, order_id: str, unrealized_pnl: float):
        with self.get_session() as session:
            stmt = update(Trade).where(Trade.order_id == order_id).values(unrealized_pnl=unrealized_pnl)
            session.execute(stmt)
            session.commit()

    def update_portfolio_unrealized_pnl(self, symbol: str, unrealized_pnl: float, is_virtual: bool):
        with self.get_session() as session:
            stmt = update(Portfolio).where(Portfolio.symbol == symbol, Portfolio.is_virtual == is_virtual).values(unrealized_pnl=unrealized_pnl)
            session.execute(stmt)
            session.commit()

    def get_setting(self, key: str) -> Optional[str]:
        with self.get_session() as session:
            setting = session.query(SystemSetting).filter_by(key=key).first()
            return json.loads(setting.value) if setting else None

    def update_setting(self, key: str, value: Any):
        with self.get_session() as session:
            setting = session.query(SystemSetting).filter_by(key=key).first()
            if setting:
                setting.value = json.dumps(value)
            else:
                setting = SystemSetting(key=key, value=json.dumps(value))
                session.add(setting)
            session.commit()
        self._save_settings_to_file()

    def reset_all_settings_to_defaults(self):
        with self.get_session() as session:
            session.query(SystemSetting).delete()
            session.commit()
        self._save_settings_to_file()
        print("[DB] 🔄 Settings reset to default values")

    def get_signals_count(self) -> int:
        with self.get_session() as session:
            return session.query(Signal).count()

    def get_trades_count(self) -> int:
        with self.get_session() as session:
            return session.query(Trade).count()

    def get_portfolio_count(self) -> int:
        with self.get_session() as session:
            return session.query(Portfolio).count()

    def get_db_health(self) -> dict:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_open_virtual_trades(self) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.status == 'open', Trade.virtual == True).all()

    def get_open_real_trades(self) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.status == 'open', Trade.virtual == False).all()

    def get_closed_virtual_trades(self) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.status == 'closed', Trade.virtual == True).all()

    def get_closed_real_trades(self) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.status == 'closed', Trade.virtual == False).all()

    def get_trade_by_id(self, trade_id: str) -> Trade:
        """Get a trade by its ID (order_id)"""
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.order_id == trade_id).first()

    def get_profitable_trades_stats(self) -> Dict:
        """Get statistics about profitable vs unprofitable trades for ML training"""
        with self.get_session() as session:
            closed_trades = session.query(Trade).filter(Trade.status == 'closed').all()

            if not closed_trades:
                return {"total": 0, "profitable": 0, "unprofitable": 0, "profit_rate": 0.0}

            profitable = sum(1 for t in closed_trades if t.pnl and t.pnl > 0)
            unprofitable = sum(1 for t in closed_trades if t.pnl and t.pnl <= 0)

            return {
                "total": len(closed_trades),
                "profitable": profitable,
                "unprofitable": unprofitable,
                "profit_rate": profitable / len(closed_trades) if closed_trades else 0.0
            }

    def get_status(self) -> Dict[str, Union[str, int, float]]:
        """
        Returns system status and ensures a 'SYSTEM_STATUS' record exists in settings.
        """
        with self.get_session() as session:
            status_setting = session.query(SystemSetting).filter_by(key="SYSTEM_STATUS").first()

            # If not exists, create it
            if not status_setting:
                status_setting = SystemSetting(
                    key="SYSTEM_STATUS",
                    value=json.dumps({
                        "total_signals": self.get_signals_count(),
                        "total_trades": self.get_trades_count(),
                        "total_portfolio": self.get_portfolio_count(),
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    })
                )
                session.add(status_setting)
                session.commit()

            # Load the JSON value
            try:
                status_data = json.loads(status_setting.value)
            except Exception:
                status_data = {}

            # Always refresh counts
            status_data.update({
                "total_signals": self.get_signals_count(),
                "total_trades": self.get_trades_count(),
                "total_portfolio": self.get_portfolio_count(),
                "last_updated": datetime.now(timezone.utc).isoformat()
            })

            # Save back to DB
            status_setting.value = json.dumps(status_data)
            session.commit()

            return status_data

    def get_ml_training_data(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get formatted data for ML training"""
        training_data: List[Dict[str, Any]] = []

        with self.get_session() as session:
            closed_trades = (
                session.query(Trade)
                .filter(
                    Trade.status == 'closed',
                    Trade.pnl.isnot(None)
                )
                .order_by(Trade.timestamp.desc())
                .limit(limit)
                .all()
            )

            for trade in closed_trades:
                pnl = cast(float, trade.pnl)  # Safe due to filter
                training_data.append({
                    "entry": trade.entry_price,
                    "tp": trade.take_profit,
                    "sl": trade.stop_loss,
                    "leverage": trade.leverage or 20,
                    "side": trade.side,
                    "pnl": pnl,
                    "profitable": 1 if pnl > 0 else 0,
                    "timestamp": trade.timestamp.isoformat() if trade.timestamp else None,
                    "type": "trade"
                })

        return training_data

# === Global Instance ===
db_manager = DatabaseManager(db_url=db_url)
db = db_manager