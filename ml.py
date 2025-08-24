import os
import numpy as np
import pandas as pd
import joblib
import logging
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from dotenv import load_dotenv
from typing import Dict, List

from db import db_manager as db  # Use db_manager from db.py

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
MODEL_PATH = os.getenv("MODEL_PATH", "ml_models/profit_xgb_model.pkl")


class MLFilter:
    def __init__(self):
        self.model = self._load_model()
        self.db = db
        self._last_training_size = 0

    def _load_model(self):
        try:
            if os.path.exists(MODEL_PATH):
                logger.info("[ML] ✅ Loaded trained model from %s", MODEL_PATH)
                return joblib.load(MODEL_PATH)
            else:
                logger.warning("[ML] ⚠️ No trained model found at %s. Using fallback scoring.", MODEL_PATH)
                return None
        except Exception as e:
            logger.error("[ML] ❌ Failed to load model: %s", e)
            return None

    def extract_features(self, signal: Dict) -> np.ndarray:
        try:
            # Align with signal_generator.py signal structure
            trend = signal.get("Type", "Neutral")  # Use 'Type' instead of 'trend'
            bb_slope = signal.get("BB Slope", "No")
            regime = "Breakout" if bb_slope != "No" else "Mean"  # Derive regime from BB Slope
            
            return np.array([
                float(signal.get("Entry", 0)),
                float(signal.get("TP", 0)),
                float(signal.get("SL", 0)),
                float(signal.get("Trail", 0)),
                float(signal.get("Score", 0)),
                float(signal.get("Score", 0)),  # Use Score as proxy for confidence if not set
                1 if signal.get("Side", "").lower() == "buy" else 0,
                1 if trend in ["Up", "Bullish"] else -1 if trend in ["Down", "Bearish"] else 0,
                1 if regime == "Breakout" else 0,
            ])
        except Exception as e:
            logger.error("[ML] ❌ Failed to extract features from signal: %s", e)
            return np.zeros(9)  # Return zero array to avoid crashes

    def enhance_signal(self, signal: Dict) -> Dict:
        try:
            if self.model:
                features = self.extract_features(signal).reshape(1, -1)
                prob = self.model.predict_proba(features)[0][1]
                signal["Score"] = round(prob * 100, 2)
                signal["confidence"] = min(signal["Score"] + 5.0, 100.0)  # Deterministic boost
            else:
                # Fallback scoring: use existing score or default to 60
                signal["Score"] = float(signal.get("Score", 60.0))
                signal["confidence"] = min(signal["Score"] + 5.0, 100.0)

            entry_price = float(signal.get("Entry", 0))
            leverage = int(signal.get("leverage", 20))
            capital = float(signal.get("capital", 100))

            if entry_price > 0 and leverage > 0:
                margin = capital / leverage
                signal["Margin"] = round(margin, 2)
            else:
                signal["Margin"] = 5.0

            return signal
        except Exception as e:
            logger.error("[ML] ❌ Failed to enhance signal: %s", e)
            signal["Score"] = 60.0
            signal["confidence"] = 65.0
            signal["Margin"] = 5.0
            return signal

    def load_data_from_db(self, limit: int = 1000) -> List[Dict]:
        try:
            combined = []
            # Load closed trades (real and virtual)
            trades = self.db.get_closed_real_trades() + self.db.get_closed_virtual_trades()
            for trade in trades[:limit]:
                t = trade.to_dict()
                entry_price = float(t.get("entry_price", 0))
                exit_price = float(t.get("exit_price", 0))
                
                if entry_price and exit_price:
                    direction = 1 if t["side"].lower() == "buy" else -1
                    profit = 1 if direction * (exit_price - entry_price) > 0 else 0
                else:
                    profit = 1 if float(t.get("pnl", 0)) > 0 else 0

                combined.append({
                    "entry": entry_price,
                    "tp": float(t.get("take_profit", 0)),
                    "sl": float(t.get("stop_loss", 0)),
                    "trail": float(t.get("trail", 0)),
                    "score": float(t.get("score", 60)),
                    "confidence": float(t.get("score", 60)),
                    "side": t.get("side", "Buy"),
                    "trend": t.get("trend", "Neutral"),
                    "regime": t.get("regime", "Breakout"),
                    "profit": profit,
                })

            # Load ML training data (signals)
            signals = self.db.get_ml_training_data(limit=limit)
            for s in signals:
                combined.append({
                    "entry": float(s.get("entry", 0)),
                    "tp": float(s.get("tp", 0)),
                    "sl": float(s.get("sl", 0)),
                    "trail": float(s.get("trail", 0)),
                    "score": float(s.get("score", 60)),
                    "confidence": float(s.get("score", 60)),
                    "side": s.get("side", "Buy"),
                    "trend": s.get("trend", "Neutral"),
                    "regime": s.get("regime", "Breakout"),
                    "profit": 1 if float(s.get("score", 0)) > 70 else 0,
                })

            logger.info("[ML] ✅ Loaded %d total training records from DB.", len(combined))
            return combined
        except Exception as e:
            logger.error("[ML] ❌ Failed to load data from DB: %s", e)
            return []

    def train_from_db(self):
        try:
            all_data = self.load_data_from_db()
            df = pd.DataFrame(all_data)

            if df.empty or len(df) < 30:
                logger.warning("[ML] ❌ Not enough data to train. Found only %d rows.", len(df))
                return

            # Encode categorical
            df["side_enc"] = df["side"].map({"Buy": 1, "Sell": 0}).fillna(0)
            df["trend_enc"] = df["trend"].map({"Up": 1, "Bullish": 1, "Down": -1, "Bearish": -1, "Neutral": 0}).fillna(0)
            df["regime_enc"] = df["regime"].map({"Breakout": 1, "Mean": 0}).fillna(0)
            df = df.fillna(0)

            feature_columns = ["entry", "tp", "sl", "trail", "score", "confidence", "side_enc", "trend_enc", "regime_enc"]
            X = df[feature_columns]
            y = df["profit"]

            if len(y.unique()) < 2:
                logger.warning("[ML] ⚠️ Only one class found in target variable. Cannot train binary classifier.")
                return

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            model = XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                eval_metric="logloss",
                random_state=42
            )
            
            model.fit(X_train, y_train)
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            joblib.dump(model, MODEL_PATH)
            self.model = model

            acc = model.score(X_test, y_test)
            train_acc = model.score(X_train, y_train)

            self._last_training_size = len(df)

            logger.info("[ML] ✅ Model trained successfully!")
            logger.info("[ML] 📊 Training records: %d", len(df))
            logger.info("[ML] 🎯 Train accuracy: %.2f%%", train_acc * 100)
            logger.info("[ML] 🎯 Test accuracy: %.2f%%", acc * 100)
            logger.info("[ML] 💾 Model saved to: %s", MODEL_PATH)
            
        except Exception as e:
            logger.error("[ML] ❌ Training failed: %s", e)

    def update_model_with_new_data(self, min_new_records: int = 10):
        try:
            total_trades = self.db.get_trades_count()
            total_signals = self.db.get_signals_count()
            total_records = total_trades + total_signals

            new_records = total_records - self._last_training_size
            
            if new_records >= min_new_records:
                logger.info("[ML] 🔄 Found %d new records. Retraining model...", new_records)
                self.train_from_db()
                return True
            else:
                logger.info("[ML] ℹ️ Only %d new records. Minimum %d required for retraining.", new_records, min_new_records)
                return False
                
        except Exception as e:
            logger.error("[ML] ❌ Failed to update model: %s", e)
            return False

    def get_model_stats(self):
        stats = {
            "model_exists": self.model is not None,
            "model_path": MODEL_PATH,
            "model_file_exists": os.path.exists(MODEL_PATH)
        }
        
        try:
            data = self.load_data_from_db()
            df = pd.DataFrame(data)
            
            stats.update({
                "total_records": len(df),
                "profitable_records": int(sum(df["profit"])) if not df.empty else 0,
                "profit_rate": float(sum(df["profit"]) / len(df)) if not df.empty else 0,
                "trades_count": self.db.get_trades_count(),
                "signals_count": self.db.get_signals_count()
            })
        except Exception as e:
            stats["error"] = str(e)
            
        return stats


# === CLI Entrypoint ===
if __name__ == "__main__":
    ml = MLFilter()
    logger.info("[ML] 📊 Current model stats: %s", ml.get_model_stats())
    ml.train_from_db()