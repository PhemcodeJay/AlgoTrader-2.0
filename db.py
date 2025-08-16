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
    raise RuntimeError("❌ DATABASE_URL_RENDER or DATABASE_URL must be set in environment.")

print("🔌 Using LOCAL PostgreSQL" if "localhost" in db_url or "127.0.0.1" in db_url else "🌐 Using RENDER PostgreSQL")

# Database configuration for production
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:password@localhost:5432/algotrader"
)

# Production database settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))

engine = create_engine(
    db_url,
    echo=False,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

# === Utility ===

def serialize_datetimes(obj):
    if isinstance(obj, dict):
        return {k: serialize_datetimes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetimes(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

# === Database Manager ===

class DatabaseManager:
    def __init__(self, db_url: str):
        self.engine = create_engine(
            db_url,
            echo=False,
            future=True,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            pool_timeout=DB_POOL_TIMEOUT,
            pool_recycle=DB_POOL_RECYCLE,
            pool_pre_ping=True
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

        self.settings = {
            "SCAN_INTERVAL": 3600,
            "TOP_N_SIGNALS": 5,
            "MAX_LOSS_PCT": -15.0,
            "TP_PERCENT": 0.30,
            "SL_PERCENT": 0.10,
            "LEVERAGE": 20,
            "RISK_PER_TRADE": 0.01,
        }
        self._load_settings_from_file()

    def get_session(self) -> Session:
        return self.Session()

    def add_signal(self, signal_data: Dict):
        signal_data["indicators"] = serialize_datetimes(signal_data.get("indicators", {}))
        with self.get_session() as session:
            session.add(Signal(**signal_data))
            session.commit()

    def get_last_signal(self, symbol: Optional[str] = None) -> Optional[Signal]:
        with self.get_session() as session:
            query = session.query(Signal).order_by(Signal.created_at.desc())
            if symbol:
                query = query.filter(Signal.symbol == symbol)
            return query.first()

    def get_signals(self, symbol: Optional[str] = None, limit: int = 50) -> List[Signal]:
        with self.get_session() as session:
            query = session.query(Signal).order_by(Signal.created_at.desc())
            if symbol:
                query = query.filter(Signal.symbol == symbol)
            return query.limit(limit).all()

    def add_trade(self, trade_data: Dict):
        with self.get_session() as session:
            session.add(Trade(**trade_data))
            session.commit()

    def get_trades(self, symbol: Optional[str] = None, limit: int = 50) -> List[Trade]:
        with self.get_session() as session:
            query = session.query(Trade).order_by(Trade.timestamp.desc())
            if symbol:
                query = query.filter(Trade.symbol == symbol)
            return query.limit(limit).all()

    def get_recent_trades(self, symbol: Optional[str] = None, limit: int = 50) -> List[Trade]:
        return self.get_trades(symbol=symbol, limit=limit)

    def get_open_trades(self) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.status == 'open').all()

    def get_trades_by_status(self, status: str) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(Trade.status == status).all()

    def close_trade(self, order_id: str, exit_price: float, pnl: float):
        with self.get_session() as session:
            trade = session.query(Trade).filter_by(order_id=order_id).first()
            if trade:
                trade.exit_price = exit_price
                trade.pnl = pnl
                trade.status = 'closed'
                session.commit()

    def update_trade_unrealized_pnl(self, order_id: str, unrealized_pnl: float) -> None:
        with self.get_session() as session:
            session.execute(
                update(Trade)
                .where(Trade.order_id == order_id)
                .values(unrealized_pnl=unrealized_pnl)
            )
            session.commit()

    def update_portfolio_unrealized_pnl(self, symbol: str, unrealized_pnl: float, is_virtual: bool = False) -> None:
        with self.get_session() as session:
            session.execute(
                update(Portfolio)
                .where(
                    Portfolio.symbol == symbol,
                    Portfolio.is_virtual == is_virtual
                )
                .values(unrealized_pnl=unrealized_pnl, updated_at=datetime.now(timezone.utc))
            )
            session.commit()

    def update_portfolio_balance(self, symbol: str, qty: float, avg_price: float, value: float):
        with self.get_session() as session:
            portfolio = session.query(Portfolio).filter_by(symbol=symbol).first()
            if portfolio:
                portfolio.qty = qty
                portfolio.avg_price = avg_price
                portfolio.value = value
                portfolio.updated_at = datetime.now(timezone.utc)
            else:
                portfolio = Portfolio(
                    symbol=symbol,
                    qty=qty,
                    avg_price=avg_price,
                    value=value,
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(portfolio)
            session.commit()

    def get_portfolio(self, symbol: Optional[str] = None) -> List[Portfolio]:
        with self.get_session() as session:
            if symbol:
                return session.query(Portfolio).filter_by(symbol=symbol).all()
            return session.query(Portfolio).all()

    def set_setting(self, key: str, value: str):
        with self.get_session() as session:
            setting = session.query(SystemSetting).filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                session.add(SystemSetting(key=key, value=value))
            session.commit()

    def get_setting(self, key: str) -> Optional[str]:
        with self.get_session() as session:
            setting = session.query(SystemSetting).filter_by(key=key).first()
            return setting.value if setting else None

    def get_all_settings(self) -> Dict[str, str]:
        with self.get_session() as session:
            settings = session.query(SystemSetting).all()
            return {s.key: s.value for s in settings}

    def get_automation_stats(self) -> Dict[str, str]:
        return {
            "total_signals": str(len(self.get_signals())),
            "open_trades": str(len(self.get_open_trades())),
            "timestamp": str(datetime.now())
        }

    def get_daily_pnl_pct(self) -> float:
        with self.get_session() as session:
            today = date.today()
            trades = session.query(Trade).filter(
                Trade.status == 'closed',
                Trade.timestamp >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
            ).all()
            total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
            total_entry = sum(t.entry_price * t.qty for t in trades if t.entry_price and t.qty)
            return round((total_pnl / total_entry) * 100, 2) if total_entry else 0.0

    def update_automation_stats(self, stats_dict: dict):
        with self.get_session() as session:
            setting = session.query(SystemSetting).filter_by(key="AUTOMATION_STATS").first()
            if setting:
                setting.value = json.dumps(stats_dict)
            else:
                session.add(SystemSetting(key="AUTOMATION_STATS", value=json.dumps(stats_dict)))
            session.commit()

    def _settings_file(self) -> str:
        return "settings.json"

    def _load_settings_from_file(self):
        if os.path.exists(self._settings_file()):
            try:
                with open(self._settings_file(), "r") as f:
                    file_settings = json.load(f)
                    self.settings.update(file_settings)
                    print("[DB] ✅ Loaded settings from settings.json")
            except Exception as e:
                print(f"[DB] ⚠️ Failed to load settings: {e}")
        else:
            self._save_settings_to_file()

    def _save_settings_to_file(self):
        try:
            with open(self._settings_file(), "w") as f:
                json.dump(self.settings, f, indent=4)
                print("[DB] 💾 Settings saved to file")
        except Exception as e:
            print(f"[DB] ❌ Failed to save settings: {e}")

    def update_setting(self, key: str, value: str):
        self.settings[key] = value
        self._save_settings_to_file()
        print(f"[DB] ⚙️ Updated setting {key} → {value}")

    def reset_all_settings_to_defaults(self):
        self.settings = {
            "SCAN_INTERVAL": 3600,
            "TOP_N_SIGNALS": 5,
            "MAX_LOSS_PCT": -15.0,
            "TP_PERCENT": 0.30,
            "SL_PERCENT": 0.15,
            "LEVERAGE": 20,
            "RISK_PER_TRADE": 0.01,
        }
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